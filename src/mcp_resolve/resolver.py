"""MCP server tool resolver — converts MCP server configs to LangChain tools.

Fully generic. Any MCP server can be configured via agent config — no
providers are hardcoded. Authentication tokens are injected by the harness
(factory graph) via vault credentials; the sandbox container never sees them.

Uses langchain-mcp-adapters MultiServerMCPClient in stateless mode:
each tool call creates a fresh MCP session, executes, and tears down.
No persistent connections, no cleanup needed.

Supported transports: stdio, http (streamable_http), sse, websocket.

Vault credential injection:
    Headers in MCP server config may contain {{vault:cred_id}} placeholders.
    These are replaced with decrypted tokens from vault_credentials before
    the MCP connection is established. The token never leaves the harness.
"""

import logging
import re

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

_VAULT_PLACEHOLDER_RE = re.compile(r"\{\{vault:([A-Za-z0-9_]+)\}\}")


def _inject_vault_credentials(
    headers: dict[str, str],
    vault_credentials: dict[str, str],
) -> dict[str, str]:
    """Replace {{vault:cred_id}} placeholders in header values.

    Each placeholder is matched against the vault_credentials dict
    (keyed by credential ULID). If found, the placeholder is replaced
    with the decrypted token. If not found, the placeholder is left
    intact and a warning is logged.

    Args:
        headers: Raw header dict from agent MCP config.
        vault_credentials: Decrypted credentials keyed by credential ID.

    Returns:
        New dict with placeholders resolved.
    """
    resolved: dict[str, str] = {}
    for key, value in headers.items():
        def _replace_match(m: re.Match, _creds: dict = vault_credentials) -> str:
            cid = m.group(1)
            if cid in _creds:
                return _creds[cid]
            logger.warning(
                "Vault credential %s not found for header '%s' — "
                "keeping placeholder. Check that the credential exists "
                "and the session has the correct vault_ids.",
                cid, key,
            )
            return m.group(0)

        resolved[key] = _VAULT_PLACEHOLDER_RE.sub(_replace_match, value)
    return resolved


def _build_server_config(
    server: dict,
    vault_credentials: dict[str, str],
) -> dict | None:
    """Build a langchain-mcp-adapters connection config from an agent MCP server entry.

    Args:
        server: Single MCP server config dict from agent config.
        vault_credentials: Decrypted credentials keyed by credential ID.

    Returns:
        Connection config dict for MultiServerMCPClient, or None if transport
        is unknown (with a warning logged).
    """
    transport = server.get("transport", "http")

    if transport == "stdio":
        return {
            "transport": "stdio",
            "command": server["command"],
            "args": server.get("args", []),
            **({"env": server["env"]} if "env" in server else {}),
            **({"cwd": server["cwd"]} if "cwd" in server else {}),
        }

    if transport in ("http", "streamable_http"):
        url = server["url"]
        headers = server.get("headers", {})
        resolved_headers = _inject_vault_credentials(headers, vault_credentials)
        config: dict = {
            "transport": "streamable_http",
            "url": url,
        }
        if resolved_headers:
            config["headers"] = resolved_headers
        return config

    if transport == "sse":
        url = server["url"]
        headers = server.get("headers", {})
        resolved_headers = _inject_vault_credentials(headers, vault_credentials)
        config = {
            "transport": "sse",
            "url": url,
        }
        if resolved_headers:
            config["headers"] = resolved_headers
        return config

    if transport == "websocket":
        url = server["url"]
        return {
            "transport": "websocket",
            "url": url,
        }

    logger.warning(
        "Unknown MCP transport '%s' for server '%s' — skipping. "
        "Supported transports: stdio, http, sse, websocket.",
        transport, server.get("name", "unnamed"),
    )
    return None


async def resolve_mcp_tools(
    mcp_servers: list[dict],
    vault_credentials: dict[str, str],
) -> list[BaseTool]:
    """Convert MCP server configs to LangChain tools.

    Each agent can define zero or more MCP servers. This function builds
    connection configs for all of them, injects vault credentials into
    HTTP headers, and returns the combined tool list.

    In stateless mode (the default), each tool call creates a fresh MCP
    session, executes, and tears down. No persistent state, no cleanup.

    Args:
        mcp_servers: List of MCP server config dicts from agent config.
            Each dict has keys: name, transport, and transport-specific fields.
        vault_credentials: Dict of {cred_id: decrypted_token} for auth injection.

    Returns:
        List of LangChain BaseTool instances. Empty list if no servers configured
        or all servers fail to connect.
    """
    if not mcp_servers:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    server_configs: dict[str, dict] = {}

    for server in mcp_servers:
        name = server.get("name")
        if not name:
            logger.warning("MCP server config missing 'name' — skipping: %s", server)
            continue

        config = _build_server_config(server, vault_credentials)
        if config is not None:
            server_configs[name] = config

    if not server_configs:
        return []

    logger.info(
        "Resolving MCP tools from %d server(s): %s",
        len(server_configs), list(server_configs.keys()),
    )

    client = MultiServerMCPClient(
        server_configs,
        tool_name_prefix=True,  # Prefix tool names with server name to avoid collisions
    )

    try:
        tools = await client.get_tools()
        logger.info(
            "Resolved %d MCP tool(s) from %d server(s)",
            len(tools), len(server_configs),
        )
        return tools
    except Exception as exc:
        logger.error(
            "Failed to resolve MCP tools from %s: %s. "
            "Check that MCP server URLs are correct and reachable.",
            list(server_configs.keys()), exc,
        )
        raise
