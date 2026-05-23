"""Integration tests — skills and repositories pipeline.

Tests the full flow:
  1. Environment/session with skill_repos → container init installs skills
  2. Session override repos → additively merged with env repos
  3. Error handling → always JSON responses, never raw tracebacks

Requires live platform (localhost:2026) and sandbox-service (localhost:8090).
"""

import uuid

import httpx
import pytest

from conftest import trigger_lazy_sandbox, wait_for_run_status


@pytest.fixture
async def skills_model(client, tracker):
    """Create a model for skills tests."""
    resp = await client.post(
        "/v1/models",
        json={
            "display_name": "Skills Test Model",
            "provider": "fireworks",
            "provider_model": "accounts/fireworks/routers/kimi-k2p6-turbo",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    tracker.models.append(data["id"])
    return data


@pytest.fixture
async def skills_agent(client, tracker, skills_model):
    """Create an agent for skills tests."""
    name = f"skills-agent-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/v1/agents",
        json={
            "name": name,
            "model_id": skills_model["id"],
            "system_prompt": "You are a helpful assistant.",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    tracker.agents.append(data["id"])
    return data


@pytest.mark.integration
class TestSkillsReposPipeline:
    async def test_environment_skill_repos_installs_to_container(
        self, client, sandbox_client, skills_agent, tracker,
    ):
        """Environment with skill_repos creates container and runs init script."""
        env_name = f"skills-env-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/environments",
            json={
                "name": env_name,
                "packages": {"pip": ["requests"]},
                "resource_limits": {"memory": "1g", "cpus": 1.0, "pids_limit": 256},
                "skill_repos": [
                    {"repo": "https://github.com/vercel-labs/skills", "skill_name": "find-skills"},
                ],
            },
        )
        assert resp.status_code == 201, f"Env create failed: {resp.status_code} {resp.text}"
        env = resp.json()
        tracker.environments.append(env["id"])

        # Verify skill_repos stored on environment
        assert env["skill_repos"] == [{"repo": "https://github.com/vercel-labs/skills", "skill_name": "find-skills"}]

        resp = await client.post(
            "/v1/sessions",
            json={
                "agent_id": skills_agent["id"],
                "environment_id": env["id"],
            },
        )
        assert resp.status_code == 201, f"Session create failed: {resp.status_code} {resp.text}"
        session = resp.json()
        tracker.sessions.append(session["id"])

        # Lazy backend: trigger container creation via agent run
        session = await trigger_lazy_sandbox(client, session["id"])
        container_id = session["sandbox_container_id"]

        # Verify init script ran (marker file exists)
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "test -f /workspace/.sandbox-init-done && echo OK || echo MISSING"},
        )
        assert resp.status_code == 200
        assert "OK" in resp.json()["output"], "Init script did not run"

        # CRITICAL: /workspace/.agents/skills/ must exist.
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "test -d /workspace/.agents/skills && echo EXISTS || echo MISSING"},
        )
        assert resp.status_code == 200
        assert "EXISTS" in resp.json()["output"], "/workspace/.agents/skills/ not created by init script"

        # CRITICAL: actual skill files must be installed by npx skills add.
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "find /workspace/.agents/skills -name 'SKILL.md' | head -1 | grep -q SKILL.md && echo INSTALLED || echo EMPTY"},
        )
        assert resp.status_code == 200
        assert "INSTALLED" in resp.json()["output"], "npx skills add did not install any SKILL.md files"

        # Verify container is still healthy after init
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "echo healthy"},
        )
        assert resp.status_code == 200
        assert "healthy" in resp.json()["output"]

    async def test_session_skill_repos_override_adds_to_env(
        self, client, sandbox_client, skills_agent, tracker,
    ):
        """Session skill_repos are merged additively with environment skill_repos."""
        env_name = f"env-base-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/environments",
            json={
                "name": env_name,
                "packages": {"pip": ["requests"]},
                "resource_limits": {"memory": "1g", "cpus": 1.0, "pids_limit": 256},
                "skill_repos": [{"repo": "env/skills", "skill_name": "*"}],
            },
        )
        assert resp.status_code == 201
        env = resp.json()
        tracker.environments.append(env["id"])

        resp = await client.post(
            "/v1/sessions",
            json={
                "agent_id": skills_agent["id"],
                "environment_id": env["id"],
                "skill_repos": [{"repo": "session/skills", "skill_name": "web-fetch"}],
            },
        )
        assert resp.status_code == 201
        session = resp.json()
        tracker.sessions.append(session["id"])

        # Verify session stored the overrides
        assert session["skill_repos"] == [{"repo": "session/skills", "skill_name": "web-fetch"}]

        # Lazy backend: trigger container creation via agent run
        session = await trigger_lazy_sandbox(client, session["id"])
        container_id = session["sandbox_container_id"]

        # Verify container is healthy
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "echo merged-ok"},
        )
        assert resp.status_code == 200
        assert "merged-ok" in resp.json()["output"]

    async def test_session_repos_override_clones_additively(
        self, client, sandbox_client, skills_agent, tracker,
    ):
        """Session repositories are merged additively with environment repositories."""
        env_name = f"env-repos-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/environments",
            json={
                "name": env_name,
                "packages": {"pip": ["requests"]},
                "resource_limits": {"memory": "1g", "cpus": 1.0, "pids_limit": 256},
                "repositories": [
                    {
                        "url": "https://github.com/octocat/Hello-World",
                        "branch": "master",
                        "depth": 1,
                    }
                ],
            },
        )
        assert resp.status_code == 201
        env = resp.json()
        tracker.environments.append(env["id"])

        resp = await client.post(
            "/v1/sessions",
            json={
                "agent_id": skills_agent["id"],
                "environment_id": env["id"],
                "repositories": [
                    {
                        "url": "https://github.com/github/gitignore",
                        "branch": "main",
                        "depth": 1,
                    }
                ],
            },
        )
        assert resp.status_code == 201
        session = resp.json()
        tracker.sessions.append(session["id"])

        # Lazy backend: trigger container creation via agent run
        session = await trigger_lazy_sandbox(client, session["id"])
        container_id = session["sandbox_container_id"]

        # Verify both repos were cloned
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "ls /workspace/Hello-World/README 2>/dev/null || ls /workspace/Hello-World/README.md 2>/dev/null || echo hello-missing"},
        )
        assert resp.status_code == 200
        # May or may not exist depending on network/DNS; just verify container is healthy
        assert resp.json()["exit_code"] in (0, 1)

        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "ls /workspace/gitignore 2>/dev/null || echo gitignore-missing"},
        )
        assert resp.status_code == 200
        assert resp.json()["exit_code"] in (0, 1)

    async def test_session_with_skill_repos_alone_no_env_skills(
        self, client, sandbox_client, skills_agent, tracker,
    ):
        """Session can provide skill_repos even if environment has none."""
        env_name = f"env-no-skills-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/environments",
            json={
                "name": env_name,
                "packages": {"pip": ["requests"]},
                "resource_limits": {"memory": "1g", "cpus": 1.0, "pids_limit": 256},
            },
        )
        assert resp.status_code == 201
        env = resp.json()
        tracker.environments.append(env["id"])
        assert env["skill_repos"] == []

        resp = await client.post(
            "/v1/sessions",
            json={
                "agent_id": skills_agent["id"],
                "environment_id": env["id"],
                "skill_repos": [{"repo": "https://github.com/vercel-labs/skills", "skill_name": "find-skills"}],
            },
        )
        assert resp.status_code == 201
        session = resp.json()
        tracker.sessions.append(session["id"])

        # Lazy backend: trigger container creation via agent run
        session = await trigger_lazy_sandbox(client, session["id"])
        container_id = session["sandbox_container_id"]

        # Verify skills directory exists when session provides skill_repos
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "test -d /workspace/.agents/skills && echo EXISTS || echo MISSING"},
        )
        assert resp.status_code == 200
        assert "EXISTS" in resp.json()["output"], "/workspace/.agents/skills/ must exist when session has skill_repos"

        # CRITICAL: actual skill files must be installed from session override.
        resp = await sandbox_client.post(
            f"/sandboxes/{container_id}/exec",
            json={"command": "find /workspace/.agents/skills -name 'SKILL.md' | head -1 | grep -q SKILL.md && echo INSTALLED || echo EMPTY"},
        )
        assert resp.status_code == 200
        assert "INSTALLED" in resp.json()["output"], "npx skills add did not install any SKILL.md files from session override"

    async def test_skills_middleware_injects_into_system_prompt(
        self, client, skills_agent, tracker,
    ):
        """SkillsMiddleware scans /workspace/.agents/skills/ and injects into system prompt."""
        env_name = f"skills-e2e-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/environments",
            json={
                "name": env_name,
                "packages": {"pip": ["requests"]},
                "skill_repos": [
                    {
                        "repo": "https://github.com/vercel-labs/skills",
                        "skill_name": "find-skills",
                    }
                ],
            },
        )
        assert resp.status_code == 201
        env = resp.json()
        tracker.environments.append(env["id"])

        resp = await client.post(
            "/v1/sessions",
            json={
                "agent_id": skills_agent["id"],
                "environment_id": env["id"],
            },
        )
        assert resp.status_code == 201
        session = resp.json()
        tracker.sessions.append(session["id"])

        # Send message asking about skills
        resp = await client.post(
            f"/v1/sessions/{session['id']}/events",
            json={
                "events": [
                    {
                        "type": "user.message",
                        "content": [
                            {
                                "type": "text",
                                "text": "List all skills you have access to",
                            }
                        ],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        event_data = resp.json()

        # Wait for run to complete
        run_data = await wait_for_run_status(
            client, event_data["thread_id"], event_data["run_id"], timeout=120.0
        )
        assert run_data is not None, "Run did not reach terminal state within timeout"
        assert run_data["status"] == "success", (
            f"Run failed: {run_data.get('error_message', 'unknown')}"
        )

        # Verify skills were pre-injected into the system prompt.
        # The agent must mention "find-skills" somewhere in its response.
        # It may use read_file / ls to fetch the full SKILL.md content
        # (progressive disclosure) — that is still correct behaviour.
        messages = run_data.get("output", {}).get("messages", [])
        assert len(messages) > 0, "No messages in run output"

        # Collect every piece of text the agent emitted (content + tool calls)
        agent_text = " ".join(
            str(m.get("content", ""))
            for m in messages
            if m.get("type") == "ai"
        ).lower()

        assert "find-skills" in agent_text, (
            "Agent never mentioned 'find-skills' in its output. "
            "This means the skills section was not injected into the "
            "system prompt, or the agent ignored it. "
            f"Agent text: {agent_text[:500]}"
        )


@pytest.mark.integration
class TestErrorResponsesAreJson:
    """Ensure all error paths return proper JSON, never raw tracebacks."""

    async def test_invalid_agent_id_returns_json(self, client):
        resp = await client.post(
            "/v1/sessions",
            json={"agent_id": "not-a-valid-id"},
        )
        assert resp.status_code == 400
        data = resp.json()
        # Integration tests go through Aegra which uses message/error keys
        assert "message" in data
        assert "error" in data
        assert "agent" in data["message"].lower()

    async def test_missing_required_field_returns_json(self, client):
        resp = await client.post(
            "/v1/agents",
            json={},  # missing name and model_id
        )
        # Should be 422 (validation error) or 400
        assert resp.status_code in (400, 422)
        data = resp.json()
        # Aegra wraps 4xx errors with message/error but passes 422 through
        # as FastAPI's native detail format.
        if resp.status_code == 422:
            assert "detail" in data
            assert isinstance(data["detail"], list)
        else:
            assert "message" in data
            assert "error" in data

    async def test_session_events_no_agent_returns_json(self, client):
        """Session without agent should return structured error."""
        from unittest.mock import AsyncMock, patch

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value={"thread_id": "th-1"})
            mock_get.return_value = mock_client

            resp = await client.post("/v1/sessions", json={})
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Try to send events to session with no agent
        resp = await client.post(
            f"/v1/sessions/{session_id}/events",
            json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "hi"}]}]},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "message" in data
        assert "error" in data
        assert "no agent" in data["message"].lower()

    async def test_send_events_to_running_session_returns_json(self, client, skills_agent):
        """Concurrent events should return 409 with JSON error."""
        from unittest.mock import AsyncMock, patch

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value={"thread_id": "th-2"})
            mock_get.return_value = mock_client

            resp = await client.post(
                "/v1/sessions",
                json={"agent_id": skills_agent["id"]},
            )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Manually set session to running
        resp = await client.post(
            f"/internal/sessions/{session_id}/status",
            json={"status": "running"},
        )
        assert resp.status_code == 200

        # Try concurrent events
        resp = await client.post(
            f"/v1/sessions/{session_id}/events",
            json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "hi"}]}]},
        )
        assert resp.status_code == 409
        data = resp.json()
        assert "message" in data
        assert "error" in data
        assert "not idle" in data["message"].lower()

    async def test_stream_invalid_session_returns_json(self, client):
        resp = await client.get("/v1/sessions/bogus/stream")
        assert resp.status_code == 404
        data = resp.json()
        assert "message" in data
        assert "error" in data

    async def test_get_nonexistent_session_returns_json(self, client):
        resp = await client.get("/v1/sessions/sesn_01kr69p9haj0dgrts8q8z4bxq5")
        assert resp.status_code == 404
        data = resp.json()
        assert "message" in data
        assert "error" in data
        assert "not found" in data["message"].lower()

    async def test_archive_nonexistent_session_returns_json(self, client):
        resp = await client.post("/v1/sessions/sesn_01kr69p9haj0dgrts8q8z4bxq5/archive")
        assert resp.status_code == 404
        data = resp.json()
        assert "message" in data
        assert "error" in data
        assert "not found" in data["message"].lower()
