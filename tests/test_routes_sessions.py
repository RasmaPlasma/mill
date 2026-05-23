"""Tests for /v1/sessions routes.

All Aegra SDK calls are mocked since there's no running Aegra server in tests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from db.models import Session as SessionModel
from routes.sessions import _is_cma_event_type, _load_seen_ids, _synthesize_cma_events


def _unpack_synthesize(result):
    """Helper to unpack the 5-tuple return from _synthesize_cma_events."""
    return result[0], result[1], result[2], result[3], result[4]


def _mock_thread():
    return {"thread_id": "thread-abc123"}


def _mock_run():
    return {"run_id": "run-xyz789"}


class TestSessionsRoutes:
    @pytest.mark.asyncio
    async def test_create_session(self, client: AsyncClient):
        agent_resp = await client.post(
            "/v1/agents",
            json={"name": "sa", "model": "fireworks:test"},
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_id},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == agent_id
        assert data["aegra_thread_id"] == "thread-abc123"
        assert data["status"] == "idle"

    @pytest.mark.asyncio
    async def test_create_session_no_agent(self, client: AsyncClient):
        """Session can be created without an agent."""
        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            resp = await client.post("/v1/sessions", json={})

        assert resp.status_code == 201
        assert resp.json()["agent_id"] is None

    @pytest.mark.asyncio
    async def test_create_session_invalid_agent(self, client: AsyncClient):
        resp = await client.post(
            "/v1/sessions",
            json={"agent_id": "agent_01kr69p9haj0dgrts8q8z4bxq5"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_session_invalid_vault(self, client: AsyncClient):
        resp = await client.post(
            "/v1/sessions",
            json={"vault_ids": ["vlt_01kr69p9haj0dgrts8q8z4bxq8"]},
        )
        assert resp.status_code == 400
        assert "Vaults not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_session_with_environment(self, client: AsyncClient):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "a", "model": "fireworks:test"}
        )
        env_resp = await client.post(
            "/v1/environments", json={"name": "env-sess"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            resp = await client.post(
                "/v1/sessions",
                json={
                    "agent_id": agent_resp.json()["id"],
                    "environment_id": env_resp.json()["id"],
                },
            )

        assert resp.status_code == 201
        assert resp.json()["environment_id"] == env_resp.json()["id"]
        # Lazy backend: container is NOT created at session creation time
        assert resp.json()["sandbox_container_id"] is None

    @pytest.mark.asyncio
    async def test_create_session_aegra_failure_marks_failed(self, client: AsyncClient):
        """If Aegra thread creation fails, session persists with status='failed'."""
        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(side_effect=Exception("connection refused"))
            mock_get.return_value = mock_client

            resp = await client.post("/v1/sessions", json={})

        assert resp.status_code == 503

        # Verify the session record persisted with status="failed"
        session_id = resp.headers.get("X-Session-Id")
        assert session_id is not None, "503 response must include X-Session-Id header"

        get_resp = await client.get(f"/v1/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "failed"
        assert get_resp.json()["aegra_thread_id"] is None

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client: AsyncClient):
        resp = await client.get("/v1/sessions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_get_session(self, client: AsyncClient):
        """Happy-path: create a session then retrieve it."""
        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            create_resp = await client.post("/v1/sessions", json={})

        session_id = create_resp.json()["id"]
        resp = await client.get(f"/v1/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == session_id
        assert resp.json()["aegra_thread_id"] == "thread-abc123"

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client: AsyncClient):
        resp = await client.get("/v1/sessions/sesn_01kr69p9haj0dgrts8q8z4bxq7")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_events(self, client: AsyncClient, llm_model):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "evt", "model_id": llm_model["id"]}
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_id}
            )

            session_id = session_resp.json()["id"]
            mock_client.runs.create = AsyncMock(return_value=_mock_run())

            resp = await client.post(
                f"/v1/sessions/{session_id}/events",
                json={
                    "events": [
                        {
                            "type": "user.message",
                            "content": [{"type": "text", "text": "Hello"}],
                        }
                    ]
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "run-xyz789"
        assert data["thread_id"] == "thread-abc123"

    @pytest.mark.asyncio
    async def test_send_events_multiple(self, client: AsyncClient, llm_model):
        """Multiple events in one request."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "multi", "model_id": llm_model["id"]}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_resp.json()["id"]}
            )

            mock_client.runs.create = AsyncMock(return_value=_mock_run())
            resp = await client.post(
                f"/v1/sessions/{session_resp.json()['id']}/events",
                json={
                    "events": [
                        {"type": "user.message", "content": [{"type": "text", "text": "First"}]},
                        {"type": "user.message", "content": [{"type": "text", "text": "Second"}]},
                    ]
                },
            )

        assert resp.status_code == 200
        # Verify the input had two messages
        call_kwargs = mock_client.runs.create.call_args
        messages = call_kwargs.kwargs["input"]["messages"]
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_send_events_no_agent(self, client: AsyncClient):
        """Session without agent_id should return 400."""
        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post("/v1/sessions", json={})

        resp = await client.post(
            f"/v1/sessions/{session_resp.json()['id']}/events",
            json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "Hi"}]}]},
        )
        assert resp.status_code == 400
        assert "no agent configured" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_send_events_no_thread(self, client: AsyncClient, session):
        """Session without aegra_thread_id returns 400."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "nt", "model": "fireworks:test"}
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_id}
            )

        session_id = session_resp.json()["id"]

        # Manually clear the thread_id via the shared test session
        row = await session.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        s = row.scalar_one()
        s.aegra_thread_id = None
        await session.flush()

        resp = await client.post(
            f"/v1/sessions/{session_id}/events",
            json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "Hi"}]}]},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_archive_session(self, client: AsyncClient):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "arch", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

            session_id = session_resp.json()["id"]
            mock_client.threads.delete = AsyncMock(return_value=None)

            resp = await client.post(f"/v1/sessions/{session_id}/archive")

        assert resp.status_code == 204

        # Session should be archived
        resp = await client.get(f"/v1/sessions/{session_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_sessions(self, client: AsyncClient):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "bulk-arch", "model": "fireworks:test"}
        )
        agent_id = agent_resp.json()["id"]

        ids = []
        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            for _ in range(3):
                session_resp = await client.post(
                    "/v1/sessions", json={"agent_id": agent_id}
                )
                ids.append(session_resp.json()["id"])

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.delete = AsyncMock(return_value=None)
            mock_get.return_value = mock_client

            resp = await client.post("/v1/sessions/archive", json={"ids": ids})

        assert resp.status_code == 200
        data = resp.json()
        assert sorted(data["archived"]) == sorted(ids)
        assert data["failed"] == []

        for sid in ids:
            assert (await client.get(f"/v1/sessions/{sid}")).status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_sessions_empty_ids(self, client: AsyncClient):
        resp = await client.post("/v1/sessions/archive", json={"ids": []})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_archive_sessions_partial(self, client: AsyncClient):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "partial", "model": "fireworks:test"}
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_id}
            )
            real_id = session_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.delete = AsyncMock(return_value=None)
            mock_get.return_value = mock_client

            resp = await client.post(
                "/v1/sessions/archive",
                json={"ids": [real_id, "session_nonexistent"]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["archived"] == [real_id]
        assert data["failed"] == ["session_nonexistent"]

    @pytest.mark.asyncio
    async def test_stream_creates_new_run(self, client: AsyncClient):
        """Without run_id, stream creates a new run."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "stream", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

            session_id = session_resp.json()["id"]

            # Mock the stream as an async iterator
            async def mock_stream(**kwargs):
                yield type("Chunk", (), {"event": "messages", "data": {"content": "hi"}})()

            mock_client.runs.stream = mock_stream

            resp = await client.get(f"/v1/sessions/{session_id}/stream")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_stream_with_run_id_joins(self, client: AsyncClient):
        """With run_id, stream joins existing run via join_stream."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "join", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

            session_id = session_resp.json()["id"]

            collected_chunks = []

            async def mock_join_stream(**kwargs):
                collected_chunks.append(kwargs)
                yield type("Chunk", (), {"event": "messages", "data": {"content": "joined"}})()

            mock_client.runs.join_stream = mock_join_stream

            resp = await client.get(f"/v1/sessions/{session_id}/stream?run_id=run-123")

        assert resp.status_code == 200
        assert len(collected_chunks) == 1
        assert collected_chunks[0]["run_id"] == "run-123"

    @pytest.mark.asyncio
    async def test_stream_forwards_last_event_id(self, client: AsyncClient):
        """Last-Event-ID header is forwarded to join_stream."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "lei", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

            session_id = session_resp.json()["id"]

            collected_chunks = []

            async def mock_join_stream(**kwargs):
                collected_chunks.append(kwargs)
                yield type("Chunk", (), {"event": "messages", "data": {}})()

            mock_client.runs.join_stream = mock_join_stream

            resp = await client.get(
                f"/v1/sessions/{session_id}/stream?run_id=run-123",
                headers={"Last-Event-id": "evt-42"},
            )

        assert resp.status_code == 200
        assert len(collected_chunks) == 1
        assert collected_chunks[0]["last_event_id"] == "evt-42"

    @pytest.mark.asyncio
    async def test_stream_error_masked(self, client: AsyncClient):
        """Internal errors are masked — client gets generic message."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "err", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

            session_id = session_resp.json()["id"]

            async def failing_stream(**kwargs):
                raise RuntimeError("internal connection string: postgres://secret@host/db")
                yield  # make it a generator

            mock_client.runs.stream = failing_stream

            resp = await client.get(f"/v1/sessions/{session_id}/stream")

        assert resp.status_code == 200
        body = resp.text
        assert "postgres://secret" not in body
        assert "Stream error occurred" in body

    @pytest.mark.asyncio
    async def test_send_events_concurrent_rejected(self, client: AsyncClient):
        """Sending events to a non-idle session returns 409."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "conc", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

        session_id = session_resp.json()["id"]

        # Set session to "running" via status endpoint
        resp = await client.post(
            f"/internal/sessions/{session_id}/status",
            json={"status": "running"},
        )
        assert resp.status_code == 200

        # Sending events to a running session should be rejected
        resp = await client.post(
            f"/v1/sessions/{session_id}/events",
            json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "Hi"}]}]},
        )
        assert resp.status_code == 409
        assert "not idle" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_send_events_passes_multitask_strategy(self, client: AsyncClient, llm_model):
        """send_events passes multitask_strategy='reject' to Aegra."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "mt", "model_id": llm_model["id"]}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

            session_id = session_resp.json()["id"]
            mock_client.runs.create = AsyncMock(return_value=_mock_run())

            await client.post(
                f"/v1/sessions/{session_id}/events",
                json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "Hi"}]}]},
            )

            call_kwargs = mock_client.runs.create.call_args.kwargs
            assert call_kwargs["multitask_strategy"] == "reject"

    @pytest.mark.asyncio
    async def test_send_events_archived_vault_excluded(self, client: AsyncClient, llm_model):
        """Credentials from archived vaults are excluded from context."""
        # Create agent, vault, credential, session
        agent_resp = await client.post(
            "/v1/agents", json={"name": "av", "model_id": llm_model["id"]}
        )
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "will-archive"}
        )
        vault_id = vault_resp.json()["id"]
        await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "cred",
                "mcp_server_url": "http://mcp.example.com",
                "auth_type": "static_bearer",
                "token": "tok",
            },
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={
                    "agent_id": agent_resp.json()["id"],
                    "vault_ids": [vault_id],
                },
            )

        session_id = session_resp.json()["id"]

        # Archive the vault
        await client.post(f"/v1/vaults/{vault_id}/archive")

        # Send events — credentials from archived vault should be excluded
        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.runs.create = AsyncMock(return_value=_mock_run())
            mock_get.return_value = mock_client

            resp = await client.post(
                f"/v1/sessions/{session_id}/events",
                json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "Hi"}]}]},
            )

        assert resp.status_code == 200
        call_kwargs = mock_client.runs.create.call_args.kwargs
        context = call_kwargs["context"]
        assert context["vault_credentials"] == {}

    @pytest.mark.asyncio
    async def test_stream_run_not_found(self, client: AsyncClient):
        """Stream with invalid run_id returns useful error via SSE."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "rnf", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

            session_id = session_resp.json()["id"]

            class NotFoundError(Exception):
                status_code = 404

            async def failing_join(**kwargs):
                raise NotFoundError("run not found")
                yield

            mock_client.runs.join_stream = failing_join

            resp = await client.get(f"/v1/sessions/{session_id}/stream?run_id=bogus")

        assert resp.status_code == 200
        body = resp.text
        assert "Run not found" in body

    @pytest.mark.asyncio
    async def test_create_session_stores_override_repos_and_skills(self, client: AsyncClient):
        """Session can store per-run repository and skill overrides."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "override", "model": "fireworks:test"}
        )
        env_resp = await client.post(
            "/v1/environments", json={"name": "env-override"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            resp = await client.post(
                "/v1/sessions",
                json={
                    "agent_id": agent_resp.json()["id"],
                    "environment_id": env_resp.json()["id"],
                    "repositories": [{"url": "https://github.com/user/repo", "branch": "main"}],
                    "skill_repos": [{"repo": "anthropic/skills", "skill_name": "*"}],
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["repositories"] == [{"url": "https://github.com/user/repo", "branch": "main"}]
        assert data["skill_repos"] == [{"repo": "anthropic/skills", "skill_name": "*"}]

    @pytest.mark.asyncio
    async def test_create_session_merges_override_with_env(self, client: AsyncClient):
        """Session repos and skill_repos are additively merged with environment defaults."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "merge", "model": "fireworks:test"}
        )
        # Environment with baseline repos and skills
        env_resp = await client.post(
            "/v1/environments",
            json={
                "name": "env-merge",
                "repositories": [{"url": "https://github.com/env/base", "branch": "main"}],
                "skill_repos": [{"repo": "env/skills", "skill_name": "*"}],
            },
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            resp = await client.post(
                "/v1/sessions",
                json={
                    "agent_id": agent_resp.json()["id"],
                    "environment_id": env_resp.json()["id"],
                    "repositories": [{"url": "https://github.com/session/extra", "branch": "dev"}],
                    "skill_repos": [{"repo": "session/skills", "skill_name": "web-fetch"}],
                },
            )

        assert resp.status_code == 201
        # Verify merged lists are in the session response
        data = resp.json()
        assert data["repositories"] == [{"url": "https://github.com/session/extra", "branch": "dev"}]
        assert data["skill_repos"] == [{"repo": "session/skills", "skill_name": "web-fetch"}]

    @pytest.mark.asyncio
    async def test_send_events_skills_path_from_session_overrides_alone(self, client: AsyncClient, llm_model):
        """Skills path is injected when session provides skill_repos, even if env has none."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "skills-override", "model_id": llm_model["id"]}
        )
        # Environment with no skill_repos
        env_resp = await client.post(
            "/v1/environments", json={"name": "env-no-skills"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={
                    "agent_id": agent_resp.json()["id"],
                    "environment_id": env_resp.json()["id"],
                    "skill_repos": [{"repo": "anthropic/skills", "skill_name": "*"}],
                },
            )

        session_id = session_resp.json()["id"]

        # Verify _resolve_context injects skills path from session override
        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.runs.create = AsyncMock(return_value=_mock_run())
            mock_get.return_value = mock_client

            resp = await client.post(
                f"/v1/sessions/{session_id}/events",
                json={"events": [{"type": "user.message", "content": [{"type": "text", "text": "Hi"}]}]},
            )

        assert resp.status_code == 200
        context = mock_client.runs.create.call_args.kwargs["context"]
        assert "/workspace/.agents/skills/" in context["agent"]["skills"]


class TestCMAEventSynthesis:
    """Tests for CMA event transformation from raw LangGraph events."""

    def test_is_cma_event_type(self):
        assert _is_cma_event_type("user.message") is True
        assert _is_cma_event_type("agent.message") is True
        assert _is_cma_event_type("session.status_idle") is True
        assert _is_cma_event_type("span.model_request_end") is True
        assert _is_cma_event_type("values") is False
        assert _is_cma_event_type("on_tool_start") is False
        assert _is_cma_event_type("metadata") is False
        assert _is_cma_event_type("end") is False

    def test_synthesize_values_to_agent_message(self):
        raw = {
            "messages": [
                {
                    "type": "ai",
                    "content": "Hello there",
                    "id": "msg-1",
                }
            ]
        }
        events, seen, _, _, usage = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events) == 1
        assert events[0]["event_type"] == "agent.message"
        assert events[0]["payload"]["message_id"] == "msg-1"
        assert events[0]["payload"]["content"] == "Hello there"

    def test_synthesize_values_to_agent_thinking_and_message(self):
        raw = {
            "messages": [
                {
                    "type": "ai",
                    "content": "Result",
                    "id": "msg-2",
                    "additional_kwargs": {"reasoning_content": "Let me think..."},
                }
            ]
        }
        events, seen, _, _, usage = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events) == 2
        assert events[0]["event_type"] == "agent.thinking"
        assert events[0]["payload"]["message_id"] == "msg-2"
        assert events[0]["payload"]["content"] == "Let me think..."
        assert events[1]["event_type"] == "agent.message"
        assert events[1]["payload"]["message_id"] == "msg-2"

    def test_synthesize_values_dedupes_ai_messages(self):
        raw = {
            "messages": [
                {"type": "ai", "content": "Hello", "id": "msg-3"}
            ]
        }
        events1, seen1, _, _, _ = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events1) == 1
        events2, seen2, _, _, _ = _synthesize_cma_events("values", raw, "run-1", "evt-2", seen1, set(), set(), False)
        assert len(events2) == 0  # deduped
        assert "msg-3" in seen2

    def test_synthesize_values_dedupes_with_preseeded_seen(self):
        """Simulates a second run where the first run's message is already in DB."""
        raw = {
            "messages": [
                {"type": "ai", "content": "Hello", "id": "msg-prev"}
            ]
        }
        # Pre-seed seen_msg_ids as if loaded from DB (cross-run dedup)
        preseeded = {"msg-prev"}
        events, seen, _, _, _ = _synthesize_cma_events("values", raw, "run-2", "evt-1", preseeded, set(), set(), False)
        assert len(events) == 0  # skipped because msg-prev was already seen
        assert "msg-prev" in seen

    @pytest.mark.asyncio
    async def test_load_seen_ids_from_db(self, client: AsyncClient):
        from db.engine import get_session_factory
        from db.models import Event

        session_factory = get_session_factory()
        async with session_factory() as db:
            # Create a dummy session first
            from db.models import Session as SessionModel
            session = SessionModel(status="idle")
            db.add(session)
            await db.commit()
            session_id = session.id

            # Add existing agent.message, agent.thinking, and tool events
            db.add_all([
                Event(session_id=session_id, run_id="run-1", event_type="agent.message", payload={"message_id": "msg-a", "content": "hi"}),
                Event(session_id=session_id, run_id="run-1", event_type="agent.thinking", payload={"message_id": "msg-b", "content": "think"}),
                Event(session_id=session_id, run_id="run-1", event_type="user.message", payload={"message_id": "msg-c", "content": "yo"}),
                Event(session_id=session_id, run_id="run-1", event_type="agent.tool_use", payload={"tool_use_id": "tool-a", "tool_name": "bash", "input": {}}),
                Event(session_id=session_id, run_id="run-1", event_type="agent.tool_result", payload={"tool_use_id": "tool-b", "tool_name": "bash", "output": "ok"}),
            ])
            await db.commit()

        seen_msgs, seen_tool_use, seen_tool_result = await _load_seen_ids(session_id)
        assert seen_msgs == {"msg-a", "msg-b"}
        assert seen_tool_use == {"tool-a"}
        assert seen_tool_result == {"tool-b"}

    def test_synthesize_values_emits_usage_once(self):
        raw = {
            "messages": [{"type": "ai", "content": "Hi", "id": "msg-4"}],
            "usage_metadata": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }
        events1, _, _, _, usage1 = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert any(e["event_type"] == "span.model_request_end" for e in events1)
        assert usage1 is True
        events2, _, _, _, usage2 = _synthesize_cma_events("values", raw, "run-1", "evt-2", set(), set(), set(), True)
        assert not any(e["event_type"] == "span.model_request_end" for e in events2)

    def test_synthesize_tool_start(self):
        raw = {"name": "bash", "args": {"command": "ls"}, "id": "tool-1"}
        events, _, _, _, _ = _synthesize_cma_events("on_tool_start", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events) == 1
        assert events[0]["event_type"] == "agent.tool_use"
        assert events[0]["payload"]["tool_name"] == "bash"
        assert events[0]["payload"]["tool_use_id"] == "tool-1"

    def test_synthesize_tool_end(self):
        raw = {"name": "bash", "output": "file.txt", "id": "tool-1"}
        events, _, _, _, _ = _synthesize_cma_events("on_tool_end", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events) == 1
        assert events[0]["event_type"] == "agent.tool_result"
        assert events[0]["payload"]["tool_name"] == "bash"
        assert events[0]["payload"]["output"] == "file.txt"

    def test_synthesize_error(self):
        raw = {"error": "Something broke", "detail": "stack trace"}
        events, _, _, _, _ = _synthesize_cma_events("error", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events) == 1
        assert events[0]["event_type"] == "session.error"
        assert events[0]["payload"]["error"]["type"] == "run_error"
        assert events[0]["payload"]["error"]["retry_status"] == "fatal"

    def test_synthesize_end(self):
        raw = {"status": "ok"}
        events, _, _, _, _ = _synthesize_cma_events("end", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events) == 1
        assert events[0]["event_type"] == "session.status_idle"
        assert events[0]["payload"]["stop_reason"] == "completed"

    def test_synthesize_metadata_returns_empty(self):
        raw = {"attempt": 1}
        events, _, _, _, _ = _synthesize_cma_events("metadata", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events) == 0

    def test_synthesize_values_tool_calls_to_agent_tool_use(self):
        raw = {
            "messages": [
                {
                    "type": "ai",
                    "content": "",
                    "id": "msg-tc",
                    "tool_calls": [
                        {"id": "call-1", "name": "write_file", "args": {"path": "/tmp/test.py"}}
                    ]
                }
            ]
        }
        events, _, tools, _, _ = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert any(e["event_type"] == "agent.tool_use" for e in events)
        tool_event = [e for e in events if e["event_type"] == "agent.tool_use"][0]
        assert tool_event["payload"]["tool_use_id"] == "call-1"
        assert tool_event["payload"]["tool_name"] == "write_file"
        assert tool_event["payload"]["input"]["path"] == "/tmp/test.py"
        assert "call-1" in tools

    def test_synthesize_values_tool_message_to_agent_tool_result(self):
        raw = {
            "messages": [
                {
                    "type": "tool",
                    "tool_call_id": "call-1",
                    "name": "write_file",
                    "content": "success",
                }
            ]
        }
        events, _, _, tool_result, _ = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert any(e["event_type"] == "agent.tool_result" for e in events)
        res_event = [e for e in events if e["event_type"] == "agent.tool_result"][0]
        assert res_event["payload"]["tool_use_id"] == "call-1"
        assert res_event["payload"]["tool_name"] == "write_file"
        assert res_event["payload"]["output"] == "success"
        assert "call-1" in tool_result

    def test_synthesize_values_tool_calls_deduped(self):
        raw = {
            "messages": [
                {
                    "type": "ai",
                    "content": "",
                    "id": "msg-dup",
                    "tool_calls": [
                        {"id": "call-dup", "name": "bash", "args": {"command": "ls"}}
                    ]
                }
            ]
        }
        events1, _, tools1, _, _ = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        assert len([e for e in events1 if e["event_type"] == "agent.tool_use"]) == 1
        events2, _, tools2, _, _ = _synthesize_cma_events("values", raw, "run-1", "evt-2", set(), tools1, set(), False)
        assert len([e for e in events2 if e["event_type"] == "agent.tool_use"]) == 0  # deduped
        assert "call-dup" in tools2

    def test_synthesize_values_tool_calls_on_already_seen_ai_message(self):
        """LangGraph emits full state on every step. An AI message may be seen first
        without tool_calls, then reappear in a later values event with tool_calls added.
        The tool_calls must still be extracted even though the AI message is already seen."""
        raw1 = {
            "messages": [
                {"type": "ai", "content": "I'll help", "id": "msg-tc-later"}
            ]
        }
        events1, seen1, tools1, _, _ = _synthesize_cma_events("values", raw1, "run-1", "evt-1", set(), set(), set(), False)
        assert len(events1) == 1  # only agent.message
        assert events1[0]["event_type"] == "agent.message"
        assert "msg-tc-later" in seen1
        assert tools1 == set()

        # Second values event: same AI message now has tool_calls
        raw2 = {
            "messages": [
                {
                    "type": "ai",
                    "content": "I'll help",
                    "id": "msg-tc-later",
                    "tool_calls": [
                        {"id": "call-later", "name": "write_file", "args": {"path": "/tmp/x"}}
                    ]
                }
            ]
        }
        events2, seen2, tools2, _, _ = _synthesize_cma_events("values", raw2, "run-1", "evt-2", seen1, tools1, set(), False)
        assert len([e for e in events2 if e["event_type"] == "agent.message"]) == 0  # deduped
        assert len([e for e in events2 if e["event_type"] == "agent.tool_use"]) == 1  # NEW: extracted even though AI msg was seen
        tool_event = [e for e in events2 if e["event_type"] == "agent.tool_use"][0]
        assert tool_event["payload"]["tool_use_id"] == "call-later"
        assert tool_event["payload"]["tool_name"] == "write_file"
        assert "call-later" in tools2

    def test_synthesize_values_tool_call_and_result_same_id(self):
        """Regression: a single values event may contain both the AI message with
        tool_calls AND the ToolMessage result. The same tool_call_id must produce
        BOTH an agent.tool_use AND an agent.tool_result event.
        """
        raw = {
            "messages": [
                {
                    "type": "ai",
                    "content": "",
                    "id": "msg-both",
                    "tool_calls": [
                        {"id": "call-both", "name": "bash", "args": {"command": "ls"}}
                    ]
                },
                {
                    "type": "tool",
                    "tool_call_id": "call-both",
                    "name": "bash",
                    "content": "file.txt\n",
                }
            ]
        }
        events, _, tool_use, tool_result, _ = _synthesize_cma_events("values", raw, "run-1", "evt-1", set(), set(), set(), False)
        tool_use_events = [e for e in events if e["event_type"] == "agent.tool_use"]
        tool_result_events = [e for e in events if e["event_type"] == "agent.tool_result"]
        assert len(tool_use_events) == 1
        assert len(tool_result_events) == 1
        assert tool_use_events[0]["payload"]["tool_use_id"] == "call-both"
        assert tool_result_events[0]["payload"]["tool_use_id"] == "call-both"
        assert tool_result_events[0]["payload"]["output"] == "file.txt\n"
        assert "call-both" in tool_use
        assert "call-both" in tool_result


class TestInterruptEndpoint:
    """Tests for POST /v1/sessions/:id/interrupt."""

    @pytest.mark.asyncio
    async def test_interrupt_running_session(self, client: AsyncClient, llm_model):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "int", "model_id": llm_model["id"]}
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_client.runs.list = AsyncMock(return_value=[
                {"run_id": "run-123", "status": "running"}
            ])
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_id}
            )
            session_id = session_resp.json()["id"]

            # Set session to running
            await client.post(
                f"/internal/sessions/{session_id}/status",
                json={"status": "running"},
            )

            resp = await client.post(f"/v1/sessions/{session_id}/interrupt")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "interrupted"
        assert data["stop_reason"] == "interrupted"

        # Verify cancel was called
        mock_client.runs.cancel.assert_called_once_with(
            thread_id="thread-abc123",
            run_id="run-123",
        )

        # Verify session is now idle
        get_resp = await client.get(f"/v1/sessions/{session_id}")
        assert get_resp.json()["status"] == "idle"
        assert get_resp.json()["stop_reason"] == "interrupted"

    @pytest.mark.asyncio
    async def test_interrupt_non_running_returns_409(self, client: AsyncClient, llm_model):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "int2", "model_id": llm_model["id"]}
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_id}
            )
            session_id = session_resp.json()["id"]

            # Session is idle by default
            resp = await client.post(f"/v1/sessions/{session_id}/interrupt")

        assert resp.status_code == 409
        assert "not running" in resp.json()["detail"].lower()


class TestStatusWithStopReason:
    """Tests for internal status callback with stop_reason."""

    @pytest.mark.asyncio
    async def test_status_update_with_stop_reason(self, client: AsyncClient, llm_model):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "sr", "model_id": llm_model["id"]}
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(return_value=_mock_thread())
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_id}
            )
            session_id = session_resp.json()["id"]

        resp = await client.post(
            f"/internal/sessions/{session_id}/status",
            json={"status": "idle", "stop_reason": "completed"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"
        assert resp.json()["stop_reason"] == "completed"

        get_resp = await client.get(f"/v1/sessions/{session_id}")
        assert get_resp.json()["stop_reason"] == "completed"
