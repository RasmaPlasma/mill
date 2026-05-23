"""Tests for /v1/models routes (LLM Model Registry)."""

import pytest
from httpx import AsyncClient


class TestModelsRoutes:
    @pytest.mark.asyncio
    async def test_create_model(self, client: AsyncClient):
        resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Kimi K2.6 Turbo",
                "provider": "fireworks",
                "provider_model": "accounts/fireworks/routers/kimi-k2p6-turbo",
                "description": "Fireworks-hosted Kimi",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "Kimi K2.6 Turbo"
        assert data["provider"] == "fireworks"
        assert data["provider_model"] == "accounts/fireworks/routers/kimi-k2p6-turbo"
        assert data["description"] == "Fireworks-hosted Kimi"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_model_missing_fields(self, client: AsyncClient):
        resp = await client.post("/v1/models", json={"display_name": "x"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_models_empty(self, client: AsyncClient):
        resp = await client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_models_after_create(self, client: AsyncClient):
        await client.post(
            "/v1/models",
            json={
                "display_name": "GLM 5.1",
                "provider": "nvidia",
                "provider_model": "z-ai/glm-5.1",
            },
        )
        await client.post(
            "/v1/models",
            json={
                "display_name": "GPT-4o",
                "provider": "openai",
                "provider_model": "gpt-4o",
            },
        )
        resp = await client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_model(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Test Model",
                "provider": "test",
                "provider_model": "test-model",
            },
        )
        model_id = create_resp.json()["id"]

        resp = await client.get(f"/v1/models/{model_id}")
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Test Model"

    @pytest.mark.asyncio
    async def test_get_model_not_found(self, client: AsyncClient):
        resp = await client.get("/v1/models/model_01kr69p9haj0dgrts8q8z4bxq5")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_model(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Old Name",
                "provider": "test",
                "provider_model": "old",
            },
        )
        model_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/v1/models/{model_id}",
            json={"display_name": "New Name", "provider_model": "new"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "New Name"
        assert data["provider_model"] == "new"
        assert data["provider"] == "test"  # unchanged

    @pytest.mark.asyncio
    async def test_update_model_no_fields(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "x",
                "provider": "test",
                "provider_model": "x",
            },
        )
        model_id = create_resp.json()["id"]

        resp = await client.patch(f"/v1/models/{model_id}", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_archive_model(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "archive-me",
                "provider": "test",
                "provider_model": "test",
            },
        )
        model_id = create_resp.json()["id"]

        resp = await client.post(f"/v1/models/{model_id}/archive")
        assert resp.status_code == 204

        resp = await client.get(f"/v1/models/{model_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_models(self, client: AsyncClient):
        ids = []
        for name in ("m1", "m2", "m3"):
            resp = await client.post(
                "/v1/models",
                json={"display_name": name, "provider": "test", "provider_model": name},
            )
            ids.append(resp.json()["id"])

        resp = await client.post("/v1/models/archive", json={"ids": ids})
        assert resp.status_code == 204

        for mid in ids:
            assert (await client.get(f"/v1/models/{mid}")).status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_models_empty_ids(self, client: AsyncClient):
        resp = await client.post("/v1/models/archive", json={"ids": []})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_archive_models_no_match(self, client: AsyncClient):
        resp = await client.post("/v1/models/archive", json={"ids": ["model_nonexistent"]})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archived_model_not_in_list(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "hidden",
                "provider": "test",
                "provider_model": "test",
            },
        )
        model_id = create_resp.json()["id"]
        await client.post(f"/v1/models/{model_id}/archive")

        resp = await client.get("/v1/models")
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_create_agent_with_model_id(self, client: AsyncClient):
        """Agents can reference a model from the registry via model_id."""
        model_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "GLM 5.1",
                "provider": "nvidia",
                "provider_model": "z-ai/glm-5.1",
            },
        )
        model_id = model_resp.json()["id"]

        resp = await client.post(
            "/v1/agents",
            json={"name": "agent-with-model", "model_id": model_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model_id"] == model_id
        assert data["model"] == "GLM 5.1"  # resolved display name

    @pytest.mark.asyncio
    async def test_create_agent_invalid_model_id(self, client: AsyncClient):
        resp = await client.post(
            "/v1/agents",
            json={"name": "bad-model", "model_id": "model_does_not_exist"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_agent_archived_model_id(self, client: AsyncClient):
        model_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Archived",
                "provider": "test",
                "provider_model": "test",
            },
        )
        model_id = model_resp.json()["id"]
        await client.post(f"/v1/models/{model_id}/archive")

        resp = await client.post(
            "/v1/agents",
            json={"name": "bad-model", "model_id": model_id},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_agents_resolves_model_name(self, client: AsyncClient):
        model_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Kimi K2.6",
                "provider": "fireworks",
                "provider_model": "accounts/fireworks/routers/kimi-k2p6-turbo",
            },
        )
        model_id = model_resp.json()["id"]

        await client.post(
            "/v1/agents",
            json={"name": "kimi-agent", "model_id": model_id},
        )

        resp = await client.get("/v1/agents")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["model_id"] == model_id
        assert items[0]["model"] == "Kimi K2.6"

    @pytest.mark.asyncio
    async def test_update_agent_model_id(self, client: AsyncClient):
        model_resp = await client.post(
            "/v1/models",
            json={
                "display_name": "Model A",
                "provider": "test",
                "provider_model": "a",
            },
        )
        model_a = model_resp.json()["id"]

        create_resp = await client.post(
            "/v1/agents",
            json={"name": "switcher", "model_id": model_a},
        )
        agent_id = create_resp.json()["id"]

        model_resp_b = await client.post(
            "/v1/models",
            json={
                "display_name": "Model B",
                "provider": "test",
                "provider_model": "b",
            },
        )
        model_b = model_resp_b.json()["id"]

        resp = await client.patch(
            f"/v1/agents/{agent_id}",
            json={"model_id": model_b},
        )
        assert resp.status_code == 200
        assert resp.json()["model_id"] == model_b
        assert resp.json()["model"] == "Model B"
