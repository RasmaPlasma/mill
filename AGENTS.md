# AGENTS.md

## Project Overview

Self-hosted clone of Anthropic's Claude Managed Agents (not claude code, claude cowork, claude agents sdk or any other claude product. managed agents is a seperate platform). Extends Aegra (not forking) with LangChain Deep Agents as the agent harness. Users define reusable agent configs, container environments, and run long-lived autonomous sessions with tool use, file operations, code execution, and streaming.

**LLM Provider:** Provider-agnostic via `init_chat_model` prefix routing — every agent must specify model with `provider:model` format (e.g., `nvidia:z-ai/glm-5.1`, `fireworks:accounts/...`, `openai:gpt-4o`). No default model. API keys are derived from the provider prefix (e.g., `nvidia:` → `NVIDIA_API_KEY` from secrets).

## Architecture

```
Platform UI (SvelteKit) → Custom FastAPI Routes → Aegra Server (Agent Protocol)
                                                        ↓
                                                   Factory Graph
                                                        ↓
                                              Deep Agents (agent harness)
                                                        ↓
                                              Sandbox Service (Docker containers)
```

- **Aegra** serves Agent Protocol endpoints + custom routes on port 2026
- **Factory graph** reads everything from context dict, never queries DB
- **Custom routes** resolve config from DB, pass via `client.runs.create(context={...})`
- **Sandbox service** is a separate container — Aegra communicates via HTTP

## Key Files

| File | Purpose |
|------|---------|
| `aegra.json` | Aegra config: graphs, dependencies, http |
| `src/factory/graph.py` | Factory graph — per-request agent construction |
| `src/factory/context.py` | `PlatformContext` Pydantic model (typed context) |
| `src/tools/registry.py` | Tool name → instance mapping |
| `src/mcp_resolve/resolver.py` | MCP server → LangChain tools conversion |
| `src/sandbox/backend.py` | `DockerSandboxBackend` extends `BaseSandbox` |
| `src/custom_routes.py` | FastAPI app mounted alongside Agent Protocol |
| `src/routes/` | CRUD endpoints (agents, sessions, vaults, secrets) |
| `src/db/models.py` | SQLAlchemy models for platform tables |

## Factory Graph Pattern

The factory graph (`src/factory/graph.py`) is the core integration point:

```python
@asynccontextmanager
async def graph(config: dict, runtime: ServerRuntime[PlatformContext]):
    ert = runtime.execution_runtime
    if ert is None:
        yield build_minimal_graph()  # Introspection — schema extraction
        return
    raw_ctx = ert.context
    if isinstance(raw_ctx, PlatformContext):
        ctx = raw_ctx              # Aegra pre-deserializes context
    else:
        ctx = PlatformContext(**raw_ctx)  # Pydantic coercion from dict
    _validate_agent_config(ctx.agent)
    backend = _create_backend(ctx)        # ONE-LINE swap point for Phase 3
    # ... resolve tools, create model, yield agent
```

- Uses `@asynccontextmanager` + `yield` (not `return`)
- Checks `execution_runtime is None` for introspection vs execution
- `PlatformContext` is Pydantic `BaseModel` with `extra="ignore"`
- Aegra pre-deserializes context to `PlatformContext` — check `isinstance` before unpacking
- `_create_backend(ctx)` is the backend swap point (StateBackend → DockerSandboxBackend)

## Context Passing Flow

1. Custom route resolves agent/env/secrets/vault config from DB
2. Calls `client.runs.create(thread_id=..., assistant_id="agent", context={...})`
3. Aegra passes context to factory via `ServerRuntime[T]`
4. Factory: `runtime.execution_runtime.context` → raw dict → `PlatformContext(**raw)`

Note: Aegra may pre-deserialize context to `PlatformContext` — always check `isinstance` before `**raw_ctx`.

## Deep Agents Integration

`create_deep_agent()` returns a compiled LangGraph graph. Built-in tools (write_todos, read_file, write_file, edit_file, ls, glob, grep, execute, task) are added automatically by middleware — do NOT register them in the tool registry.

```python
agent = create_deep_agent(
    model=model,              # Always from context, never default
    system_prompt=prompt,     # From context
    tools=custom_tools,       # Custom + MCP only
    backend=backend,          # NOT sandbox= — sandboxes are a type of backend
)
```

## Conventions

