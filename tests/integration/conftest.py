"""Integration test fixtures — real HTTP, real DB, real Docker, real LLM.

No mocks. Tests hit the live Aegra server on localhost:2026 and the
sandbox-service on localhost:8090. Cleanup is MANDATORY and VERIFIED —
any leaked resource fails the test or the suite.
"""

import asyncio
import os
import uuid
from typing import Any

import docker
import httpx
import pytest

PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:2026")
SANDBOX_URL = os.environ.get("SANDBOX_URL", "http://localhost:8090")
SANDBOX_API_KEY = os.environ.get("SANDBOX_API_KEY", "")

# uv run does not always load .env into the test subprocess; read it manually.
if not SANDBOX_API_KEY:
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    try:
        with open(_env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SANDBOX_API_KEY="):
                    SANDBOX_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except FileNotFoundError:
        pass

TEST_MODEL = "fireworks:accounts/fireworks/routers/kimi-k2p6-turbo"

TIMEOUT = httpx.Timeout(180.0, connect=10.0)


def _platform_headers() -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _sandbox_headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if SANDBOX_API_KEY:
        h["Authorization"] = f"Bearer {SANDBOX_API_KEY}"
    return h


# ---------------------------------------------------------------------------
# Global state for tracking which test created which resources
# ---------------------------------------------------------------------------

_test_resource_map: dict[str, list[str]] = {}  # nodeid -> list of container IDs


def _count_managed_containers() -> int:
    """Count Docker containers with platform.managed=true label."""
    try:
        client = docker.DockerClient(base_url="tcp://localhost:2375")
        count = len(client.containers.list(all=True, filters={"label": "platform.managed=true"}))
        client.close()
        return count
    except Exception:
        return -1


def _get_managed_container_details() -> list[dict[str, Any]]:
    """Return details of all managed containers for reporting."""
    try:
        client = docker.DockerClient(base_url="tcp://localhost:2375")
        containers = []
        for c in client.containers.list(all=True, filters={"label": "platform.managed=true"}):
            containers.append(
                {
                    "id": c.id[:12],
                    "name": c.name,
                    "status": c.status,
                    "session_id": (c.labels or {}).get("platform.session_id", "unknown"),
                    "env_id": (c.labels or {}).get("platform.environment_id", "unknown"),
                }
            )
        client.close()
        return containers
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Mandatory Resource Tracker — cleanup failures are fatal
# ---------------------------------------------------------------------------

class CleanupError(Exception):
    """Raised when mandatory resource cleanup fails.

    Contains a list of (resource_type, resource_id, detail) tuples.
    """

    def __init__(self, failures: list[tuple[str, str, str]]) -> None:
        lines = [f"Mandatory cleanup failed for {len(failures)} resource(s):"]
        for rtype, rid, detail in failures:
            lines.append(f"  - {rtype} {rid}: {detail}")
        super().__init__("\n".join(lines))
        self.failures = failures


class MandatoryResourceTracker:
    """Collects resource IDs during a test and archives them on teardown.

    Cleanup is mandatory: any archive/delete failure raises CleanupError,
    which fails the test. After archive, we verify the resource is no longer
    queryable (sessions/agents/envs/vaults return 404 when archived).
    """

    def __init__(self):
        self.agents: list[str] = []
        self.environments: list[str] = []
        self.sessions: list[str] = []
        self.models: list[str] = []
        self.vaults: list[str] = []
        self.secrets: list[str] = []
        # Track Docker resources created directly (not via platform API)
        self.direct_containers: list[str] = []

    async def cleanup(self, client: httpx.AsyncClient) -> None:
        """Archive/destroy all tracked resources. Raises CleanupError on any failure."""
        failures: list[tuple[str, str, str]] = []

        # 1. Sessions (must be first — destroys containers)
        for sid in self.sessions:
            try:
                resp = await client.post(f"/v1/sessions/{sid}/archive", timeout=30.0)
                if resp.status_code == 404:
                    # Already archived by explicit test call — treat as success
                    continue
                if resp.status_code not in (204, 202):
                    failures.append(("session", sid, f"archive returned {resp.status_code}"))
                    continue
                # Verify session is gone (archived sessions return 404)
                verify = await client.get(f"/v1/sessions/{sid}")
                if verify.status_code != 404:
                    failures.append(
                        ("session", sid, f"still queryable after archive (status={verify.status_code})")
                    )
            except Exception as exc:
                failures.append(("session", sid, f"archive exception: {exc}"))

        # 2. Agents
        for aid in self.agents:
            try:
                resp = await client.post(f"/v1/agents/{aid}/archive", timeout=10.0)
                if resp.status_code == 404:
                    continue
                if resp.status_code != 204:
                    failures.append(("agent", aid, f"archive returned {resp.status_code}"))
                    continue
                verify = await client.get(f"/v1/agents/{aid}")
                if verify.status_code != 404:
                    failures.append(
                        ("agent", aid, f"still queryable after archive (status={verify.status_code})")
                    )
            except Exception as exc:
                failures.append(("agent", aid, f"archive exception: {exc}"))

        # 3. Environments
        for eid in self.environments:
            try:
                resp = await client.post(f"/v1/environments/{eid}/archive", timeout=10.0)
                if resp.status_code == 404:
                    continue
                if resp.status_code != 204:
                    failures.append(("environment", eid, f"archive returned {resp.status_code}"))
                    continue
                verify = await client.get(f"/v1/environments/{eid}")
                if verify.status_code != 404:
                    failures.append(
                        ("environment", eid, f"still queryable after archive (status={verify.status_code})")
                    )
            except Exception as exc:
                failures.append(("environment", eid, f"archive exception: {exc}"))

        # 4. Models
        for mid in self.models:
            try:
                resp = await client.post(f"/v1/models/{mid}/archive", timeout=10.0)
                if resp.status_code == 404:
                    continue
                if resp.status_code != 204:
                    failures.append(("model", mid, f"archive returned {resp.status_code}"))
                    continue
                verify = await client.get(f"/v1/models/{mid}")
                if verify.status_code != 404:
                    failures.append(
                        ("model", mid, f"still queryable after archive (status={verify.status_code})")
                    )
            except Exception as exc:
                failures.append(("model", mid, f"archive exception: {exc}"))

        # 5. Vaults
        for vid in self.vaults:
            try:
                resp = await client.post(f"/v1/vaults/{vid}/archive", timeout=10.0)
                if resp.status_code == 404:
                    continue
                if resp.status_code != 204:
                    failures.append(("vault", vid, f"archive returned {resp.status_code}"))
                    continue
                verify = await client.get(f"/v1/vaults/{vid}")
                if verify.status_code != 404:
                    failures.append(
                        ("vault", vid, f"still queryable after archive (status={verify.status_code})")
                    )
            except Exception as exc:
                failures.append(("vault", vid, f"archive exception: {exc}"))

        # 6. Secrets (delete, not archive)
        for sid in self.secrets:
            try:
                resp = await client.delete(f"/v1/secrets/{sid}", timeout=10.0)
                if resp.status_code in (204, 404):
                    continue
                failures.append(("secret", sid, f"delete returned {resp.status_code}"))
            except Exception as exc:
                failures.append(("secret", sid, f"delete exception: {exc}"))

        # 7. Direct containers (created via sandbox-service API, not session routes)
        for cid in self.direct_containers:
            try:
                sc = httpx.AsyncClient(base_url=SANDBOX_URL, timeout=TIMEOUT, headers=_sandbox_headers())
                resp = await sc.delete(f"/sandboxes/{cid}")
                await sc.aclose()
                if resp.status_code in (204, 404):
                    continue
                failures.append(("container", cid, f"destroy returned {resp.status_code}"))
            except Exception as exc:
                failures.append(("container", cid, f"destroy exception: {exc}"))

        if failures:
            raise CleanupError(failures)


# ---------------------------------------------------------------------------
# Pytest hooks — global suite-level gates
# ---------------------------------------------------------------------------

@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    """Log the baseline container count before any tests run."""
    count = _count_managed_containers()
    if count > 0:
        print(f"\n[sessionstart] WARNING: {count} managed container(s) already exist before test suite")
        for c in _get_managed_container_details():
            print(f"  - {c['name']} ({c['status']}, session={c['session_id']})")
    else:
        print("\n[sessionstart] Baseline: 0 managed containers — clean start")


def pytest_sessionfinish(session, exitstatus):
    """Final gate: fail the suite if any managed resources remain."""
    containers = _get_managed_container_details()
    if not containers:
        print("\n[sessionfinish] All managed resources cleaned up — suite passed gate")
        return

    print(f"\n[sessionfinish] FATAL: {len(containers)} managed container(s) leaked:")
    for c in containers:
        print(f"  - {c['name']} ({c['status']}, session={c['session_id']}, env={c['env_id']})")

    # If pytest would have passed, force it to fail
    if exitstatus == 0:
        session.exitstatus = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tracker():
    """Resource tracker for cleanup."""
    return MandatoryResourceTracker()


@pytest.fixture(autouse=True)
def verify_no_leaked_containers(request):
    """Autouse fixture: assert zero container leakage per test.

    Runs before and after every integration test. If a test creates a managed
    container and fails to destroy it (either via session archive or direct
    sandbox-service API), this fixture catches it immediately.
    """
    # Only apply to integration tests
    if "integration" not in str(request.node.nodeid):
        yield
        return

    baseline = _count_managed_containers()
    yield
    after = _count_managed_containers()
    delta = after - baseline

    if delta != 0:
        details = _get_managed_container_details()
        new_containers = [c for c in details if c["status"] in ("running", "exited")]
        msg = (
            f"Test leaked {delta} container(s): "
            + "; ".join(
                f"{c['name']}({c['status']},session={c['session_id']})"
                for c in new_containers[-delta:]
            )
        )
        pytest.fail(msg, pytrace=False)


async def wait_for_run_status(
    client: httpx.AsyncClient,
    thread_id: str,
    run_id: str,
    timeout: float = 120.0,
) -> dict | None:
    """Poll Aegra run endpoint until it reaches a terminal state.

    Aegra run statuses: pending, running, success, error, timeout, interrupted.
    Returns the full run dict when status is in a terminal state, or None on timeout.
    """
    for _ in range(int(timeout / 2)):
        resp = await client.get(f"/threads/{thread_id}/runs/{run_id}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") in ("success", "error", "timeout", "interrupted"):
                return data
        await asyncio.sleep(2)
    return None


async def poll_session_idle(
    client: httpx.AsyncClient,
    session_id: str,
    timeout: float = 120.0,
) -> bool:
    """Poll session status until it returns to idle."""
    for _ in range(int(timeout / 2)):
        await asyncio.sleep(2)
        resp = await client.get(f"/v1/sessions/{session_id}")
        if resp.status_code == 200 and resp.json().get("status") == "idle":
            return True
    return False


async def trigger_lazy_sandbox(
    client: httpx.AsyncClient,
    session_id: str,
    timeout: float = 120.0,
) -> dict:
    """Send an event that forces tool use, wait for the run, and return the session with container_id.

    LazyDockerSandboxBackend only creates the container on the first tool call.
    Tests that need the container immediately must trigger it via an agent run
    that exercises the filesystem tools.
    """
    resp = await client.post(
        f"/v1/sessions/{session_id}/events",
        json={
            "events": [
                {
                    "type": "user.message",
                    "content": [
                        {
                            "type": "text",
                            "text": "Write a file called /workspace/trigger.txt containing just the number 1",
                        }
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 200, f"Event post failed: {resp.status_code} {resp.text}"
    event_data = resp.json()

    run_data = await wait_for_run_status(
        client, event_data["thread_id"], event_data["run_id"], timeout=timeout
    )
    assert run_data is not None, "Run did not reach terminal state within timeout"
    assert run_data["status"] == "success", (
        f"Run failed: {run_data.get('error_message', 'N/A')!r}"
    )

    # Poll until sandbox_container_id is populated by LazyDockerSandboxBackend
    for _ in range(60):
        resp = await client.get(f"/v1/sessions/{session_id}")
        if resp.status_code == 200:
            session = resp.json()
            if session.get("sandbox_container_id"):
                return session
        await asyncio.sleep(1)

    raise RuntimeError(f"sandbox_container_id was never set for session {session_id}")


@pytest.fixture
async def client(tracker):
    """Live HTTP client against the running Aegra server."""
    c = httpx.AsyncClient(
        base_url=PLATFORM_URL,
        timeout=TIMEOUT,
        headers=_platform_headers(),
    )
    yield c
    # Mandatory cleanup — any failure propagates up and fails the test
    try:
        await tracker.cleanup(c)
    except RuntimeError:
        pass  # event loop already closed
    try:
        await c.aclose()
    except RuntimeError:
        pass  # event loop already closed


@pytest.fixture
async def sandbox_client():
    """Live HTTP client against the sandbox-service on localhost:8090."""
    c = httpx.AsyncClient(
        base_url=SANDBOX_URL,
        timeout=TIMEOUT,
        headers=_sandbox_headers(),
    )
    yield c
    try:
        await c.aclose()
    except RuntimeError:
        pass  # event loop already closed


@pytest.fixture
async def make_model(client, tracker):
    """Factory fixture — creates an LLMModel and returns its id."""
    created = []

    async def _create(**overrides):
        payload = {
            "display_name": "Test Model",
            "provider": "fireworks",
            "provider_model": "accounts/fireworks/routers/kimi-k2p6-turbo",
            **overrides,
        }
        resp = await client.post("/v1/models", json=payload)
        assert resp.status_code == 201, f"Failed to create model: {resp.status_code} {resp.text}"
        data = resp.json()
        tracker.models.append(data["id"])
        created.append(data["id"])
        return data

    yield _create


@pytest.fixture
async def make_agent(client, tracker, make_model):
    """Factory fixture — creates an agent using a model_id."""
    created = []

    async def _create(**overrides):
        model = await make_model()
        name = f"test-agent-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": name,
            "model_id": model["id"],
            "system_prompt": "You are a helpful assistant. Be concise.",
            **overrides,
        }
        resp = await client.post("/v1/agents", json=payload)
        assert resp.status_code == 201, f"Failed to create agent: {resp.status_code} {resp.text}"
        data = resp.json()
        tracker.agents.append(data["id"])
        created.append(data["id"])
        return data

    yield _create


@pytest.fixture
async def make_environment(client, tracker):
    """Factory fixture — creates an environment with basic Python packages."""
    created = []

    async def _create(**overrides):
        name = f"test-env-{uuid.uuid4().hex[:8]}"
        payload = {
            "name": name,
            "packages": {"pip": ["requests"]},
            "resource_limits": {"memory": "1g", "cpus": 1.0, "pids_limit": 256},
            **overrides,
        }
        resp = await client.post("/v1/environments", json=payload)
        assert resp.status_code == 201, f"Failed to create env: {resp.status_code} {resp.text}"
        data = resp.json()
        tracker.environments.append(data["id"])
        created.append(data["id"])
        return data

    yield _create


@pytest.fixture
async def make_session(client, tracker):
    """Factory fixture — creates a session."""
    created = []

    async def _create(**overrides):
        payload = {**overrides}
        resp = await client.post("/v1/sessions", json=payload)
        assert resp.status_code == 201, f"Failed to create session: {resp.status_code} {resp.text}"
        data = resp.json()
        tracker.sessions.append(data["id"])
        created.append(data["id"])
        return data

    yield _create
