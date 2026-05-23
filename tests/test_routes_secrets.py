"""Tests for /v1/secrets routes."""

import pytest
from httpx import AsyncClient


class TestSecretsRoutes:
    @pytest.mark.asyncio
    async def test_create_secret(self, client: AsyncClient):
        resp = await client.post(
            "/v1/secrets",
            json={
                "name": "FIREWORKS_API_KEY",
                "value": "fw-abc123",
                "scope": "global",
                "description": "Fireworks API key",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "FIREWORKS_API_KEY"
        assert data["scope"] == "global"
        assert data["description"] == "Fireworks API key"
        # Value should NEVER be in the response
        assert "value" not in data
        assert "encrypted_value" not in data

    @pytest.mark.asyncio
    async def test_create_secret_upsert(self, client: AsyncClient):
        """Creating a secret with same name+scope updates the existing one."""
        await client.post(
            "/v1/secrets",
            json={"name": "KEY", "value": "old", "scope": "global"},
        )
        resp = await client.post(
            "/v1/secrets",
            json={"name": "KEY", "value": "new", "scope": "global"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "KEY"

    @pytest.mark.asyncio
    async def test_create_secret_different_scopes(self, client: AsyncClient):
        """Same name in different scopes is allowed."""
        await client.post(
            "/v1/secrets",
            json={"name": "KEY", "value": "v1", "scope": "global"},
        )
        resp = await client.post(
            "/v1/secrets",
            json={"name": "KEY", "value": "v2", "scope": "agent:agent_01kr69p9haj0dgrts8q8z4bxq5"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_secret_invalid_scope(self, client: AsyncClient):
        resp = await client.post(
            "/v1/secrets",
            json={"name": "BAD", "value": "v", "scope": "invalid"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_secret_invalid_scope_no_uuid(self, client: AsyncClient):
        resp = await client.post(
            "/v1/secrets",
            json={"name": "BAD", "value": "v", "scope": "agent:not-a-ulid"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_secrets_empty(self, client: AsyncClient):
        resp = await client.get("/v1/secrets")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_list_secrets_values_not_returned(self, client: AsyncClient):
        await client.post(
            "/v1/secrets",
            json={"name": "SECRET", "value": "super-secret-value"},
        )
        resp = await client.get("/v1/secrets")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        # Ensure no value fields leak
        for item in items:
            assert "value" not in item
            assert "encrypted_value" not in item

    @pytest.mark.asyncio
    async def test_list_secrets_with_scope_filter(self, client: AsyncClient):
        await client.post(
            "/v1/secrets",
            json={"name": "G", "value": "v", "scope": "global"},
        )
        await client.post(
            "/v1/secrets",
            json={"name": "A", "value": "v", "scope": "agent:agent_01kr69p9haj0dgrts8q8z4bxq5"},
        )
        resp = await client.get("/v1/secrets", params={"scope": "global"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["items"][0]["name"] == "G"

    @pytest.mark.asyncio
    async def test_delete_secret(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/secrets",
            json={"name": "DELETE_ME", "value": "v"},
        )
        secret_id = create_resp.json()["id"]

        resp = await client.delete(f"/v1/secrets/{secret_id}")
        assert resp.status_code == 204

        # Should be gone
        resp = await client.get("/v1/secrets")
        assert resp.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_delete_secret_not_found(self, client: AsyncClient):
        resp = await client.delete(
            "/v1/secrets/scrt_01kr69p9haj0dgrts8q8z4bxq9"
        )
        assert resp.status_code == 404