- **Python 3.12+** required
- **No default model** — every agent must specify `provider:model` format explicitly (e.g., `nvidia:z-ai/glm-5.1`, `fireworks:accounts/...`)
- **Context-only factory** — factory graph never queries DB, reads everything from context dict
- **AES-256-GCM** encryption for secrets/vault credentials (master key from env var)
- **Separate Alembic** — `version_table="platform_alembic_version"` to avoid collision with Aegra's tables
- **One credential per MCP server URL per vault**
- **Secrets injected into harness, never into sandbox containers**
- **Secret scope priority** — when multiple secrets share the same name across scopes, resolution follows agent > environment > global
- **Custom routes need `sys.path` fix** — Aegra's app loader doesn't add `./src` to `sys.path` for HTTP apps; `custom_routes.py` must do it manually
- **NO silent fallbacks or silent failures: VERY IMPORTANT** 
- When writing test, NEVER EVER make them more lenient to pass the test and ignore the erorr. NEVER rewrite tests to allow convenient failures. BUT ALSO NEVER EVER BREAK A WORKING FEATURE TO MAKE A TEST PASS.

Profile before diagnosing. Never theorize about performance without actual data. A 30-second freeze was invisible to code review — only the Performance tab revealed scrollToBottom repeating 550 times in 500ms.
"I'm sure" without proof is a lie. Every time I said "I found the root cause," I was wrong. The actual fix was only found after the user forced me to measure.

- Prefer end-state implementations over transitional ones. This is a greenfield project, do NOT add backwards compatibility fallbacks, alias fields, bridge routes or dual shape parses unless the user asks specifically for a migration or compatibility layer. When redisigning config or APIS, remove obsolete shapes instead of silently suporting both old and new contracts.
- Do not hedge for failures.

## Running

```bash
# Local dev
uv sync
docker compose up -d postgres redis
uv run aegra dev

# Docker
docker compose up --build

# Tests
PYTHONPATH=src uv run pytest tests/ -v

# Lint
uv run ruff check src/ tests/
```

### Known Gotchas

- **Custom routes `sys.path`**: Aegra's app loader doesn't add `./src` to `sys.path` when loading `http.app`. `custom_routes.py` must insert it manually at the top.
- **Secret scope priority**: When multiple secrets share the same name (e.g., `NVIDIA_API_KEY` at global, agent, and environment scopes), resolution must follow agent > environment > global priority. The `_resolve_context` function sorts by scope specificity.

### Sandbox Runtime Backends

The sandbox-service supports three container runtimes via the `DOCKER_RUNTIME` env var. Only the agent sandbox containers use the selected runtime; platform infrastructure (Postgres, Redis, Aegra, etc.) stays on the default `runc`.

| Runtime | Isolation | Startup | DNS Notes | Setup |
|---|---|---|---|---|
| `runc` (default) | Namespaces / cgroups | ~10ms | Works with Docker embedded DNS | None |
| `sysbox-runc` | User namespace + procfs virtualization | ~15ms | Works with Docker embedded DNS | Install `sysbox` on host |
| `runsc` (gVisor) | Userspace kernel (Sentry) | ~100ms | **Requires explicit DNS** — set `SANDBOX_DNS_SERVERS` | Install `runsc` + register in `/etc/docker/daemon.json` |

