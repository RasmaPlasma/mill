"""Tests for POST /internal/sessions/:id/status endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestStatusRoutes:
    @pytest.mark.asyncio
    async def test_update_session_status(self, client: AsyncClient):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "st", "model": "fireworks:test"}
        )
        agent_id = agent_resp.json()["id"]

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(
                return_value={"thread_id": "t1"}
            )
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions", json={"agent_id": agent_id}
            )

        session_id = session_resp.json()["id"]

        resp = await client.post(
            f"/internal/sessions/{session_id}/status",
            json={"status": "running"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        # Verify the session was updated
        resp = await client.get(f"/v1/sessions/{session_id}")
        assert resp.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_update_session_status_invalid(self, client: AsyncClient):
        agent_resp = await client.post(
            "/v1/agents", json={"name": "inv", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(
                return_value={"thread_id": "t2"}
            )
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

        session_id = session_resp.json()["id"]

        resp = await client.post(
            f"/internal/sessions/{session_id}/status",
            json={"status": "bogus"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_session_status_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/internal/sessions/sesn_01kr69p9haj0dgrts8q8z4bxq7/status",
            json={"status": "running"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_session_status_transitions(self, client: AsyncClient):
        """Verify status can transition: idle → running → idle."""
        agent_resp = await client.post(
            "/v1/agents", json={"name": "trans", "model": "fireworks:test"}
        )

        with patch("routes.sessions._get_aegra_client") as mock_get:
            mock_client = AsyncMock()
            mock_client.threads.create = AsyncMock(
                return_value={"thread_id": "t3"}
            )
            mock_get.return_value = mock_client

            session_resp = await client.post(
                "/v1/sessions",
                json={"agent_id": agent_resp.json()["id"]},
            )

        session_id = session_resp.json()["id"]
        assert session_resp.json()["status"] == "idle"

        # idle → running
        resp = await client.post(
            f"/internal/sessions/{session_id}/status",
            json={"status": "running"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        # running → idle
        resp = await client.post(
            f"/internal/sessions/{session_id}/status",
            json={"status": "idle"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"
