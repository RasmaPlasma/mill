# Self-Hosted Claude Managed Agents — Master Plan

## Goal

Build a self-hosted clone of Anthropic's Claude Managed Agents by extending Aegra (not forking) with LangChain Deep Agents as the agent harness. Users define reusable agent configs, container environments, and run long-lived autonomous sessions with tool use, file operations, code execution, and streaming.

## Decisions

| Decision | Choice |
|----------|--------|
| LLM provider | Provider-agnostic via `init_chat_model`. No default model. Every agent specifies explicitly with `provider:model` format (e.g. `fireworks:accounts/...`, `nvidia:nvidia/...`, `openai:gpt-4o`). |
| Tracing | Arize Phoenix now. Migrate to Langfuse later (Phase 7). |
| UI | Pure admin panel (SvelteKit 2 + shadcn-svelte). No chat UI — developer builds their own. |
| Auth | better-auth (replaces Auth.js). Single-tenant global admin for now; multi-tenancy deferred to Phase 6. |
| Sandbox | Full per-session Docker containers via separate sandbox service. Writable root filesystem (read-only removed). |
| Sandbox limits | memory=1g, cpus=1.0, pids-limit=256, no-new-privileges. cap_drop deferred to Phase 6+. |
| Sandbox lifecycle | Stop after 15 min inactivity, destroy on session archive. |
| Sandbox networking | Limited (custom bridge network per environment). Outbound unrestricted until HTTP proxy implemented (Phase 3+). |
| Secrets | PostgreSQL vault + secrets table. AES-256-GCM encryption. Factory graph injects into harness, never into sandbox containers. |
| Secrets lifecycle | Soft archive (archived_at), not hard delete. |
| DB migrations | Separate Alembic with `version_table="platform_alembic_version"`. |
| Factory graph | Context-only. Custom routes resolve config, pass via `client.runs.create(context={...})`. |
| Session concurrency guard | `run_id` stored on session row. Factory graph removes status callback mechanism. Status is informational only. |
| File transfer | Shared volume mount (not docker cp). |
| Docker access | Socket proxy (tecnativa/docker-socket-proxy) with `POST:1` and code-level guard against privileged containers. |
| Proxy + SSO | Existing Traefik + Authelia. Add routing rules for new services. |

## How We Extend Aegra (Not Fork)

Aegra is installed as pip packages (`aegra-cli`, `aegra-api`), NOT built from a git submodule. The same container serves both Aegra's Agent Protocol endpoints AND our custom FastAPI routes on port 2026.

- `aegra.json` mounts custom routes via `http.app` and factory graph via `graphs`
- Aegra migrations apply automatically on startup (`aegra serve`)
- Sandbox service is a separate container — factory graph communicates via HTTP (`DockerSandboxBackend` → sandbox-service API)

## Pinned Versions

### Python (backend)

Requirement: Python 3.12+

| Package | Version | Purpose |
|---------|---------|---------|
| aegra-cli | 0.9.7 | Aegra CLI |
| aegra-api | 0.9.7 | Aegra server (FastAPI + LangGraph runtime) |
| deepagents | 0.5.6 | Agent harness (planning, filesystem, shell, sub-agents) |
| fastapi | 0.136.1 | HTTP framework for custom routes + sandbox service |
| uvicorn | 0.46.0 | ASGI server |
| sqlalchemy | 2.0.49 | ORM for platform tables |
| alembic | 1.18.4 | Database migrations (platform tables) |
| boto3 | 1.43.1 | S3 client for Garage artifact storage |
| docker | 7.1.0 | Docker SDK for Python (sandbox service) |
| langchain-mcp-adapters | 0.2.2 | MCP server integration for Deep Agents |
| tavily-python | 0.7.24 | Web search tool for agents |
| arize-phoenix | 15.1.0 | Tracing SDK (client side) |
| langchain-fireworks | 1.3.0 | Fireworks AI model provider |

### JavaScript/TypeScript (frontend)

Requirement: Node.js 20.9+