**gVisor on ARM64:** gVisor uses the `ptrace` platform on ARM64 (slower than x86's `systrap`). Expect higher per-syscall overhead for I/O-heavy agent workloads (`pip install`, `npm install`). DNS must be explicit because gVisor's netstack cannot reach Docker's embedded resolver on user-defined bridge networks.

**Sysbox:** A Docker-acquired project that hardens containers via user namespaces and procfs virtualization without a hypervisor. No syscall overhead. No DNS workarounds. Requires `sysbox-mgr` and `sysbox-fs` daemons on the host.

**Switching runtimes:** Unset `DOCKER_RUNTIME` to revert to `runc`. No DB migrations or container state changes required. Existing containers keep their original runtime.

### Sandbox Environment Lifecycle (Production)

**Base image:** `deepagents/sandbox-base:latest` is built from `ubuntu:24.04` with `git`, `nodejs`, `npm`, `python3`, `build-essential`, and common `-dev` libraries preinstalled. This avoids agents wasting time installing basic tooling. The per-environment image layers only the packages specified in the environment config on top of this base.

**Image cache invalidation:** Per-environment images use content-addressable tags (`sandbox-env-{env_id}:{build_key}`) where `build_key` is a truncated SHA-256 of `{base_image, packages}`. Changing packages or the base image triggers a new build automatically. Old hash-tagged images are removed by the cleanup job after 24 hours if unused.

**Network allocation — the 31-network fix:** Docker's default address pools only allow 31 custom bridge networks before throwing "could not find an available, non-overlapping IPv4 address pool". The sandbox service explicitly allocates `/28` subnets from `10.224.0.0/12` (262,144 possible networks). Each environment stores its assigned subnet in `environments.ip_subnet` and reuses it on rebuild.

**Git repository initialization:** Environments can specify `repositories` (list of `{url, branch, path, depth, auth_secret_name}`). When a sandbox container is created, the sandbox service runs a one-time init script via `docker exec` that clones each repo into `/workspace`. Credentials are resolved from platform secrets and passed inline in the HTTPS URL — they are never written to disk inside the container. A marker file `/workspace/.sandbox-init-done` prevents re-cloning on container restart after inactivity.

**Resource cleanup (every 5 minutes):**
| Resource | Action |
|---|---|
| Zombie containers | Remove `platform.managed=true` containers with no matching active session |
| Orphaned volumes | Remove `platform.managed=true` volumes with no attached container |
| Orphaned networks | Remove `platform.managed=true` networks with zero attached containers (running or stopped) |
| Dangling images | Prune untagged images with `platform.managed=true` label |
| Old tagged images | Remove unused environment images older than 24h with no referencing containers |
| Build cache | Run `docker system prune` for build cache |

**We never use `docker network prune`** because Docker 28+ incorrectly removes networks for stopped containers. The cleanup job inspects each network's `Containers` dict directly.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary — each role maps to its canonical name. See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context repo: `CONTEXT-MAP.md` at the root points to per-context `CONTEXT.md` files. See `docs/agents/domain.md`.

## Hard-Won UI Performance Lessons

### Profile First, Diagnose Second

When a UI is slow, **capture a Chrome DevTools Performance profile before touching any code**. The flame chart tells the truth; your theories are probably wrong. In this session, the profile showed `scrollToBottom` + `Recalculate style` repeating 550 times in a 500ms window — the root cause was O(n²) reactive thrashing, not SSE bandwidth or DB queries.

### Proxy Layers Swallow Query Params

When adding `?since` or any query parameter to a proxied SSE/WebSocket endpoint, **always verify the SvelteKit/Express/Nginx proxy forwards it**. The proxy at `ui/src/routes/api/sessions/[id]/events/stream/+server.ts` originally constructed a brand-new URL string and dropped `url.search` on the floor. FastAPI received `since=None`, skipped the warm-up, and only tailed live events.

### Event Streaming Requires Batching

Any UI receiving rapid-fire SSE/WebSocket events must **buffer and flush per `requestAnimationFrame`**. Processing each event synchronously triggers a full Svelte/React render cycle per message. For 550 events, this means 550 DOM flushes. The fix: `queueEvent()` pushes to a plain array; `flushEvents()` runs inside `requestAnimationFrame` and does a single batch update (`allEvents = [...allEvents, ...batch]`). This is the standard pattern across Claude, ChatGPT, Orbit, Roo Code, and every major LLM chat UI.

### Reactive Updates Are Expensive — Batch Them

Svelte 5 runes (`$state`, `$derived`, `$effect`) are fast, but **550 individual reactive updates on a 750-item array is O(n²) work**. Each `allEvents = [...allEvents, item]` triggers: derived recalculation (`filteredEvents`, `uniqueEventTypes`), `$effect` execution (`scrollToBottom`), child component prop updates (`SessionTimelineBar`), and full DOM reconciliation. Batch the array mutation.

### Minimal Fixes First

The actual fixes for the 30-second freeze were: (1) add `url.search` to the proxy fetch URL (2 lines), and (2) batch SSE events in a `requestAnimationFrame` loop (~30 lines). Do not reach for virtualization, pagination, or architectural refactoring until profiling proves the DOM node count itself is the bottleneck.

## Phase Status

| Phase | Status |
|-------|--------|
| 1. Aegra + Factory Graph | **Done** |
| 2. Platform DB + Custom Routes | **Done** |
| 3. Sandbox Service + DockerSandboxBackend | **Done** |
| 4. Platform UI (SvelteKit) | **In Progress** |
| 5. Object Storage (Garage) | Not started |
| 6. Production Hardening | Not started |
| 7. Advanced Features | Not started |

remember to use the questions tool when it is useful