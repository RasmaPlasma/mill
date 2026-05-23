"""ULID resource ID generator with type prefixes.

Matches Cloud Managed Agents ID format: {type}_{ulid}
e.g., agent_01HqR2k7vXbZ9mNpL3wYcT8f, sesn_01HqR2k7vXbZ9mNpL3wYcT8f

Uses python-ulid for monotonic generation within the same millisecond.
All IDs are stored as strings in PostgreSQL Text columns.
"""

from ulid import ULID

_PREFIXES = {
    "agent": "agent_",
    "session": "sesn_",
    "environment": "env_",
    "vault": "vlt_",
    "credential": "vcrd_",
    "secret": "scrt_",
    "llm_model": "llmm_",
}


def generate(resource_type: str) -> str:
    """Generate a type-prefixed ULID string.

    Args:
        resource_type: One of 'agent', 'session', 'environment',
            'vault', 'credential', 'secret'.

    Returns:
        A string like ``agent_01HqR2k7vXbZ9mNpL3wYcT8f``.

    Raises:
        ValueError: If resource_type is not a known prefix.
    """
    prefix = _PREFIXES.get(resource_type)
    if prefix is None:
        raise ValueError(
            f"Unknown resource type: {resource_type!r}. "
            f"Known types: {list(_PREFIXES.keys())}"
        )
    return prefix + str(ULID()).lower()