| Package | Version | Purpose |
|---------|---------|---------|
| @sveltejs/kit | 2.59.0 | SvelteKit framework |
| svelte | 5.55.5 | UI framework |
| @sveltejs/adapter-node | 5.5.4 | Node.js adapter for Docker deployment |
| tailwindcss | 4.2.4 | CSS framework |
| shadcn-svelte (CLI) | latest | Component registry CLI |
| better-auth | 1.6.9 | Authentication |
| @tanstack/svelte-query | 6.1.27 | Server state management |
| svelte-codemirror-editor | 2.1.0 | Code editor for system prompts |
| zod | 4.4.1 | Schema validation |
| formsnap | latest | Form handling |
| sveltekit-superforms | latest | Form validation |

### Docker Images

| Image | Tag | Purpose |
|-------|-----|---------|
| aegra/aegra | local build | Aegra server (from pip packages, NOT git submodule) |
| pgvector/pgvector | pg18 | PostgreSQL 18 + pgvector 0.8.2 |
| redis | 8.6.2-alpine | Redis job queue + SSE pub/sub |
| arizephoenix/phoenix | 15.1.0 | Trace visualization |
| dxflrs/garage | v2.3.0 | S3-compatible object storage |
| prom/prometheus | v3.11.3 | Metrics scraping |
| tecnativa/docker-socket-proxy | latest | Docker socket proxy |
| traefik | v3.6.15 | Reverse proxy (existing) |
| authelia/authelia | 4.39.17 | SSO (existing) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Traefik (existing — add routing rules for new services)             │
│ Authelia (existing) + better-auth (platform UI auth)                  │
├─────────────────────────────────────────────────────────────────────┤
│ Platform UI (SvelteKit + shadcn-svelte — pure admin panel)           │
│   /agents — Agent registry CRUD                                      │
│   /environments — Environment builder (packages, networking)         │
│   /sessions — Session list, resume, archive                          │
│   /vaults — Vault + credential management                            │
│   /secrets — General-purpose secrets                                 │
│   /traces — Embeds Phoenix UI in iframe                              │
├─────────────────────────────────────────────────────────────────────┤
│ Aegra Server (Agent Protocol backend + Custom FastAPI routes)         │
│   Port 2026 — both Aegra and custom routes on same port              │
│   Factory graph reads PlatformContext, builds Deep Agents graph        │
├─────────────────────────────────────────────────────────────────────┤
│ Sandbox Service (separate container)                                 │
│   HTTP API for container lifecycle + command execution               │
│   Docker access via socket proxy                                     │
├─────────────────────────────────────────────────────────────────────┤
│ Deep Agents (LangGraph agent harness)                                │
│   Planning, Filesystem, Shell, Sub-agents, SkillsMiddleware          │
├─────────────────────────────────────────────────────────────────────┤
│ Phoenix (local tracing) + Prometheus (metrics)                       │
├─────────────────────────────────────────────────────────────────────┤
│ PostgreSQL 18 + pgvector + Redis 8 + Garage (S3)                     │
└─────────────────────────────────────────────────────────────────────┘
```

## What Aegra Provides (zero custom code)

| Feature | Aegra mechanism |
|---------|-----------------|
| Agent Protocol API | `/threads`, `/runs`, `/assistants`, `/store` |
| Streaming | 8 SSE modes with reconnection + Redis pub/sub |
| Persistence | PostgreSQL checkpoints via LangGraph |
| Job queue | Redis BLPOP, 30 concurrent runs/instance, crash recovery |
| Human-in-the-loop | Interrupt before/after nodes, approval gates, state editing |
| Auth framework | JWT/OAuth/Firebase handlers |
| Observability | OpenTelemetry fan-out to Phoenix + OTLP |
| Custom routes | Mount FastAPI app alongside Agent Protocol endpoints |
| Factory graphs | Per-request graph customization via `ServerRuntime` context |
| Semantic store | pgvector embeddings |

## What Aegra Does NOT Provide (we must build)

- Agent registry (CRUD for agent configs with model, tools, MCP servers)
- Environment registry (CRUD for container templates with packages, networking)
- Session-to-environment binding
- Sandbox service (separate container with Docker access)
- Vault + credential management (per-user MCP auth tokens)
- General-purpose secrets store (API keys, env vars)
- Artifact storage API
- The UI

## What Deep Agents Provides (zero custom code)

| Feature | Deep Agents mechanism |
|---------|----------------------|
| Planning | `write_todos` tool for task decomposition |
| Filesystem | `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep` |
| Shell | `execute` tool (pluggable sandbox backend via `BaseSandbox`) |
| Sub-agents | `task` tool for delegated work with context isolation |
| Context management | Auto-summarization at 170k tokens, large output offloading |
| Memory | LangGraph Memory Store for cross-thread persistence |
| MCP support | via `langchain-mcp-adapters` |
| Skills | `SkillsMiddleware` loads `SKILL.md` files from backend paths |

Sub-agent backend inheritance: Sub-agents share the parent's backend instance by default. This means sub-agents operate on the same virtual filesystem and can use the same sandbox. No extra configuration needed.

## Mapping Claude Managed Agents → Our Platform

| Claude Managed Agents | Our Implementation |
|-----------------------|-------------------|
| POST /v1/agents | Custom route → writes to PostgreSQL agents table |
| POST /v1/environments | Custom route → writes to PostgreSQL environments table |
| POST /v1/sessions | Custom route → creates Aegra thread + sandbox container |
| POST /v1/sessions/:id/events | Custom route → resolves config → `client.runs.create(context={...})` |
| GET /v1/sessions/:id/stream | Custom route → proxies `client.runs.join_stream()` as SSE |
| POST /v1/vaults | Custom route → writes to PostgreSQL vaults table |
| POST /v1/vaults/:id/credentials | Custom route → encrypted credential stored in credentials table |
| Agent toolset (bash, file ops, web search) | Deep Agents built-in tools + Tavily (registered as custom tool) |
| Environment container | Docker container spawned by sandbox service |
| Checkpointing | Aegra PostgreSQL checkpoints (automatic) |
| Session tracing | Phoenix via OpenTelemetry (automatic) |
| Vault injection at session time | Factory graph resolves vault credentials from context → MCP connections |
| Secret injection at session time | Factory graph resolves secrets from context → harness (NOT sandbox) |
| Scoped permissions | Factory graph reads permission config from context, passes to Deep Agents |

## External Dependencies

### 1. Arize Phoenix — Observability

Lightweight local tracing. ~1GB RAM. Provides: trace visualization, span inspection, token tracking per session.

Integration:
```
OTEL_TARGETS="PHOENIX"
PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:6006/v1/traces
```

Migration path: When scaling up, add Langfuse v3 alongside Phoenix (`OTEL_TARGETS="PHOENIX,LANGFUSE"`).

### 2. better-auth — Authentication

Replaces Auth.js (deprecated). Framework-agnostic auth for TypeScript with first-class SvelteKit support.

Features: Email/password, social sign-in, passkeys, 2FA, organizations, OIDC, SCIM.

Integration: `hooks.server.ts` with `svelteKitHandler` + `sveltekitCookies` plugin. Session validation in handle hook, populated in `event.locals`.

### 3. Vault + Secrets — PostgreSQL-Native

Two data models in the same PostgreSQL database, both using AES-256-GCM encryption (master key from `PLATFORM_MASTER_KEY` env var):

**Vaults** (matching Claude Managed Agents' vault model):
- Per-user credential collections for MCP server auth
- `vaults` table: id, display_name, metadata
- `credentials` table: id, vault_id, mcp_server_url, auth_type, encrypted_token, encrypted_refresh_token, expires_at
- Write-only: secrets never returned in API responses
- One credential per MCP server URL per vault
- Auto-resolved at session time: custom routes read vault credentials, pass via context dict to factory graph

**Secrets** (general-purpose):
- Key-value pairs for API keys, env vars, non-MCP credentials
- `secrets` table: id, name, encrypted_value, scope (global/agent/environment), archived_at
- Soft archive (not hard delete) for audit history
- Resolved by custom routes at session time, passed via context to factory graph
- Factory graph injects into harness (tool config, model params) — NEVER into sandbox containers

### 4. Garage — S3-Compatible Object Store

Stores: agent artifacts, build caches, file outputs from sandbox sessions.

Deployment: Single container, S3 API on port 3900, admin on 3903, web UI on 3902.

boto3 config:
```python
import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url="http://garage:3900",
    aws_access_key_id="...",
    aws_secret_access_key="...",
    config=Config(
        s3={"addressing_style": "path"},
        region_name="garage",
    ),
)
```

### 5. Prometheus — Metrics

Scrapes Traefik and Aegra /metrics endpoint. Zero custom code.

### 6. Traefik + Authelia (existing)

Already running on the server. Just add routing rules for new services.

Auth boundary:
- Authelia = Traefik-level SSO (reverse proxy auth). Handles authentication for all services behind Traefik.
- better-auth = Platform UI authentication (SvelteKit). Manages user sessions, login forms, OIDC integration.
- Both are needed: Authelia protects the infrastructure, better-auth manages the application-layer users.
- better-auth integrates with Authelia via OIDC (Phase 6).

## What We Must Build Custom

### 1. Platform Database Schema

PostgreSQL tables (separate from Aegra's checkpoint tables). Managed by our own Alembic instance with `version_table="platform_alembic_version"`.

```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY, -- ULID string
    name TEXT NOT NULL,
    model_id TEXT REFERENCES llm_models(id), -- nullable
    model TEXT, -- nullable, raw provider:model string
    system_prompt TEXT,
    tools JSONB DEFAULT '[]',
    mcp_servers JSONB DEFAULT '[]',
    skills JSONB DEFAULT '[]',
    description TEXT,
    metadata JSONB DEFAULT '{}',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ
);

