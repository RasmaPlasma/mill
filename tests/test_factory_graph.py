"""Unit tests for Phase 1: Factory graph, PlatformContext, and tool registry."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from deepagents.backends.state import StateBackend

from factory.context import PlatformContext
from factory.graph import _create_backend, _validate_agent_config, build_minimal_graph, graph
from mcp_resolve.resolver import resolve_mcp_tools
from tools.registry import resolve_tools


# ---------------------------------------------------------------------------
# PlatformContext tests
# ---------------------------------------------------------------------------


class TestPlatformContext:
    """Tests for PlatformContext Pydantic model."""

    def test_coerce_from_dict_minimal(self):
        """Minimal context dict coerces correctly."""
        raw = {
            "agent": {
                "model": "fireworks:accounts/fireworks/models/qwen3-235b-a22b",
                "system_prompt": "You are helpful.",
            },
        }
        ctx = PlatformContext(**raw)
        assert ctx.agent["model"] == "fireworks:accounts/fireworks/models/qwen3-235b-a22b"
        assert ctx.agent["system_prompt"] == "You are helpful."
        assert ctx.environment == {}
        assert ctx.secrets == {}
        assert ctx.vault_credentials == {}
        assert ctx.sandbox_url == ""
        assert ctx.status_callback_url == ""

    def test_coerce_from_dict_full(self):
        """Full context dict with all fields coerces correctly."""
        raw = {
            "agent": {
                "model": "fireworks:accounts/fireworks/models/qwen3-235b-a22b",
                "system_prompt": "You are a coder.",
                "tools": ["tavily_search"],
                "mcp_servers": [{"name": "fs", "transport": "stdio", "command": "python"}],
                "skills": ["/workspace/.skills/"],
            },
            "environment": {
                "packages": {"pip": ["pandas"]},
                "networking": {"type": "limited"},
                "resource_limits": {"memory": "1g"},
            },
            "secrets": {"FIREWORKS_API_KEY": "fw-abc123"},
            "vault_credentials": {"http://mcp.example.com": "token123"},
            "sandbox_url": "http://sandbox:8090",
            "sandbox_id": "container-abc123",
            "status_callback_url": "http://localhost:2026/internal/sessions/sess-1/status",
            "session_id": "sess-1",
            "agent_id": "agent-1",
        }
        ctx = PlatformContext(**raw)
        assert ctx.agent["model"] == "fireworks:accounts/fireworks/models/qwen3-235b-a22b"
        assert ctx.agent["tools"] == ["tavily_search"]
        assert ctx.environment["packages"] == {"pip": ["pandas"]}
        assert ctx.secrets["FIREWORKS_API_KEY"] == "fw-abc123"
        assert ctx.vault_credentials["http://mcp.example.com"] == "token123"
        assert ctx.sandbox_url == "http://sandbox:8090"
        assert ctx.sandbox_id == "container-abc123"
        assert ctx.status_callback_url == "http://localhost:2026/internal/sessions/sess-1/status"
        assert ctx.session_id == "sess-1"
        assert ctx.agent_id == "agent-1"

    def test_coerce_missing_agent_raises(self):
        """Missing required 'agent' field raises ValidationError."""
        with pytest.raises(Exception):  # ValidationError
            PlatformContext(environment={})

    def test_coerce_extra_fields_ignored(self):
        """Extra fields are ignored (Pydantic default behavior)."""
        raw = {
            "agent": {"model": "fireworks:test"},
            "unknown_field": "should be ignored",
        }
        ctx = PlatformContext(**raw)
        assert ctx.agent["model"] == "fireworks:test"


# ---------------------------------------------------------------------------
# Tool registry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    """Tests for resolve_tools()."""

    def test_empty_list_returns_empty(self):
        """Empty tool_names returns empty list."""
        result = resolve_tools([])
        assert result == []

    def test_unknown_tool_raises_value_error(self):
        """Unknown tool name raises ValueError with clear message."""
        with pytest.raises(ValueError, match="Unknown tool: 'nonexistent'"):
            resolve_tools(["nonexistent"])

    def test_unknown_tool_error_lists_available(self):
        """ValueError message lists available tools."""
        with pytest.raises(ValueError, match="Available tools:"):
            resolve_tools(["nonexistent"])


# ---------------------------------------------------------------------------
# MCP resolver tests
# ---------------------------------------------------------------------------


class TestMcpResolver:
    """Tests for resolve_mcp_tools()."""

    @pytest.mark.asyncio
    async def test_empty_servers_returns_empty(self):
        """Empty mcp_servers returns empty list."""
        result = await resolve_mcp_tools([], {})
        assert result == []

    @pytest.mark.asyncio
    async def test_non_empty_servers_resolves_tools(self):
        """Non-empty mcp_servers resolves tools via MultiServerMCPClient."""
        mock_tool = MagicMock()
        mock_tool.name = "mcp_tool"

        with patch("langchain_mcp_adapters.client.MultiServerMCPClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_tools = AsyncMock(return_value=[mock_tool])
            mock_cls.return_value = mock_instance

            servers = [{"name": "test", "transport": "stdio", "command": "python"}]
            result = await resolve_mcp_tools(servers, {})
            assert len(result) == 1
            assert result[0].name == "mcp_tool"


# ---------------------------------------------------------------------------
# Factory graph tests
# ---------------------------------------------------------------------------


class TestFactoryGraph:
    """Tests for factory graph introspection and execution paths."""

    def test_build_minimal_graph_returns_compiled_graph(self):
        """build_minimal_graph() returns a compiled LangGraph graph."""
        with patch("factory.graph.create_deep_agent") as mock_create_agent:
            mock_agent = MagicMock()
            mock_create_agent.return_value = mock_agent

            result = build_minimal_graph()
            assert result is mock_agent
            mock_create_agent.assert_called_once()

    def test_create_backend_returns_state_backend(self):
        """_create_backend() returns StateBackend when sandbox_id is empty."""
        ctx = PlatformContext(
            agent={"model": "fireworks:test"},
            sandbox_id="",
            sandbox_url="",
        )
        backend = _create_backend(ctx)
        assert isinstance(backend, StateBackend)

    def test_create_backend_env_id_returns_lazy_backend(self):
        """_create_backend() returns LazyDockerSandboxBackend when environment.id is set."""
        ctx = PlatformContext(
            agent={"model": "fireworks:test"},
            environment={"id": "env-123"},
            sandbox_url="http://sandbox:8090",
            secrets={"SANDBOX_API_KEY": "test-key"},
            session_id="sess-123",
            agent_id="agent-123",
            platform_url="http://localhost:2026",
        )
        backend = _create_backend(ctx)
        from sandbox.backend import LazyDockerSandboxBackend

        assert isinstance(backend, LazyDockerSandboxBackend)

    def test_create_backend_sandbox_id_returns_direct_backend(self):
        """_create_backend() returns DockerSandboxBackend when sandbox_id is set."""
        ctx = PlatformContext(
            agent={"model": "fireworks:test"},
            environment={"id": "env-123"},
            sandbox_id="container-abc123",
            sandbox_url="http://sandbox:8090",
            secrets={"SANDBOX_API_KEY": "test-key"},
        )
        backend = _create_backend(ctx)
        from sandbox.backend import DockerSandboxBackend

        assert isinstance(backend, DockerSandboxBackend)
        assert backend.id == "container-abc123"

    @pytest.mark.asyncio
    async def test_introspection_path_yields_minimal_graph(self):
        """Factory yields minimal graph when execution_runtime is None."""
        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = None

        with patch("factory.graph.create_deep_agent") as mock_create_agent:
            mock_agent = MagicMock()
            mock_create_agent.return_value = mock_agent

            async with graph({}, mock_runtime) as agent:
                assert agent is mock_agent

    @pytest.mark.asyncio
    async def test_execution_path_yields_agent(self):
        """Factory yields Deep Agents agent when execution_runtime has context."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "fireworks:accounts/fireworks/models/qwen3-235b-a22b",
                "system_prompt": "You are helpful.",
                "tools": [],
                "mcp_servers": [],
            },
            "environment": {},
            "secrets": {},
            "vault_credentials": {},
            "sandbox_id": "",
            "sandbox_url": "",
            "status_callback_url": "",
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_model = MagicMock()
            mock_init_model.return_value = mock_model

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_agent = MagicMock()
                mock_create_agent.return_value = mock_agent

                async with graph({}, mock_runtime) as agent:
                    assert agent is mock_agent
                    assert hasattr(agent, "invoke")

    @pytest.mark.asyncio
    async def test_execution_path_uses_context_model(self):
        """Factory uses model from context, not default."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "fireworks:accounts/fireworks/models/qwen3-235b-a22b",
                "system_prompt": "Test prompt.",
            },
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_model = MagicMock()
            mock_init_model.return_value = mock_model

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_agent = MagicMock()
                mock_create_agent.return_value = mock_agent

                async with graph({}, mock_runtime):
                    # Verify init_chat_model was called with correct model
                    mock_init_model.assert_called_once_with(
                        "fireworks:accounts/fireworks/models/qwen3-235b-a22b",
                        api_key=None,
                    )
                    # Verify create_deep_agent was called with the model
                    mock_create_agent.assert_called_once()
                    call_kwargs = mock_create_agent.call_args
                    assert call_kwargs.kwargs["model"] is mock_model
                    assert call_kwargs.kwargs["system_prompt"] == "Test prompt."

    @pytest.mark.asyncio
    async def test_execution_path_passes_secrets_as_api_key(self):
        """Factory derives API key name from provider prefix."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "nvidia:nvidia/nemotron-3-super-120b-a22b",
                "system_prompt": "Test.",
            },
            "secrets": {"NVIDIA_API_KEY": "nv-secret-key"},
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_init_model.return_value = MagicMock()

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_create_agent.return_value = MagicMock()

                async with graph({}, mock_runtime):
                    mock_init_model.assert_called_once_with(
                        "nvidia:nvidia/nemotron-3-super-120b-a22b",
                        api_key="nv-secret-key",
                    )

    @pytest.mark.asyncio
    async def test_execution_path_derives_fireworks_key(self):
        """Factory derives FIREWORKS_API_KEY for fireworks: prefix."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "fireworks:accounts/fireworks/models/qwen3-235b-a22b",
                "system_prompt": "Test.",
            },
            "secrets": {"FIREWORKS_API_KEY": "fw-key"},
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_init_model.return_value = MagicMock()

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_create_agent.return_value = MagicMock()

                async with graph({}, mock_runtime):
                    mock_init_model.assert_called_once_with(
                        "fireworks:accounts/fireworks/models/qwen3-235b-a22b",
                        api_key="fw-key",
                    )

    @pytest.mark.asyncio
    async def test_execution_path_passes_tools_to_agent(self):
        """Factory passes custom tools to create_deep_agent."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "fireworks:test",
                "system_prompt": "Test.",
                "tools": [],
            },
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_init_model.return_value = MagicMock()

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_create_agent.return_value = MagicMock()

                async with graph({}, mock_runtime):
                    call_kwargs = mock_create_agent.call_args
                    # Empty tools list since no custom tools registered
                    assert call_kwargs.kwargs["tools"] == []

    @pytest.mark.asyncio
    async def test_execution_path_passes_backend(self):
        """Factory passes StateBackend to create_deep_agent."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "fireworks:test",
                "system_prompt": "Test.",
            },
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_init_model.return_value = MagicMock()

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_create_agent.return_value = MagicMock()

                async with graph({}, mock_runtime):
                    call_kwargs = mock_create_agent.call_args
                    assert isinstance(call_kwargs.kwargs["backend"], StateBackend)

    def test_minimal_and_execution_graph_same_topology(self):
        """build_minimal_graph() and execution graph use same create_deep_agent args."""
        with patch("factory.graph.create_deep_agent") as mock_create_agent:
            mock_agent = MagicMock()
            mock_create_agent.return_value = mock_agent

            build_minimal_graph()

            call_kwargs = mock_create_agent.call_args.kwargs
            assert call_kwargs["tools"] == []
            assert call_kwargs["system_prompt"] == "You are a helpful assistant."
            assert isinstance(call_kwargs["backend"], StateBackend)

    @pytest.mark.asyncio
    async def test_execution_path_missing_model_raises_value_error(self):
        """Factory raises ValueError when agent config is missing 'model'."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "system_prompt": "Test.",
            },
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with pytest.raises(ValueError, match="missing required field: 'model'"):
            async with graph({}, mock_runtime):
                pass

    @pytest.mark.asyncio
    async def test_execution_path_no_provider_prefix_raises_value_error(self):
        """Factory raises ValueError when model has no provider: prefix."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "gpt-4o",
                "system_prompt": "Test.",
            },
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with pytest.raises(ValueError, match="provider:model"):
            async with graph({}, mock_runtime):
                pass

    @pytest.mark.asyncio
    async def test_execution_path_calls_status_callback(self):
        """Factory calls update_session_status on start and end."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "fireworks:test",
                "system_prompt": "Test.",
            },
            "status_callback_url": "http://localhost:2026/internal/sessions/s1/status",
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_init_model.return_value = MagicMock()

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_create_agent.return_value = MagicMock()

                with patch("factory.graph._update_session_status") as mock_status:
                    async with graph({}, mock_runtime):
                        # "running" called before yield
                        mock_status.assert_called_once_with(
                            "http://localhost:2026/internal/sessions/s1/status",
                            "running",
                        )

                    # "idle" called after yield with stop_reason=completed
                    assert mock_status.call_count == 2
                    mock_status.assert_called_with(
                        "http://localhost:2026/internal/sessions/s1/status",
                        "idle",
                        "completed",
                    )

    @pytest.mark.asyncio
    async def test_execution_path_status_callback_on_error(self):
        """Factory calls update_session_status('idle') even when agent errors."""
        mock_ert = MagicMock()
        mock_ert.context = {
            "agent": {
                "model": "fireworks:test",
                "system_prompt": "Test.",
            },
            "status_callback_url": "http://localhost:2026/internal/sessions/s2/status",
        }

        mock_runtime = MagicMock()
        mock_runtime.execution_runtime = mock_ert

        with patch("factory.graph.init_chat_model") as mock_init_model:
            mock_init_model.return_value = MagicMock()

            with patch("factory.graph.create_deep_agent") as mock_create_agent:
                mock_create_agent.return_value = MagicMock()

                with patch("factory.graph._update_session_status") as mock_status:
                    with pytest.raises(RuntimeError, match="boom"):
                        async with graph({}, mock_runtime):
                            raise RuntimeError("boom")

                    # "idle" still called in finally with stop_reason=error
                    assert mock_status.call_count == 2
                    mock_status.assert_called_with(
                        "http://localhost:2026/internal/sessions/s2/status",
                        "idle",
                        "error",
                    )


