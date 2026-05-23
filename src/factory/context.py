"""Typed factory context — drives model selection, tools, and backend creation.

PlatformContext is the dict passed from custom routes to the factory graph
via Aegra's context mechanism. All fields are resolved by custom routes
from the DB. The factory graph reads everything from here — never queries DB.

Usage:
    Custom routes resolve config → client.runs.create(context={...})
    Aegra passes context to factory via ServerRuntime[T]
    Factory: runtime.execution_runtime.context → PlatformContext(**raw)
"""

from pydantic import BaseModel, ConfigDict


class PlatformContext(BaseModel):
    """Request context for the platform factory graph.

    Callers pass this as ``context={...}`` when creating a run. Fields are
    used at two different levels:

    **Factory level** (``ServerRuntime[PlatformContext]``):
        ``agent.tools``, ``agent.mcp_servers``, ``sandbox_id`` control
        graph structure and resource lifecycle — decisions that must
        happen before execution.

    **Node level** (``Runtime[PlatformContext]``):
        ``agent.model``, ``agent.system_prompt`` are read inside node
        functions during execution via LangGraph's standard runtime injection.

    Attributes:
        agent: Agent configuration dict containing:
            - model: LLM identifier in provider:model format (required)
              e.g., 'nvidia:nvidia/nemotron-3-super-120b-a22b',
              'fireworks:accounts/fireworks/models/qwen3-235b-a22b',
              'openai:gpt-5'
            - system_prompt: System message for the agent
            - tools: List of custom tool name strings
            - mcp_servers: List of MCP server config dicts
            - skills: List of filesystem paths where SkillsMiddleware should scan for SKILL.md files (auto-injected by session resolver when environment has skill_repos)
        environment: Environment configuration dict containing:
            - packages: Dict of package manager → package list
            - networking: Network configuration dict
            - resource_limits: Container resource limits dict
        secrets: Dict of {key: value} for harness injection (API keys, etc.)
        vault_credentials: Dict of {credential_id: token} for MCP auth
        sandbox_id: Container ID from sandbox service (empty for StateBackend)
        sandbox_url: Sandbox service HTTP endpoint (empty for StateBackend)
        status_callback_url: URL for factory to update session status
    """

    model_config = ConfigDict(extra="ignore")

    agent: dict
    environment: dict = {}
    secrets: dict = {}
    vault_credentials: dict = {}
    sandbox_url: str = ""
    sandbox_id: str = ""
    status_callback_url: str = ""
    session_id: str = ""
    agent_id: str = ""
    repo_secrets: dict = {}
    platform_url: str = ""
