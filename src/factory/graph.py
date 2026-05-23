"""Factory graph — per-request agent construction.

Reads everything from context (PlatformContext). Never queries DB.
Returns DockerSandboxBackend when sandbox_id is provided, StateBackend otherwise.

aegra.json configuration:
{
  "dependencies": ["./src"],
  "graphs": {
    "agent": "./src/factory/graph.py:graph"
  }
}

The factory is called by Aegra for each run. It receives:
- config: RunnableConfig dict
- runtime: ServerRuntime[PlatformContext] with typed context access

Context passing flow:
1. Custom route resolves all config (agent, env, secrets, vault creds)
2. Calls client.runs.create(thread_id=..., assistant_id="agent", context={...})
3. Aegra passes context to factory via ServerRuntime[T]
4. Factory: runtime.execution_runtime.context → raw dict → PlatformContext(**raw)

Model provider routing:
The model field uses provider:model format (e.g., 'nvidia:nvidia/...',
'fireworks:accounts/...', 'openai:gpt-4o'). init_chat_model routes to
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from typing import Any

import httpx
from deepagents import create_deep_agent
from deepagents.backends.state import StateBackend
from deepagents.middleware.skills import _list_skills, SKILLS_SYSTEM_PROMPT
from langchain.chat_models import init_chat_model
from langchain_core.tools import BaseTool
from langgraph_sdk.runtime import ServerRuntime

from factory.context import PlatformContext
from mcp_resolve.resolver import resolve_mcp_tools
from tools.registry import resolve_tools

logger = logging.getLogger(__name__)



def _validate_agent_config(agent: dict) -> None:
    """Validate required fields in the agent config dict.

    Args:
        agent: Agent configuration dict from PlatformContext.

    Raises:
        ValueError: If required fields are missing or malformed.
    """
    if "model" not in agent:
        raise ValueError(
            "Agent config missing required field: 'model'. "
            "Every agent must specify a model with 'provider:model' format "
            "(e.g., 'nvidia:nvidia/nemotron-3-super-120b-a22b')."
        )
    model = agent["model"]
    if not isinstance(model, str) or ":" not in model:
        raise ValueError(
            f"Agent model must use 'provider:model' format, got: {model!r}. "
            "Example: 'nvidia:nvidia/nemotron-3-super-120b-a22b'"
        )


def build_minimal_graph() -> Any:
    """Build a minimal graph for Aegra introspection (schema extraction).

    Must have the same topology (nodes, edges, state schema) as the
    execution graph — just empty tool lists and no backend setup.

    Aegra calls the factory for introspection when execution_runtime
    is None. This function must return a compiled graph with identical
    structure so schema extraction works correctly.

    create_deep_agent() always produces the same middleware stack
    (PlanningMiddleware, FilesystemMiddleware, SubAgentMiddleware,
    SummarizationMiddleware) regardless of tools/backend, so calling
    it with empty tools and StateBackend produces matching topology.
    """
    return create_deep_agent(
        model=None,
        tools=[],
        system_prompt="You are a helpful assistant.",
        backend=StateBackend(),
    )


def _create_backend(ctx: PlatformContext) -> Any:
    """Create the sandbox backend based on context.

    Returns LazyDockerSandboxBackend when an environment is configured
    (lazy container creation on first tool call). Otherwise returns
    StateBackend for in-memory execution.
    """
    env_id = ctx.environment.get("id")
    if not env_id:
        return StateBackend()

    from sandbox.backend import DockerSandboxBackend, LazyDockerSandboxBackend

    if ctx.sandbox_id:
        return DockerSandboxBackend(
            container_id=ctx.sandbox_id,
            sandbox_service_url=ctx.sandbox_url,
            api_key=ctx.secrets.get("SANDBOX_API_KEY"),
        )

    return LazyDockerSandboxBackend(
        session_id=ctx.session_id,
        environment_id=env_id,
        agent_id=ctx.agent_id,
        packages=ctx.environment.get("packages", {}),
        resource_limits=ctx.environment.get("resource_limits", {}),
        repositories=ctx.environment.get("repositories", []),
        repo_secrets=ctx.repo_secrets,
        skill_repos=ctx.environment.get("skill_repos", []),
        ip_subnet=ctx.environment.get("ip_subnet"),
        base_image=ctx.environment.get("base_image"),
        sandbox_service_url=ctx.sandbox_url,
        api_key=ctx.secrets.get("SANDBOX_API_KEY"),
        platform_url=ctx.platform_url,
    )


def _build_skills_prompt(backend: Any, skills_paths: list[str]) -> str | None:
    """Read skill metadata from backend sources and format for system prompt.

    Replicates what SkillsMiddleware does before_agent + modify_request,
    but runs synchronously inside the factory graph so Aegra state
    channels are not required.

    Returns the formatted skills section string, or None if no skills found.
    """
    all_skills: list[dict] = []
    for source_path in skills_paths:
        try:
            source_skills = _list_skills(backend, source_path)
            all_skills.extend(source_skills)
        except Exception:
            logger.warning("Failed to list skills from %s", source_path, exc_info=True)

    if not all_skills:
        return None

    locations: list[str] = []
    for i, source_path in enumerate(skills_paths):
        name = PurePosixPath(source_path.rstrip("/")).name.capitalize()
        suffix = " (higher priority)" if i == len(skills_paths) - 1 else ""
        locations.append(f"**{name} Skills**: `{source_path}`{suffix}")

    skills_lines: list[str] = []
    for skill in all_skills:
        desc = skill.get("description", "")
        line = f"- **{skill['name']}**: {desc}"
        annotations: list[str] = []
        if skill.get("license"):
            annotations.append(f"License: {skill['license']}")
        if skill.get("compatibility"):
            annotations.append(f"Compatibility: {skill['compatibility']}")
        if annotations:
            line += f" ({', '.join(annotations)})"
        skills_lines.append(line)
        if skill.get("allowed_tools"):
            skills_lines.append(f"  -> Allowed tools: {', '.join(skill['allowed_tools'])}")
        skills_lines.append(f"  -> Read `{skill['path']}` for full instructions")

    skills_section = SKILLS_SYSTEM_PROMPT.format(
        skills_locations="\n".join(locations),
        skills_list="\n".join(skills_lines),
        skills_load_warnings="",
    )
    return skills_section


async def _update_session_status(callback_url: str, status: str, stop_reason: str | None = None) -> None:
    """POST session status update to the internal callback endpoint.

    Called by the factory graph to transition session status:
    - On run start:  set to "running"
    - On run end:    set to "idle" with stop_reason

    Failures are logged but never raised — the status callback is
    best-effort and must not break the agent run.
    """
    if not callback_url:
        return
    payload = {"status": status}
    if stop_reason is not None:
        payload["stop_reason"] = stop_reason
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                callback_url,
                json=payload,
                timeout=5.0,
            )
    except Exception:
        logger.warning("Failed to update session status to %s at %s", status, callback_url)


@asynccontextmanager
async def graph(
    config: dict[str, Any],
    runtime: ServerRuntime[PlatformContext],
) -> AsyncIterator[Any]:
    """Per-request factory — reads config from context, builds Deep Agents graph.

    Called by Aegra for each run. Uses ServerRuntime[PlatformContext] for
    structural decisions (tool selection, backend type) and passes
    execution-time values (model, system_prompt) to create_deep_agent().

    Args:
        config: RunnableConfig dict from Aegra.
        runtime: ServerRuntime with typed context access.

    Yields:
        Compiled LangGraph graph (Deep Agents agent).
    """
    ert = runtime.execution_runtime

    if ert is None:
        # Introspection call — return minimal graph for schema extraction
        yield build_minimal_graph()
        return

    # Execution call — full setup with context
    raw_ctx = ert.context
    if isinstance(raw_ctx, PlatformContext):
        ctx = raw_ctx
    else:
        ctx = PlatformContext(**raw_ctx)

    # Validate agent config has required fields
    _validate_agent_config(ctx.agent)

    # Create backend (DockerSandboxBackend when sandbox_id is set, StateBackend otherwise)
    backend = _create_backend(ctx)

    # Resolve MCP servers to tools
    mcp_tools: list[BaseTool] = await resolve_mcp_tools(
        mcp_servers=ctx.agent.get("mcp_servers", []),
        vault_credentials=ctx.vault_credentials,
    )

    # Resolve custom tools from registry
    custom_tools: list[BaseTool] = resolve_tools(ctx.agent.get("tools", []))

    # All tools: custom + MCP (built-in tools added automatically by Deep Agents)
    all_tools: list[BaseTool] = custom_tools + mcp_tools

    # Create model instance with API key from secrets.
    # Model string uses provider:model format (e.g.,
    # "nvidia:nvidia/nemotron-3-super-120b-a22b").
    # init_chat_model routes to the correct provider based on the prefix.
    # API key is derived from the provider prefix: "nvidia:" -> "NVIDIA_API_KEY".
    # create_deep_agent() defaults model to Claude if model=None —
    # the factory must always pass the model from context.
    model_str = ctx.agent["model"]
    provider = model_str.split(":")[0].upper()
    api_key_env = f"{provider}_API_KEY"
    api_key = ctx.secrets.get(api_key_env) or os.environ.get(api_key_env)
    model = init_chat_model(
        model_str,
        api_key=api_key,
    )

    # Build system prompt, pre-loading skill metadata directly.
    # Aegra does not support the skills_metadata state channel that
    # SkillsMiddleware requires for progressive disclosure injection,
    # so we read skill metadata from the backend here and append it
    # to the system prompt before passing it to create_deep_agent.
    #
    # Deep Agents has a rich built-in system prompt (planning, tools,
    # subagents).  If no system_prompt was configured we leave it as
    # None so the built-in prompt is preserved.
    system_prompt = ctx.agent.get("system_prompt")
    if not system_prompt:
        system_prompt = None

    skills_paths = ctx.agent.get("skills", [])
    if skills_paths:
        try:
            skills_section = _build_skills_prompt(backend, skills_paths)
        except Exception:
            logger.exception("Failed to build skills prompt from %s", skills_paths)
            raise
        if skills_section:
            system_prompt = (
                f"{system_prompt}\n\n{skills_section}"
                if system_prompt
                else skills_section
            )
            logger.info(
                "Injected %d skills into system prompt (paths: %s)",
                skills_section.count("- **"),
                skills_paths,
            )
        else:
            logger.warning(
                "No skills found in %s — system prompt will not contain skills section",
                skills_paths,
            )

    # Create Deep Agents agent.
    # backend= — NOT sandbox=. Sandboxes are a type of backend.
    # Built-in tools (write_todos, read_file, write_file, edit_file,
    # ls, glob, grep, execute, task) are added automatically by
    # Deep Agents' middleware stack.
    # skills=None — we handle skill injection ourselves above because
    # Aegra does not support the SkillsMiddleware state channel.
    create_kwargs: dict[str, Any] = {
        "model": model,
        "tools": all_tools,
        "backend": backend,
        "skills": None,
    }
    if system_prompt is not None:
        create_kwargs["system_prompt"] = system_prompt
        logger.info(
            "System prompt length: %d chars (skills_section present: %s)",
            len(system_prompt),
            "## Skills System" in system_prompt,
        )

    agent = create_deep_agent(**create_kwargs)

    try:
        await _update_session_status(ctx.status_callback_url, "running")
        yield agent
        await _update_session_status(ctx.status_callback_url, "idle", "completed")
    except Exception:
        await _update_session_status(ctx.status_callback_url, "idle", "error")
        raise
