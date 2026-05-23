"""Tool registry — maps tool name strings to actual tool instances.

resolve_tools() is called by the factory graph to convert agent config
tool names (strings) into LangChain BaseTool instances.

Built-in tools (write_todos, read_file, write_file, edit_file, ls, glob,
grep, execute, task) are NOT registered here — create_deep_agent()
automatically includes them via its middleware stack.

This registry holds custom LangChain tools that are NOT MCP-based.
MCP servers are resolved separately via mcp_resolve.resolver.resolve_mcp_tools().

To register a custom tool:
    1. Add it to _TOOLS dict with a descriptive name
    2. The name must match what agents use in their config tools array
    3. Tool instances are created once at startup and shared across agents

Example agent config:
    {"tools": ["my_custom_tool"], "mcp_servers": [...]}
"""

import logging

import httpx
from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)


@tool
def web_fetch(url: str) -> str:
    """Fetch a URL and return its text content.

    Args:
        url: The HTTP(S) URL to fetch.

    Returns:
        Response body as text, or an error message on failure.
    """
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        return f"web_fetch failed: {exc}"


# Registry of custom (non-MCP) tools.
# Add tools here as needed. Each entry maps a string name to a BaseTool instance.
# MCP servers are handled separately — they don't go in this registry.
_TOOLS: dict[str, BaseTool] = {
    "web_fetch": web_fetch,
}


def resolve_tools(tool_names: list[str]) -> list[BaseTool]:
    """Map tool name strings to actual tool instances.

    Only custom (non-MCP) tools are resolved here. MCP tools are resolved
    separately via resolve_mcp_tools() in the factory graph.

    Args:
        tool_names: List of tool name strings from agent config.

    Returns:
        List of LangChain BaseTool instances.

    Raises:
        ValueError: If a tool name isn't found in the registry.
    """
    tools: list[BaseTool] = []
    for name in tool_names:
        if name not in _TOOLS:
            available = list(_TOOLS.keys())
            raise ValueError(
                f"Unknown tool: '{name}'. Available tools: {available}. "
                "MCP servers should be configured via mcp_servers, not tools."
            )
        tools.append(_TOOLS[name])
    return tools