CREATE TABLE llm_models (
    id TEXT PRIMARY KEY, -- ULID string
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_model TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ
);

CREATE TABLE environments (
    id TEXT PRIMARY KEY, -- ULID string
    name TEXT NOT NULL UNIQUE,
    packages JSONB DEFAULT '{}',
    networking JSONB DEFAULT '{"type":"limited","allowed_hosts":[],"allow_package_managers":false}',
    resource_limits JSONB DEFAULT '{"memory":"1g","cpus":1.0,"pids_limit":256}',
    repositories JSONB DEFAULT '[]',
    base_image TEXT,
    ip_subnet TEXT,
    dockerfile_cache TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY, -- ULID string
    agent_id TEXT REFERENCES agents(id),
    environment_id TEXT REFERENCES environments(id),
    run_id TEXT, -- active Aegra run, null when idle
    aegra_thread_id TEXT,
    sandbox_container_id TEXT,
    last_exec_at TIMESTAMPTZ,
    title TEXT,
    status TEXT DEFAULT 'idle',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ
);

CREATE TABLE vaults (
    id TEXT PRIMARY KEY, -- ULID string
    display_name TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ
);

CREATE TABLE credentials (
    id TEXT PRIMARY KEY, -- ULID string
    vault_id TEXT REFERENCES vaults(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    mcp_server_url TEXT NOT NULL,
    auth_type TEXT NOT NULL,
    encrypted_token BYTEA NOT NULL,
    encrypted_refresh_token BYTEA,
    token_endpoint TEXT,
    client_id TEXT,
    scope TEXT,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ,
    UNIQUE(vault_id, mcp_server_url)
);

CREATE TABLE secrets (
    id TEXT PRIMARY KEY, -- ULID string
    name TEXT NOT NULL,
    encrypted_value BYTEA NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ,
    UNIQUE(name, scope)
);

CREATE TABLE session_vaults (
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    vault_id TEXT REFERENCES vaults(id) ON DELETE CASCADE,
    PRIMARY KEY (session_id, vault_id)
);
```

### 2. Custom FastAPI Routes

Mounted via Aegra's `http.app` config in `aegra.json`. All DB operations happen here — factory graph never queries DB directly.

**Session flow:**
1. `POST /v1/sessions` → creates DB record + Aegra thread (via `client.threads.create()`) + sandbox container
2. `POST /v1/sessions/:id/events` → resolves agent/env/secrets/vault config from DB, calls `client.runs.create(thread_id, assistant_id, context={...})`, stores `run_id` on session row, returns `run_id`
3. `GET /v1/sessions/:id/stream` → requires `run_id` query param, proxies `client.runs.join_stream()` as SSE
4. `POST /v1/sessions/:id/archive` → archives Aegra thread, destroys sandbox

**Assistant ID strategy:** All sessions use the single "agent" assistant registered in `aegra.json`. Agent customization (model, tools, system prompt) happens via the context dict. No per-agent Aegra assistants needed.

**Self-referential HTTP:** Custom routes call themselves via `get_client(url="http://localhost:2026")`. Aegra serves both Agent Protocol and custom routes on the same port.

**Partial creation rollback:** If creating a session partially succeeds (sandbox OK but Aegra thread fails), record partial state in DB with `status=failed`. Background job queries for `status=failed` sessions and cleans up orphaned resources. Cleanup ordering: destroy sandbox first, then archive Aegra thread.

**Session concurrency:** `send_events` stores `run_id` on the session row. The `status` field is informational only (UI badges). A periodic reconciliation job checks Aegra run states for stale `run_id`s and clears them. The factory graph no longer uses `status_callback_url`.

| Route | Purpose |
|-------|---------|
| POST /v1/agents | Create agent config (model_id or model required) |
| GET /v1/agents | List agents |
| GET /v1/agents/:id | Get agent detail |
| PATCH /v1/agents/:id | Update agent (creates new version) |
| POST /v1/agents/:id/archive | Archive agent |
| POST /v1/environments | Create environment config |
| GET /v1/environments | List environments |
| GET /v1/environments/:id | Get environment detail |
| POST /v1/sessions | Create session: spawn sandbox + Aegra thread |
| POST /v1/sessions/:id/events | Send message: resolve config → create Aegra run → return run_id |
| GET /v1/sessions/:id/stream | SSE stream: requires run_id query param |
| GET /v1/sessions/:id | Get session status |
| POST /v1/sessions/:id/archive | Archive session + destroy sandbox |
| GET /v1/sessions | List sessions |
| POST /v1/vaults | Create vault |
| GET /v1/vaults | List vaults |
| POST /v1/vaults/:id/credentials | Add credential to vault |
| PATCH /v1/vaults/:id/credentials/:cid | Rotate credential |
| GET /v1/secrets | List secret names (values never returned) |
| POST /v1/secrets | Create/update secret |
| POST /v1/secrets/:id/archive | Archive secret (soft delete) |
| POST /internal/sessions/:id/cleanup | Internal: cleanup session whose sandbox was destroyed |
| GET /internal/sessions/stale | Internal: find sessions with inactive sandboxes |

### 3. Factory Graph

`./src/factory/graph.py` — Exported as `graph` in `aegra.json`. Reads everything from context, never queries DB.

**Key patterns:**
- `@asynccontextmanager` + `yield` (not `return`)
- Checks `execution_runtime is None` for introspection vs execution
- `PlatformContext` is Pydantic `BaseModel` with `extra="ignore"`
- Aegra pre-deserializes context to `PlatformContext` — check `isinstance` before unpacking
- `_create_backend(ctx)` is the backend swap point (StateBackend ↔ DockerSandboxBackend)

**Agent model resolution:**
- If `agent.model_id` is set: lookup `llm_models` row. If archived/missing → `ValueError` (hard error, no fallback)
- If `agent.model` is set: use raw string directly
- `AgentCreate` Pydantic validation enforces: at least one of `model_id` or `model` must be provided

**Skills:** The factory graph receives `ctx.agent.get("skills", [])` but **currently does not pass it** to `create_deep_agent()`. This is a known gap. Phase 7 will integrate with `skills.sh` for skill marketplace + auto-download. For now, power users can manage skill files manually in the sandbox volume.

### 4. Sandbox Service

Separate container with Docker access via socket proxy. HTTP API that Aegra calls.

**sandbox-service/** structure:
- `main.py` — FastAPI app
- `manager.py` — Container lifecycle (create, start, stop, destroy)
- `executor.py` — Command execution (docker exec), file transfer via shared volume
- `cleanup.py` — Periodic zombie container + orphaned volume cleanup (every 5 minutes)

**DockerSandboxBackend** (in `src/sandbox/backend.py`) extends `deepagents.backends.sandbox.BaseSandbox`:
- `execute(command, *, timeout)` — sync, calls sandbox-service via `httpx.Client`
- `upload_files(files)` — sync, writes to shared volume via sandbox-service HTTP API
- `download_files(paths)` — sync, reads from shared volume via sandbox-service HTTP API
- `id` property — returns sandbox container ID

**Security:**
- Writable root filesystem (not read-only) for runtime package installation
- `cap_drop` and `no-new-privileges` applied (deferred to Phase 6+ for full verification)
- Code-level guard in sandbox-service rejects `Privileged=true` container creation
- Socket proxy permissions: `CONTAINERS=1`, `EXEC=1`, `IMAGES=1`, `ALLOW_START=1`, `ALLOW_STOP=1`, `POST=1`, all others disabled

**Resource limits:**
- `--memory=1g` (configurable per environment)
- `--cpus=1.0` (configurable per environment)
- `--pids-limit=256`
- `--security-opt=no-new-privileges`

**Package installation:** Packages from the environment config's `packages` field are installed at **image build time** (Dockerfile), not at runtime. The container root is writable, so additional packages can be installed at runtime via `pip install`, `npm install`, etc.

**Container labels:**
- `platform.managed=true`
- `platform.session_id={session_id}`
- `platform.environment_id={env_id}`
- `platform.agent_id={agent_id}`

**Sandbox lifecycle:**
- **Create:** When session is created. Per-session volume `sandbox-workspace-{session_id}` mounted at `/workspace`.
- **Stop:** After 15 minutes of inactivity (no exec calls). `docker stop`, not `docker rm`.
- **Destroy:** Only when session is archived. `docker rm` + `docker volume rm`.
- **Restart:** If sandbox is stopped and session receives new event, `docker start` on existing container. Volume persists.
- **Inactivity detection:** Sandbox service tracks `last_exec_at`. Background job checks every 5 minutes.

**Networking:**
- Custom Docker bridge network per environment: `sandbox-env-{environment_id}`
- `/28` subnets from `10.224.0.0/12` (262,144 possible networks)
- Outbound network unrestricted until HTTP proxy implemented (Phase 3+ security gap)

### 5. Platform UI (SvelteKit — Pure Admin Panel)

No chat interface. Developer builds their own UI on top of the API.

**Existing pages:**
- `/agents` — Agent list, create/edit with CodeMirror for system prompt
- `/environments` — Environment list, create/edit with package picker
- `/models` — LLM model registry CRUD
- `/login` — better-auth email/password sign-in/sign-up
- `/` — Dashboard with counts

**Missing pages (Phase 4 remaining):**
- `/sessions` — Session list, create form, detail with basic message input + stream
- `/vaults` — Vault list, create, credential CRUD
- `/secrets` — Secret list, create, archive
- `/traces` — Phoenix iframe
- `/api/sessions/[id]/stream` — SSE proxy endpoint

**Priority order:** Sessions → Vaults → Secrets → Traces

**Tech stack:**
- SvelteKit 2 + TypeScript (Node.js 20.9+ required)
- Tailwind CSS v4 + shadcn-svelte
- better-auth (authentication via `better-auth/svelte-kit`)
- TanStack Query for Svelte
- SvelteKit form actions + Formsnap + SuperForms + Zod
- CodeMirror 6 via `svelte-codemirror-editor`
- `adapter-node` for Docker deployment

**Auth:** `hooks.server.ts` with `svelteKitHandler` + `sveltekitCookies`. Session validation in handle hook, populated in `event.locals`.

**SSE proxy:** `/api/sessions/[id]/stream/+server.ts` using `fetch()` with `response.body` (ReadableStream). Handles reconnection (Last-Event-ID), error events, run completion. `export const runtime = 'nodejs'` for long-lived connections.

**CSRF protection:** `ORIGIN` env var for SvelteKit's built-in CSRF protection.

**Cookie forwarding:** Server-side API calls (`+page.server.ts`) currently do not forward the `Cookie` header to Aegra. Acceptable while `AUTH_TYPE=noop`. When switching to real auth in Phase 6, all `apiFetch` calls must forward cookies.

## Docker Compose Stack

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg18
    env_file: .env
    ports: ["5432:5432"]
    volumes: [pg_data:/var/lib/postgresql]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:8.6.2-alpine
    ports: ["6379:6379"]
    volumes: [redis_data:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  phoenix:
    image: arizephoenix/phoenix:15.1.0
    ports: ["6006:6006", "4317:4317"]
    environment:
      PHOENIX_PORT: 6006

  docker-proxy:
    image: tecnativa/docker-socket-proxy:latest
    environment:
      CONTAINERS: 1
      EXEC: 1
      IMAGES: 1
      POST: 1
      ALLOW_START: 1
      ALLOW_STOP: 1
      AUTH: 0
      BUILD: 1
      COMMIT: 0
      CONFIGS: 0
      DISTRIBUTION: 0
      EVENTS: 1
      GRPC: 0
      INFO: 0
      NETWORKS: 1
      NODES: 0
      PLUGINS: 0
      SECRETS: 0
      SERVICES: 0
      SESSION: 0
      SWARM: 0
      SYSTEM: 0
      TASKS: 0
      VOLUMES: 1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro

  sandbox-service:
    build: ./sandbox-service
    ports: ["8090:8090"]
    environment:
      PORT: 8090
      DOCKER_HOST: tcp://docker-proxy:2375
      SANDBOX_API_KEY: ${SANDBOX_API_KEY}
      PLATFORM_URL: http://aegra:2026
      DOCKER_RUNTIME: ${DOCKER_RUNTIME:-}
      SANDBOX_DNS_SERVERS: ${SANDBOX_DNS_SERVERS:-}
    depends_on: [docker-proxy]
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import httpx; r = httpx.get('http://localhost:8090/health'); exit(0 if r.status_code == 200 else 1)\""]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  migrate-platform:
    build:
      context: .
      dockerfile: Dockerfile
    env_file: .env
    environment:
      POSTGRES_HOST: postgres
    depends_on:
      postgres:
        condition: service_healthy
    command: ["alembic", "-c", "src/db/alembic.ini", "upgrade", "head"]
    restart: "no"
    volumes:
      - ./src:/app/src:ro

  aegra:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "2026:2026"
    env_file: .env
    environment:
      POSTGRES_HOST: postgres
      REDIS_BROKER_ENABLED: "true"
      REDIS_URL: redis://redis:6379/0
      SANDBOX_SERVICE_URL: http://sandbox-service:8090
      SANDBOX_API_KEY: ${SANDBOX_API_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrate-platform:
        condition: service_completed_successfully
      sandbox-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:2026/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    volumes:
      - ./aegra.json:/app/aegra.json:ro
      - ./src:/app/src:ro

  platform-ui:
    build: ./ui
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      HOST: 0.0.0.0
      PORT: 3000
      ORIGIN: ${PLATFORM_ORIGIN:-http://localhost:3000}
      API_BASE_URL: ${API_BASE_URL:-http://aegra:2026}
      DATABASE_URL: ${DATABASE_URL}
      PLATFORM_MASTER_KEY: ${PLATFORM_MASTER_KEY}
    depends_on:
      aegra:
        condition: service_healthy

volumes:
  pg_data:
  redis_data:
```

Note: Traefik + Authelia are already running on the host. Add routing rules for:
- `platform.yourdomain.com` → localhost:3000 (Platform UI)
- `aegra.yourdomain.com` → localhost:2026 (Aegra API)
- `phoenix.yourdomain.com` → localhost:6006 (Phoenix UI)
- `garage.yourdomain.com` → localhost:3902 (Garage S3 Web UI)
- `garage-admin.yourdomain.com` → localhost:3903 (Garage Admin API)

## Implementation Phases

| Phase | Status |
|-------|--------|
| 1. Aegra + Factory Graph | Done |
| 2. Platform DB + Custom Routes | Done |
| 3. Sandbox Service + DockerSandboxBackend | Done |
| 4. Platform UI (SvelteKit) | **Partial** |
| 5. Object Storage (Garage) | Not started |
| 6. Production Hardening | Not started |
| 7. Advanced Features | Not started |

### Phase 4 What's Missing

- `/sessions` — list, create, detail with basic message input + stream
- `/vaults` — list, create, credential CRUD
- `/secrets` — list, create, archive
- `/traces` — Phoenix iframe
- `/api/sessions/[id]/stream` — SSE proxy endpoint

**Priority order:** Sessions → Vaults → Secrets → Traces

### Phase 5: Object Storage

Goal: Artifact storage for agent file outputs.

- Deploy Garage, configure buckets
- Build artifact API (upload/download via boto3 with path-style addressing)
- Wire sandbox containers with Garage access

How agents write to Garage: Agents don't write directly to S3. Instead, the sandbox service exposes a `/sandboxes/:id/artifacts` endpoint that proxies uploads to Garage.

### Phase 6: Production Hardening

Goal: Metrics, SSO integration, production config.

- Add Prometheus metrics scraping for Aegra + Traefik
- Add routing rules to existing Traefik for new services
- Add better-auth SSO integration with Authelia OIDC
- Production Docker Compose with health checks and restarts
- Web search integration (Tavily)
- End-to-end testing

### Phase 7: Advanced Features

- MCP server support in agent configs (vault credential injection)
- Agent skills system (integrate with `skills.sh` registry)
- Multi-agent orchestration (callable agents)
- Cron/scheduled sessions (when Aegra adds native cron)
- Migrate from Phoenix to Langfuse v3
- Agent versioning UI with diff view

## File Structure

```
deep-agents/
├── aegra.json                    # Aegra config
├── docker-compose.yml
├── Dockerfile                   # Platform + Aegra container
├── pyproject.toml
├── .env
├── CONTEXT.md                   # Domain glossary
├── docs/
│   ├── MASTER-PLAN.md           # This file
│   └── adr/
│       ├── 0001-run-id-concurrency-guard.md
│       ├── 0002-writable-sandbox-root.md
│       └── 0003-model-registry-dual-path.md
├── src/                         # Custom code
│   ├── custom_routes.py
│   ├── factory/graph.py
│   ├── factory/context.py
│   ├── routes/
│   ├── sandbox/backend.py
│   ├── mcp_resolve/resolver.py
│   ├── tools/registry.py
│   └── db/
│       ├── models.py
│       ├── crypto.py
│       └── alembic/
├── sandbox-service/
│   ├── main.py
│   ├── manager.py
│   ├── executor.py
│   ├── cleanup.py
│   ├── Dockerfile
│   ├── Dockerfile.base
│   └── requirements.txt
└── ui/                          # SvelteKit 2
    ├── package.json
    ├── svelte.config.js
    └── src/
```

## Verification Commands

```bash
# Tests
PYTHONPATH=src uv run pytest tests/ -v

# Local dev
uv sync
docker compose up -d postgres redis
uv run aegra dev

# Docker
docker compose up --build

# Lint
uv run ruff check src/ tests/
```

## Known Gaps

1. **Factory graph does not pass `skills`** to `create_deep_agent()`. The `skills` array from `ctx.agent` is silently ignored. Phase 7 will fix this with `skills.sh` integration.
2. **Cookie forwarding** not implemented in UI server-side API calls. Works while `AUTH_TYPE=noop`. Required for Phase 6.
3. **cap_drop** and full security hardening deferred to Phase 6+.
4. **HTTP proxy for sandbox networking** not implemented. Sandboxes have unrestricted outbound network access.