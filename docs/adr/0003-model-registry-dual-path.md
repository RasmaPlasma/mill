# Agent model specification supports both registry and raw string

Agents must specify a model. Two paths exist, but both must produce a valid `provider:model` string:

- **Registry path (`model_id`):** User selects from the `llm_models` table. The resolved string is `{provider}:{provider_model}` from the registry row. If the registry entry is archived or missing, this is a hard error — the agent config is invalid.
- **Direct path (`model`):** User enters a raw `provider:model` string (e.g. `fireworks:accounts/...`). No registry lookup involved.

`AgentCreate` validation enforces that at least one of `model_id` or `model` is provided. `_resolve_context` resolves `model_id` first; if that registry row is archived, it raises `HTTPException(400)` immediately rather than falling back to `agent.model`, which may be null or stale.

The `llm_models` registry is optional. A team can use direct strings exclusively and never populate the registry.
