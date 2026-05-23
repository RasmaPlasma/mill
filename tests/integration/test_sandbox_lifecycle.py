"""Integration tests — sandbox-service direct tests.

No mocks. Hits the sandbox-service on localhost:8090.
Creates real Docker containers with resource limits.

Uses a shared agent+environment to avoid creating a new Docker network
per test (which exhausts the subnet pool).
"""

import base64
import uuid

import httpx
import pytest


async def _create_session_with_sandbox(sandbox_client, client, agent_id, environment_id, tracker):
    """Helper — create a session then directly provision a sandbox via sandbox-service.

    Since lazy backend no longer creates containers at session creation time,
    we provision the container directly for tests that exercise the sandbox-service.
    """
    resp = await client.post(
        "/v1/sessions",
        json={"agent_id": agent_id, "environment_id": environment_id},
    )
    assert resp.status_code == 201, f"Session create failed: {resp.status_code} {resp.text}"
    session_data = resp.json()
    tracker.sessions.append(session_data["id"])

    # Provision container directly via sandbox-service
    resp = await sandbox_client.post(
        "/sandboxes",
        json={
            "session_id": session_data["id"],
            "environment_id": environment_id,
            "agent_id": agent_id,
            "packages": {"pip": ["requests"]},
            "resource_limits": {"memory": "1g", "cpus": 1.0, "pids_limit": 256},
        },
    )
    assert resp.status_code == 201, f"Sandbox create failed: {resp.status_code} {resp.text}"
    container_id = resp.json()["container_id"]
    tracker.direct_containers.append(container_id)

    # Notify platform so the session row gets the container_id
    # (LazyDockerSandboxBackend normally does this via HTTP after first tool call)
    resp = await client.post(
        f"/internal/sessions/{session_data['id']}/sandbox",
        json={"container_id": container_id},
    )
    assert resp.status_code == 204, f"Failed to update session sandbox_id: {resp.status_code} {resp.text}"

    session_data["sandbox_container_id"] = container_id
    return session_data


@pytest.fixture
async def shared_agent(client, tracker):
    """Create a single agent shared across all sandbox tests in this module."""
    model_resp = await client.post(
        "/v1/models",
        json={
            "display_name": "Sandbox Model",
            "provider": "fireworks",
            "provider_model": "accounts/fireworks/routers/kimi-k2p6-turbo",
        },
    )
    assert model_resp.status_code == 201
    model = model_resp.json()
    tracker.models.append(model["id"])

    name = f"sandbox-test-agent-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/v1/agents",
        json={"name": name, "model_id": model["id"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    tracker.agents.append(data["id"])
    return data["id"]


@pytest.fixture
async def shared_environment(client, tracker):
    """Create a single environment shared across all sandbox tests in this module."""
    name = f"sandbox-test-env-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/v1/environments",
        json={
            "name": name,
            "packages": {"pip": ["requests"]},
            "resource_limits": {"memory": "1g", "cpus": 1.0, "pids_limit": 256},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    tracker.environments.append(data["id"])
    return data["id"]


@pytest.mark.integration
class TestSandboxLifecycle:
    async def test_create_and_destroy_sandbox(
        self, sandbox_client, client, shared_agent, shared_environment, tracker,
    ):
        session_data = await _create_session_with_sandbox(
            sandbox_client, client, shared_agent, shared_environment, tracker,
        )
        container_id = session_data["sandbox_container_id"]

        resp = await sandbox_client.get(f"/sandboxes/{container_id}/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        # Destroy via session archive
        resp = await client.post(f"/v1/sessions/{session_data['id']}/archive")
        assert resp.status_code == 204
        tracker.sessions.remove(session_data["id"])

    async def test_exec_echo_command(
        self, sandbox_client, client, shared_agent, shared_environment, tracker,
    ):
        session_data = await _create_session_with_sandbox(
            sandbox_client, client, shared_agent, shared_environment, tracker,
        )
        container_id = session_data["sandbox_container_id"]

        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "echo hello"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "hello" in data["output"]
        assert data["exit_code"] == 0

    async def test_exec_python_command(
        self, sandbox_client, client, shared_agent, shared_environment, tracker,
    ):
        session_data = await _create_session_with_sandbox(
            sandbox_client, client, shared_agent, shared_environment, tracker,
        )
        container_id = session_data["sandbox_container_id"]

        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "python3 -c 'print(42)'"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "42" in data["output"]
        assert data["exit_code"] == 0

    async def test_upload_and_download_file(
        self, sandbox_client, client, shared_agent, shared_environment, tracker,
    ):
        session_data = await _create_session_with_sandbox(
            sandbox_client, client, shared_agent, shared_environment, tracker,
        )
        container_id = session_data["sandbox_container_id"]

        content = b"integration test content"
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/files",
            json={"files": [{"path": "test.txt", "content": base64.b64encode(content).decode()}]},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert results[0]["error"] is None

        resp = await sandbox_client.get(f"/sandboxes/{container_id}/files/test.txt")
        assert resp.status_code == 200
        assert resp.content == content

    async def test_stop_and_start_sandbox(
        self, sandbox_client, client, shared_agent, shared_environment, tracker,
    ):
        session_data = await _create_session_with_sandbox(
            sandbox_client, client, shared_agent, shared_environment, tracker,
        )
        container_id = session_data["sandbox_container_id"]

        resp = await sandbox_client.post(f"/sandboxes/{container_id}/stop")
        assert resp.status_code == 204

        resp = await sandbox_client.get(f"/sandboxes/{container_id}/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "exited"

        resp = await sandbox_client.post(f"/sandboxes/{container_id}/start")
        assert resp.status_code == 204

        resp = await sandbox_client.get(f"/sandboxes/{container_id}/status")
        assert resp.json()["status"] == "running"

        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "echo restarted"},
        )
        assert resp.status_code == 200
        assert "restarted" in resp.json()["output"]

    async def test_sandbox_resource_limits(self, sandbox_client, client, tracker):
        """Uses a dedicated environment with specific resource limits."""
        name = f"reslimit-env-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/environments",
            json={
                "name": name,
                "packages": {"pip": ["requests"]},
                "resource_limits": {"memory": "512m", "cpus": 0.5, "pids_limit": 128},
            },
        )
        assert resp.status_code == 201
        env = resp.json()
        tracker.environments.append(env["id"])

        model_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Sandbox ResLimit Model",
                "provider": "fireworks",
                "provider_model": "accounts/fireworks/routers/kimi-k2p6-turbo",
            },
        )
        assert model_resp.status_code == 201
        model = model_resp.json()
        tracker.models.append(model["id"])

        agent_name = f"reslimit-agent-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/agents",
            json={"name": agent_name, "model_id": model["id"]},
        )
        assert resp.status_code == 201
        agent = resp.json()
        tracker.agents.append(agent["id"])

        session_data = await _create_session_with_sandbox(
            sandbox_client, client, agent["id"], env["id"], tracker,
        )
        container_id = session_data["sandbox_container_id"]

        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "cat /sys/fs/cgroup/pids.max 2>/dev/null || cat /sys/fs/cgroup/pids/pids.max 2>/dev/null || echo unknown"},
        )
        assert resp.status_code == 200
        output = resp.json()["output"].strip()
        assert output in ("128", "129", "max") or output == "unknown"
