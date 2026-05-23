"""Tests for /v1/environments routes."""

import pytest
from httpx import AsyncClient


class TestEnvironmentsRoutes:
    @pytest.mark.asyncio
    async def test_create_environment(self, client: AsyncClient):
        resp = await client.post(
            "/v1/environments",
            json={
                "name": "python-dev",
                "packages": {"pip": ["pandas", "numpy"]},
                "networking": {"type": "limited", "allowed_hosts": ["pypi.org"]},
                "resource_limits": {"memory": "2g", "cpus": 2.0, "pids_limit": 512},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "python-dev"
        assert data["packages"]["pip"] == ["pandas", "numpy"]

    @pytest.mark.asyncio
    async def test_create_environment_defaults(self, client: AsyncClient):
        resp = await client.post(
            "/v1/environments",
            json={"name": "minimal"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "minimal"
        assert data["packages"]["pip"] == []
        assert data["networking"]["type"] == "limited"
        assert data["resource_limits"]["memory"] == "1g"

    @pytest.mark.asyncio
    async def test_create_environment_partial_packages(self, client: AsyncClient):
        resp = await client.post(
            "/v1/environments",
            json={"name": "partial", "packages": {"pip": ["requests"]}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["packages"]["pip"] == ["requests"]
        assert data["packages"]["npm"] == []
        assert data["packages"]["apt"] == []

    @pytest.mark.asyncio
    async def test_create_environment_duplicate_name(self, client: AsyncClient):
        await client.post("/v1/environments", json={"name": "dup"})
        resp = await client.post("/v1/environments", json={"name": "dup"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_environments(self, client: AsyncClient):
        await client.post("/v1/environments", json={"name": "env1"})
        await client.post("/v1/environments", json={"name": "env2"})
        resp = await client.get("/v1/environments")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_get_environment(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/environments", json={"name": "get-me"}
        )
        env_id = create_resp.json()["id"]
        resp = await client.get(f"/v1/environments/{env_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-me"

    @pytest.mark.asyncio
    async def test_get_environment_not_found(self, client: AsyncClient):
        resp = await client.get("/v1/environments/env_01kr69p9haj0dgrts8q8z4bxq6")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_environment(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/environments", json={"name": "original"}
        )
        env_id = create_resp.json()["id"]
        resp = await client.patch(
            f"/v1/environments/{env_id}",
            json={"name": "updated", "packages": {"pip": ["requests"]}},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated"
        assert resp.json()["packages"]["pip"] == ["requests"]

    @pytest.mark.asyncio
    async def test_update_environment_duplicate_name(self, client: AsyncClient):
        await client.post("/v1/environments", json={"name": "env-a"})
        create_resp = await client.post("/v1/environments", json={"name": "env-b"})
        env_b_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/v1/environments/{env_b_id}",
            json={"name": "env-a"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_archive_environment(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/environments", json={"name": "arch-env"}
        )
        env_id = create_resp.json()["id"]
        resp = await client.post(f"/v1/environments/{env_id}/archive")
        assert resp.status_code == 204

        resp = await client.get(f"/v1/environments/{env_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_environments(self, client: AsyncClient):
        ids = []
        for name in ("e1", "e2", "e3"):
            resp = await client.post("/v1/environments", json={"name": name})
            ids.append(resp.json()["id"])

        resp = await client.post("/v1/environments/archive", json={"ids": ids})
        assert resp.status_code == 204

        for eid in ids:
            assert (await client.get(f"/v1/environments/{eid}")).status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_environments_empty_ids(self, client: AsyncClient):
        resp = await client.post("/v1/environments/archive", json={"ids": []})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_archive_environments_no_match(self, client: AsyncClient):
        resp = await client.post("/v1/environments/archive", json={"ids": ["env_nonexistent"]})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_environment_after_archive_same_name(self, client: AsyncClient):
        """Archiving an environment and creating a new one with the same name succeeds."""
        # Create and archive
        create_resp = await client.post(
            "/v1/environments", json={"name": "recycle"}
        )
        env_id = create_resp.json()["id"]
        await client.post(f"/v1/environments/{env_id}/archive")

        # Re-create with same name — should succeed
        resp = await client.post("/v1/environments", json={"name": "recycle"})
        assert resp.status_code == 201
        assert resp.json()["id"] != env_id
