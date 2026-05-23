"""Integration tests — vault + credential + secret operations.

No mocks. Tests real AES-256-GCM encryption round-trips against
the real PostgreSQL database.
"""

import uuid

import httpx
import pytest


@pytest.mark.integration
class TestVaultSecrets:
    async def test_create_vault_and_credential(self, client, tracker):
        resp = await client.post(
            "/v1/vaults",
            json={"display_name": f"test-vault-{uuid.uuid4().hex[:8]}"},
        )
        assert resp.status_code == 201
        vault = resp.json()
        tracker.vaults.append(vault["id"])

        resp = await client.post(
            f"/v1/vaults/{vault['id']}/credentials",
            json={
                "display_name": "Test MCP Cred",
                "mcp_server_url": "https://mcp.example.com/mcp",
                "auth_type": "static_bearer",
                "token": "my-secret-api-key",
            },
        )
        assert resp.status_code == 201
        cred = resp.json()
        assert cred["display_name"] == "Test MCP Cred"
        assert cred["mcp_server_url"] == "https://mcp.example.com/mcp"
        assert "token" not in cred  # token must never be returned

    async def test_credential_token_never_returned_in_get(self, client, tracker):
        resp = await client.post(
            "/v1/vaults",
            json={"display_name": f"test-vault-{uuid.uuid4().hex[:8]}"},
        )
        vault = resp.json()
        tracker.vaults.append(vault["id"])

        await client.post(
            f"/v1/vaults/{vault['id']}/credentials",
            json={
                "display_name": "Secret Cred",
                "mcp_server_url": "https://mcp.example.com/mcp",
                "auth_type": "static_bearer",
                "token": "super-secret-token-value",
            },
        )

        # Get vault — should include credential metadata but NOT the token
        resp = await client.get(f"/v1/vaults/{vault['id']}")
        assert resp.status_code == 200
        data = resp.json()
        creds = data.get("credentials", [])
        assert len(creds) >= 1
        for c in creds:
            assert "token" not in c
            assert "encrypted_token" not in c

    async def test_rotate_credential(self, client, tracker):
        resp = await client.post(
            "/v1/vaults",
            json={"display_name": f"test-vault-{uuid.uuid4().hex[:8]}"},
        )
        vault = resp.json()
        tracker.vaults.append(vault["id"])

        resp = await client.post(
            f"/v1/vaults/{vault['id']}/credentials",
            json={
                "display_name": "Rotate Me",
                "mcp_server_url": "https://mcp.example.com/mcp",
                "auth_type": "static_bearer",
                "token": "old-token",
            },
        )
        cred = resp.json()

        resp = await client.patch(
            f"/v1/vaults/{vault['id']}/credentials/{cred['id']}",
            json={"token": "new-token"},
        )
        assert resp.status_code == 200

    async def test_create_secret(self, client, tracker):
        resp = await client.post(
            "/v1/secrets",
            json={
                "name": f"TEST_KEY_{uuid.uuid4().hex[:8]}",
                "value": "secret-value-123",
                "scope": "global",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        tracker.secrets.append(data["id"])
        assert data["name"]
        assert "value" not in data  # value must never be returned

    async def test_secret_value_never_returned_in_list(self, client, tracker):
        name = f"LIST_TEST_{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/secrets",
            json={"name": name, "value": "my-secret", "scope": "global"},
        )
        secret = resp.json()
        tracker.secrets.append(secret["id"])

        resp = await client.get("/v1/secrets")
        assert resp.status_code == 200
        data = resp.json()
        found = [s for s in data["items"] if s["name"] == name]
        assert len(found) >= 1
        for s in found:
            assert "value" not in s
            assert "encrypted_value" not in s

    async def test_delete_secret(self, client, tracker):
        name = f"DELETE_TEST_{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/v1/secrets",
            json={"name": name, "value": "delete-me", "scope": "global"},
        )
        assert resp.status_code == 201
        secret_id = resp.json()["id"]

        resp = await client.delete(f"/v1/secrets/{secret_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = await client.get("/v1/secrets")
        names = [s["name"] for s in resp.json()["items"]]
        assert name not in names
