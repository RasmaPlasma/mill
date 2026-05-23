"""Integration tests — agent CRUD against real PostgreSQL.

No mocks. Hits the live Aegra server on localhost:2026.
"""

import uuid

import httpx
import pytest


@pytest.mark.integration
class TestAgentLifecycle:
    async def test_create_agent_with_model(self, client, make_agent):
        agent = await make_agent()
        assert agent["id"]
        assert agent["model"] == "Test Model"
        assert agent["model_id"]
        assert agent["version"] == 1
        assert agent["archived_at"] is None

    async def test_get_agent(self, client, make_agent):
        agent = await make_agent()
        resp = await client.get(f"/v1/agents/{agent['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == agent["id"]
        assert data["model"] == agent["model"]

    async def test_list_agents_includes_created(self, client, make_agent):
        agent = await make_agent()
        resp = await client.get("/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        ids = [a["id"] for a in data["items"]]
        assert agent["id"] in ids

    async def test_update_agent_increments_version(self, client, make_agent):
        agent = await make_agent()
        assert agent["version"] == 1

        resp = await client.patch(
            f"/v1/agents/{agent['id']}",
            json={"system_prompt": "Updated prompt."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        assert data["system_prompt"] == "Updated prompt."

    async def test_archive_agent(self, client, make_agent):
        agent = await make_agent()
        resp = await client.post(f"/v1/agents/{agent['id']}/archive")
        assert resp.status_code == 204

        resp = await client.get(f"/v1/agents/{agent['id']}")
        assert resp.status_code == 404

    async def test_create_agent_missing_model_id_succeeds(self, client):
        resp = await client.post(
            "/v1/agents",
            json={"name": "no-model-agent"},
        )
        assert resp.status_code == 201
        assert resp.json()["model_id"] is None

    async def test_create_agent_invalid_model_id_returns_400(self, client):
        resp = await client.post(
            "/v1/agents",
            json={"name": "bad-model", "model_id": "model_nonexistent"},
        )
        assert resp.status_code == 400
