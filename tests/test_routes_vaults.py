"""Tests for /v1/vaults routes."""

import pytest
from httpx import AsyncClient


class TestVaultsRoutes:
    @pytest.mark.asyncio
    async def test_create_vault(self, client: AsyncClient):
        resp = await client.post(
            "/v1/vaults",
            json={"display_name": "my-vault", "metadata": {"team": "backend"}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "my-vault"
        assert data["metadata"]["team"] == "backend"
        assert data["credentials"] == []

    @pytest.mark.asyncio
    async def test_list_vaults(self, client: AsyncClient):
        await client.post("/v1/vaults", json={"display_name": "v1"})
        await client.post("/v1/vaults", json={"display_name": "v2"})
        resp = await client.get("/v1/vaults")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_get_vault(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/vaults", json={"display_name": "get-me"}
        )
        vault_id = create_resp.json()["id"]
        resp = await client.get(f"/v1/vaults/{vault_id}")
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "get-me"

    @pytest.mark.asyncio
    async def test_get_vault_not_found(self, client: AsyncClient):
        resp = await client.get("/v1/vaults/vlt_01kr69p9haj0dgrts8q8z4bxq8")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_vault(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/vaults", json={"display_name": "original"}
        )
        vault_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/v1/vaults/{vault_id}",
            json={"display_name": "updated", "metadata": {"key": "value"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "updated"
        assert data["metadata"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_update_vault_no_fields(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/vaults", json={"display_name": "noop"}
        )
        resp = await client.patch(
            f"/v1/vaults/{create_resp.json()['id']}", json={}
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_archive_vault(self, client: AsyncClient):
        create_resp = await client.post(
            "/v1/vaults", json={"display_name": "arch"}
        )
        vault_id = create_resp.json()["id"]

        resp = await client.post(f"/v1/vaults/{vault_id}/archive")
        assert resp.status_code == 204

        resp = await client.get(f"/v1/vaults/{vault_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_vaults(self, client: AsyncClient):
        ids = []
        for name in ("v1", "v2", "v3"):
            resp = await client.post("/v1/vaults", json={"display_name": name})
            ids.append(resp.json()["id"])

        resp = await client.post("/v1/vaults/archive", json={"ids": ids})
        assert resp.status_code == 204

        for vid in ids:
            assert (await client.get(f"/v1/vaults/{vid}")).status_code == 404

    @pytest.mark.asyncio
    async def test_bulk_archive_vaults_empty_ids(self, client: AsyncClient):
        resp = await client.post("/v1/vaults/archive", json={"ids": []})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_bulk_archive_vaults_no_match(self, client: AsyncClient):
        resp = await client.post("/v1/vaults/archive", json={"ids": ["vault_nonexistent"]})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_vault_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/v1/vaults/vlt_01kr69p9haj0dgrts8q8z4bxq8/archive"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_credential(self, client: AsyncClient):
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "cred-vault"}
        )
        vault_id = vault_resp.json()["id"]

        resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "MCP Server Token",
                "mcp_server_url": "http://mcp.example.com",
                "auth_type": "static_bearer",
                "token": "my-secret-token",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["display_name"] == "MCP Server Token"
        assert data["mcp_server_url"] == "http://mcp.example.com"
        # Token should NEVER be in the response
        assert "token" not in data
        assert "encrypted_token" not in data

    @pytest.mark.asyncio
    async def test_add_credential_invalid_auth_type(self, client: AsyncClient):
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "bad-auth"}
        )
        vault_id = vault_resp.json()["id"]

        resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "bad",
                "mcp_server_url": "http://x.com",
                "auth_type": "invalid_type",
                "token": "t",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_credential_duplicate_url(self, client: AsyncClient):
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "dup-vault"}
        )
        vault_id = vault_resp.json()["id"]

        await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "c1",
                "mcp_server_url": "http://same.com",
                "auth_type": "static_bearer",
                "token": "token1",
            },
        )
        resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "c2",
                "mcp_server_url": "http://same.com",
                "auth_type": "static_bearer",
                "token": "token2",
            },
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_add_credential_vault_not_found(self, client: AsyncClient):
        resp = await client.post(
            "/v1/vaults/vlt_01kr69p9haj0dgrts8q8z4bxq8/credentials",
            json={
                "display_name": "c",
                "mcp_server_url": "http://x.com",
                "auth_type": "static_bearer",
                "token": "t",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rotate_credential(self, client: AsyncClient):
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "rot-vault"}
        )
        vault_id = vault_resp.json()["id"]

        cred_resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "rotate-me",
                "mcp_server_url": "http://mcp.example.com",
                "auth_type": "static_bearer",
                "token": "old-token",
            },
        )
        cred_id = cred_resp.json()["id"]

        resp = await client.patch(
            f"/v1/vaults/{vault_id}/credentials/{cred_id}",
            json={"token": "new-token", "refresh_token": "new-refresh", "expires_at": "2027-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == cred_id

    @pytest.mark.asyncio
    async def test_get_vault_includes_credentials(self, client: AsyncClient):
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "with-creds"}
        )
        vault_id = vault_resp.json()["id"]

        await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "cred1",
                "mcp_server_url": "http://a.com",
                "auth_type": "static_bearer",
                "token": "t1",
            },
        )
        await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "cred2",
                "mcp_server_url": "http://b.com",
                "auth_type": "static_bearer",
                "token": "t2",
            },
        )

        resp = await client.get(f"/v1/vaults/{vault_id}")
        assert resp.status_code == 200
        assert len(resp.json()["credentials"]) == 2

    @pytest.mark.asyncio
    async def test_add_credential_after_archive_same_url(self, client: AsyncClient):
        """Archiving a credential and re-adding the same URL should succeed."""
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "re-add"}
        )
        vault_id = vault_resp.json()["id"]

        # Add credential
        cred_resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "first",
                "mcp_server_url": "http://same.com",
                "auth_type": "static_bearer",
                "token": "token1",
            },
        )
        assert cred_resp.status_code == 201

        # Try adding a second credential with the same URL — should fail while the
        # first is active
        dup_resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "second",
                "mcp_server_url": "http://same.com",
                "auth_type": "static_bearer",
                "token": "token2",
            },
        )
        assert dup_resp.status_code == 409

    @pytest.mark.asyncio
    async def test_add_credential_after_archive_same_url_success(
        self, client: AsyncClient, session
    ):
        """After archiving a credential, re-adding the same URL succeeds."""
        vault_resp = await client.post(
            "/v1/vaults", json={"display_name": "re-add2"}
        )
        vault_id = vault_resp.json()["id"]

        # Add credential
        cred_resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "first",
                "mcp_server_url": "http://same2.com",
                "auth_type": "static_bearer",
                "token": "token1",
            },
        )
        assert cred_resp.status_code == 201
        cred_id = cred_resp.json()["id"]

        # Archive the credential directly via DB
        from db.models import Credential as CredModel
        from sqlalchemy import select
        from datetime import datetime, timezone

        row = await session.execute(
            select(CredModel).where(CredModel.id == cred_id)
        )
        cred = row.scalar_one()
        cred.archived_at = datetime.now(timezone.utc)
        await session.flush()

        # Re-add same URL — should succeed
        resp = await client.post(
            f"/v1/vaults/{vault_id}/credentials",
            json={
                "display_name": "second",
                "mcp_server_url": "http://same2.com",
                "auth_type": "static_bearer",
                "token": "token2",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["id"] != cred_id
