"""Tests for /v1/agents routes."""

import pytest
from httpx import AsyncClient


class TestAgentsRoutes:
    @pytest.fixture
    async def model_fixture(self, client: AsyncClient):
        """Helper to create a model and return its id."""
        resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Test Model",
                "provider": "fireworks",
                "provider_model": "test",
            },
        )
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_create_agent(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={
                "display_name": "Qwen",
                "provider": "fireworks",
                "provider_model": "accounts/fireworks/models/qwen3-235b-a22b",
            },
        )).json()["id"]

        resp = await client.post(
            "/v1/agents",
            json={
                "name": "test-agent",
                "model_id": model_id,
                "system_prompt": "You are helpful.",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-agent"
        assert data["model_id"] == model_id
        assert data["model"] == "Qwen"  # resolved display name
        assert data["version"] == 1
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_agent_missing_model_id(self, client: AsyncClient):
        resp = await client.post(
            "/v1/agents",
            json={"name": "no-model"},
        )
        assert resp.status_code == 201
        # Agent without model_id is allowed (legacy / optional)
        assert resp.json()["model_id"] is None

    @pytest.mark.asyncio
    async def test_create_agent_invalid_model_id(self, client: AsyncClient):
        resp = await client.post(
            "/v1/agents",
            json={"name": "bad", "model_id": "model_does_not_exist"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, client: AsyncClient):
        resp = await client.get("/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_agents_after_create(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        await client.post(
            "/v1/agents",
            json={"name": "a1", "model_id": model_id},
        )
        await client.post(
            "/v1/agents",
            json={"name": "a2", "model_id": model_id},
        )
        resp = await client.get("/v1/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_agent(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "get-me", "model_id": model_id},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.get(f"/v1/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-me"
        assert resp.json()["model"] == "T"

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, client: AsyncClient):
        resp = await client.get("/v1/agents/agent_01kr69p9haj0dgrts8q8z4bxq5")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_agent(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "original", "model_id": model_id},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/v1/agents/{agent_id}",
            json={"name": "updated", "system_prompt": "New prompt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "updated"
        assert data["system_prompt"] == "New prompt"
        assert data["version"] == 2

    @pytest.mark.asyncio
    async def test_update_agent_no_fields(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "noop", "model_id": model_id},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.patch(f"/v1/agents/{agent_id}", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_agent_null_list_fields_coerced(self, client: AsyncClient):
        """Setting tools to null should be coerced to empty list, not stored as null."""
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "coerce", "model_id": model_id, "tools": ["t1"]},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/v1/agents/{agent_id}",
            json={"tools": None},
        )
        assert resp.status_code == 200
        assert resp.json()["tools"] == []

    @pytest.mark.asyncio
    async def test_archive_agent(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "arch-me", "model_id": model_id},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.post(f"/v1/agents/{agent_id}/archive")
        assert resp.status_code == 204

        # Agent should no longer be visible
        resp = await client.get(f"/v1/agents/{agent_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_agents(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        ids = []
        for name in ("a1", "a2", "a3"):
            resp = await client.post("/v1/agents", json={"name": name, "model_id": model_id})
            ids.append(resp.json()["id"])

        resp = await client.post("/v1/agents/archive", json={"ids": ids})
        assert resp.status_code == 204

        for aid in ids:
            assert (await client.get(f"/v1/agents/{aid}")).status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_agents_empty_ids(self, client: AsyncClient):
        resp = await client.post("/v1/agents/archive", json={"ids": []})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_archive_agents_no_match(self, client: AsyncClient):
        resp = await client.post("/v1/agents/archive", json={"ids": ["agent_nonexistent"]})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archived_agent_not_in_list(self, client: AsyncClient):
        model_id = (await client.post(
            "/v1/models",
            json={"display_name": "T", "provider": "test", "provider_model": "t"},
        )).json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "hidden", "model_id": model_id},
        )
        agent_id = create_resp.json()["id"]
        await client.post(f"/v1/agents/{agent_id}/archive")

        resp = await client.get("/v1/agents")
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_legacy_agent_without_model_id(self, client: AsyncClient):
        """Agents created without model_id should still work (legacy)."""
        resp = await client.post(
            "/v1/agents",
            json={"name": "legacy-agent"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_id"] is None
        assert data["model"] is None

    @pytest.mark.asyncio
    async def test_agent_resolves_model_display_name(self, client: AsyncClient):
        model_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "GLM 5.1",
                "provider": "nvidia",
                "provider_model": "z-ai/glm-5.1",
            },
        )
        model_id = model_resp.json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "glm-agent", "model_id": model_id},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.get(f"/v1/agents/{agent_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_id"] == model_id
        assert data["model"] == "GLM 5.1"
