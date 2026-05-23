# Deep Agents Platform

Self-hosted agent orchestration platform. Users define reusable agent configs, container environments, and run long-lived autonomous sessions with tool use, file operations, code execution, and streaming.

## Language

**Agent**:
A reusable configuration for an LLM-powered autonomous worker. Contains model, system prompt, tools, MCP servers, and skills. Agents do not run directly; they are bound to sessions.
_Avoid_: Bot, assistant

**Environment**:
A container template defining packages (pip/npm/apt), networking rules, and resource limits. Used to build per-session sandbox images.
_Avoid_: Template, image

**Session**:
A live binding of an agent to an environment. Owns an Aegra thread (persistence) and a sandbox container (execution). Multiple runs can be queued on a session.
_Avoid_: Conversation, chat, job

**Run**:
A single execution of an agent on a session's thread. Has a unique run_id and produces a stream of events. A session can have many runs over its lifetime.
_Avoid_: Job, task

**Vault**:
A collection of encrypted credentials for MCP server authentication. Each credential maps one MCP server URL to one token. Credentials are write-only in the API.
_Avoid_: Keychain, credential store

**Secret**:
A general-purpose encrypted key-value pair with scope (global, agent-scoped, or environment-scoped). Injected into the agent harness, never into the sandbox container.
_Avoid_: Env var, config

**Factory Graph**:
The per-request agent construction function. Reads everything from PlatformContext and yields a compiled LangGraph graph. Never queries the database.
_Avoid_: Graph builder

**PlatformContext**:
The typed dict passed from custom routes to the factory graph via Aegra's context mechanism. Contains agent config, environment config, secrets, vault credentials, sandbox IDs, and callback URLs.
_Avoid_: Context, config

**Sandbox Service**:
The separate Docker container with Docker socket proxy access. Manages container lifecycle (create, start, stop, destroy) and command execution.
_Avoid_: Executor, runner

**Backend**:
The Deep Agents execution abstraction. Either DockerSandboxBackend (containerized) or StateBackend (in-memory). Not a sandbox; sandboxes are a type of backend.
_Avoid_: Sandbox, executor

**Skill**:
A directory containing a SKILL.md file with YAML frontmatter. Loaded by Deep Agents' SkillsMiddleware into the system prompt. Paths are backend-relative (e.g. /workspace/skills/).
Aegra does not implement SkillsMiddleware so we inject into the system prompt. 
_Avoid_: Capability, plugin

## Relationships

- An **Agent** is referenced by zero or more **Sessions**
- A **Session** binds exactly one **Agent** and optionally one **Environment**
- An **Environment** is referenced by zero or more **Sessions**
- A **Session** can attach zero or more **Vaults** (via session_vaults join table)
- A **Vault** contains zero or more **Credentials**
- A **Credential** maps one **Vault** + one MCP server URL to one encrypted token
- **Secrets** are resolved by scope specificity: agent > environment > global
- A **Factory Graph** receives **PlatformContext** and produces a compiled graph for a single **Run**
- A **Run** belongs to exactly one **Session** (tracked via run_id)

## Example dialogue

> **Dev:** "When a user creates a **Session**, do we need an **Agent**?"
> **Domain expert:** "No — the session can be created without an agent, but you can't send events until one is attached. The agent defines what model and tools the run uses."
>
> **Dev:** "Where do **Secrets** go?"
> **Domain expert:** "Secrets are injected into the **Factory Graph** — they configure the model API key and custom tools. They never reach the **Sandbox Service** or the container."
>
> **Dev:** "Can I delete a **Secret**?"
> **Domain expert:** "No — secrets are soft-archived. The value is encrypted and the record stays for audit, but archived secrets are excluded from resolution."

## Flagged ambiguities

- "skills" was used to mean both Deep Agents runtime skills (backend paths to SKILL.md directories) and the skills.sh ecosystem (registry of agent capabilities). Resolved: the platform runtime uses Deep Agents' skill paths. Phase 7 will integrate with skills.sh as a skill marketplace.
- "model" was used ambiguously: the DB has both `model_id` (FK to llm_models registry) and `model` (raw provider:model string). Resolved: `model` is the canonical runtime specification (provider:model format). `model_id` is a foreign key to the `llm_models` registry; the registry entry provides `display_name` (human-readable label) and the `provider:provider_model` pair that resolves to the canonical runtime specification.