# ---------------------------------------------------------------------------
# Agent config validation tests
# ---------------------------------------------------------------------------


class TestValidateAgentConfig:
    """Tests for _validate_agent_config()."""

    def test_valid_config_nvidia(self):
        """Valid config with nvidia: prefix passes validation."""
        agent = {"model": "nvidia:nvidia/nemotron-3-super-120b-a22b"}
        _validate_agent_config(agent)

    def test_valid_config_fireworks(self):
        """Valid config with fireworks: prefix passes validation."""
        agent = {"model": "fireworks:accounts/fireworks/models/qwen3-235b-a22b"}
        _validate_agent_config(agent)

    def test_valid_config_openai(self):
        """Valid config with openai: prefix passes validation."""
        agent = {"model": "openai:gpt-4o"}
        _validate_agent_config(agent)

    def test_missing_model_raises(self):
        """Missing 'model' key raises ValueError."""
        with pytest.raises(ValueError, match="missing required field: 'model'"):
            _validate_agent_config({})

    def test_no_provider_prefix_raises(self):
        """Model without provider: prefix raises ValueError."""
        with pytest.raises(ValueError, match="provider:model"):
            _validate_agent_config({"model": "gpt-4o"})

    def test_empty_string_raises(self):
        """Empty model string raises ValueError."""
        with pytest.raises(ValueError, match="provider:model"):
            _validate_agent_config({"model": ""})

    def test_none_model_raises(self):
        """None model raises ValueError."""
        with pytest.raises(ValueError, match="provider:model"):
            _validate_agent_config({"model": None})
