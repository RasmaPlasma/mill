"""Unit tests for the MCP resolver — resolve_mcp_tools().

Tests server config building, vault credential injection, transport
handling, and error cases. Uses mock MultiServerMCPClient (no real
MCP servers needed).
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_resolve.resolver import (
    _build_server_config,
    _inject_vault_credentials,
    resolve_mcp_tools,
)

# ULID-style credential IDs for vault credential tests
CRED_ULID_1 = "vcrd_01HqR2k7vXbZ9mNpL3wYcT8f"
CRED_ULID_2 = "vcrd_01HqR2k7vXbZ9mNpL3wYcT9g"
MISSING_ULID = "vcrd_01HqR2k7vXbZ9mNpL3wYcT0z"


class TestInjectVaultCredentials:
    """Tests for _inject_vault_credentials()."""

    def test_placeholder_only_value(self):
        """Header value that is entirely a placeholder gets replaced with the token."""
        headers = {"Authorization": f"{{{{vault:{CRED_ULID_1}}}}}"}
        creds = {CRED_ULID_1: "my-secret-token"}
        result = _inject_vault_credentials(headers, creds)
        assert result["Authorization"] == "my-secret-token"

    def test_placeholder_with_prefix(self):
        """Placeholder embedded in a larger value preserves surrounding text."""
        headers = {"Authorization": f"Bearer {{{{vault:{CRED_ULID_1}}}}}"}
        creds = {CRED_ULID_1: "my-secret-token"}
        result = _inject_vault_credentials(headers, creds)
        assert result["Authorization"] == "Bearer my-secret-token"

    def test_no_placeholders(self):
        headers = {"Authorization": "Bearer static-token"}
        result = _inject_vault_credentials(headers, {})
        assert result["Authorization"] == "Bearer static-token"

    def test_missing_credential_keeps_placeholder(self, caplog):
        headers = {"Authorization": f"Bearer {{{{vault:{MISSING_ULID}}}}}"}
        with caplog.at_level(logging.WARNING):
            result = _inject_vault_credentials(headers, {})
        assert result["Authorization"] == f"Bearer {{{{vault:{MISSING_ULID}}}}}"
        assert f"Vault credential {MISSING_ULID} not found" in caplog.text

    def test_multiple_headers_mixed(self):
        headers = {
            "Authorization": f"Bearer {{{{vault:{CRED_ULID_1}}}}}",
            "X-Custom": "static-value",
        }
        creds = {CRED_ULID_1: "token-1"}
        result = _inject_vault_credentials(headers, creds)
        assert result["Authorization"] == "Bearer token-1"
        assert result["X-Custom"] == "static-value"

    def test_placeholder_with_surrounding_text(self):
        """Placeholder with text on both sides gets inline replacement."""
        headers = {"Authorization": f"Prefix {{{{vault:{CRED_ULID_1}}}}} suffix"}
        creds = {CRED_ULID_1: "my-token"}
        result = _inject_vault_credentials(headers, creds)
        assert result["Authorization"] == "Prefix my-token suffix"


class TestBuildServerConfig:
    """Tests for _build_server_config()."""

    def test_stdio_transport(self):
        server = {
            "name": "fs",
            "transport": "stdio",
            "command": "python",
            "args": ["/srv.py"],
        }
        config = _build_server_config(server, {})
        assert config["transport"] == "stdio"
        assert config["command"] == "python"
        assert config["args"] == ["/srv.py"]

    def test_stdio_with_env(self):
        server = {
            "name": "fs",
            "transport": "stdio",
            "command": "python",
            "args": ["/srv.py"],
            "env": {"KEY": "value"},
        }
        config = _build_server_config(server, {})
        assert config["env"] == {"KEY": "value"}

    def test_http_transport(self):
        server = {
            "name": "api",
            "transport": "http",
            "url": "http://mcp.example.com/mcp",
        }
        config = _build_server_config(server, {})
        assert config["transport"] == "streamable_http"
        assert config["url"] == "http://mcp.example.com/mcp"

    def test_http_with_vault_headers(self):
        server = {
            "name": "api",
            "transport": "http",
            "url": "http://mcp.example.com/mcp",
            "headers": {"Authorization": f"Bearer {{{{vault:{CRED_ULID_1}}}}}"},
        }
        creds = {CRED_ULID_1: "decrypted-token"}
        config = _build_server_config(server, creds)
        assert config["headers"]["Authorization"] == "Bearer decrypted-token"

    def test_sse_transport(self):
        server = {
            "name": "events",
            "transport": "sse",
            "url": "http://mcp.example.com/sse",
        }
        config = _build_server_config(server, {})
        assert config["transport"] == "sse"
        assert config["url"] == "http://mcp.example.com/sse"

    def test_websocket_transport(self):
        server = {
            "name": "ws",
            "transport": "websocket",
            "url": "ws://mcp.example.com/ws",
        }
        config = _build_server_config(server, {})
        assert config["transport"] == "websocket"

    def test_unknown_transport_returns_none(self, caplog):
        server = {"name": "bad", "transport": "ftp"}
        with caplog.at_level(logging.WARNING):
            config = _build_server_config(server, {})
        assert config is None
        assert "Unknown MCP transport 'ftp'" in caplog.text

    def test_default_transport_is_http(self):
        server = {
            "name": "default",
            "url": "http://mcp.example.com/mcp",
        }
        config = _build_server_config(server, {})
        assert config["transport"] == "streamable_http"


class TestResolveMcpTools:
    """Tests for resolve_mcp_tools()."""

    @pytest.mark.asyncio
    async def test_empty_servers_returns_empty(self):
        result = await resolve_mcp_tools([], {})
        assert result == []

    @pytest.mark.asyncio
    async def test_stdio_server_builds_config_and_calls_client(self):
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"

        with patch("langchain_mcp_adapters.client.MultiServerMCPClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_tools = AsyncMock(return_value=[mock_tool])
            mock_cls.return_value = mock_instance

            servers = [{
                "name": "fs",
                "transport": "stdio",
                "command": "python",
                "args": ["/srv.py"],
            }]
            result = await resolve_mcp_tools(servers, {})

            assert len(result) == 1
            assert result[0].name == "test_tool"

            call_args = mock_cls.call_args
            config = call_args[0][0]
            assert "fs" in config
            assert config["fs"]["transport"] == "stdio"
            assert call_args[1].get("tool_name_prefix") is True

    @pytest.mark.asyncio
    async def test_http_server_injects_vault_credentials(self):
        with patch("langchain_mcp_adapters.client.MultiServerMCPClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_tools = AsyncMock(return_value=[])
            mock_cls.return_value = mock_instance

            servers = [{
                "name": "exa",
                "transport": "http",
                "url": "https://mcp.exa.ai/mcp",
                "headers": {"Authorization": f"Bearer {{{{vault:{CRED_ULID_1}}}}}"},
            }]
            vault_creds = {CRED_ULID_1: "exa-api-key-123"}

            await resolve_mcp_tools(servers, vault_creds)

            config = mock_cls.call_args[0][0]
            assert config["exa"]["headers"]["Authorization"] == "Bearer exa-api-key-123"

    @pytest.mark.asyncio
    async def test_multiple_servers(self):
        with patch("langchain_mcp_adapters.client.MultiServerMCPClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_tools = AsyncMock(return_value=[])
            mock_cls.return_value = mock_instance

            servers = [
                {"name": "server1", "transport": "stdio", "command": "python"},
                {"name": "server2", "transport": "http", "url": "http://localhost:8000/mcp"},
            ]
            await resolve_mcp_tools(servers, {})

            config = mock_cls.call_args[0][0]
            assert "server1" in config
            assert "server2" in config

    @pytest.mark.asyncio
    async def test_unknown_transport_skipped(self, caplog):
        with patch("langchain_mcp_adapters.client.MultiServerMCPClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_tools = AsyncMock(return_value=[])
            mock_cls.return_value = mock_instance

            servers = [
                {"name": "good", "transport": "stdio", "command": "python"},
                {"name": "bad", "transport": "ftp"},
            ]
            with caplog.at_level(logging.WARNING):
                await resolve_mcp_tools(servers, {})

            config = mock_cls.call_args[0][0]
            assert "good" in config
            assert "bad" not in config
            assert "Unknown MCP transport" in caplog.text

    @pytest.mark.asyncio
    async def test_missing_name_skipped(self, caplog):
        servers = [{"transport": "stdio", "command": "python"}]
        with caplog.at_level(logging.WARNING):
            result = await resolve_mcp_tools(servers, {})
        assert result == []
        assert "missing 'name'" in caplog.text

    @pytest.mark.asyncio
    async def test_client_error_raises(self, caplog):
        """MCP connection errors now propagate to the caller instead of returning []."""
        with patch("langchain_mcp_adapters.client.MultiServerMCPClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_tools = AsyncMock(side_effect=RuntimeError("Connection failed"))
            mock_cls.return_value = mock_instance

            servers = [{"name": "failing", "transport": "http", "url": "http://bad"}]
            with caplog.at_level(logging.ERROR):
                with pytest.raises(RuntimeError, match="Connection failed"):
                    await resolve_mcp_tools(servers, {})
            assert "Failed to resolve MCP tools" in caplog.text
