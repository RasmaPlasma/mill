"""Session management routes — /v1/sessions.

Session lifecycle:
  POST /                    → create DB record + Aegra thread + sandbox container
  POST /{id}/events         → resolve config → ensure sandbox running → client.runs.create
                              → start background stream consumer → return run_id
  GET  /{id}/events/stream  → session-level SSE via Redis pub/sub + DB replay
  GET  /{id}/events         → paginated event history
  POST /{id}/archive        → archive thread + destroy sandbox
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from langgraph_sdk import get_client
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.crypto import decrypt
from db.engine import get_db, get_session_factory
from db.models import (
    Agent,
    Credential,
    Environment,
    Event,
    LLMModel,
    Secret,
    Session,
    SessionVault,
    Vault,
)
from events.bus import RedisStreamBus
from redis.exceptions import TimeoutError as RedisTimeoutError
from schemas.sessions import (
    EventListResponse,
    EventResponse,
    SessionCreate,
    SessionEventCreate,
    SessionEventResponse,
    SessionListResponse,
    SessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/sessions", tags=["Sessions"])

# Lazy-initialized Aegra SDK client — self-referential HTTP to localhost:2026.
_aegra_client = None


def _get_aegra_client():
    global _aegra_client
    if _aegra_client is None:
        _aegra_client = get_client(url="http://localhost:2026")
    return _aegra_client


def _to_response(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        agent_id=session.agent_id,
        environment_id=session.environment_id,
        vault_ids=[v.id for v in session.vaults],
        aegra_thread_id=session.aegra_thread_id,
        sandbox_container_id=session.sandbox_container_id,
        last_exec_at=session.last_exec_at,
        title=session.title,
        repositories=session.repositories or [],
        skill_repos=session.skill_repos or [],
        status=session.status,
        stop_reason=session.stop_reason,
        created_at=session.created_at,
        updated_at=session.updated_at,
        archived_at=session.archived_at,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_session(session_id: str, db: AsyncSession) -> Session:
    stmt = (
        select(Session)
        .options(selectinload(Session.vaults))
        .where(Session.id == session_id, Session.archived_at.is_(None))
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.refresh(session)
    return session


def _sandbox_url() -> str:
    return os.environ.get("SANDBOX_SERVICE_URL", "http://sandbox-service:8090")


def _sandbox_headers() -> dict[str, str]:
    api_key = os.environ.get("SANDBOX_API_KEY", "")
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


async def _destroy_sandbox(container_id: str) -> bool:
    """Destroy a sandbox container and its volume.

    Returns True on success (or 404 already gone), False on failure.
    """

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{_sandbox_url()}/sandboxes/{container_id}",
                headers=_sandbox_headers(),
                timeout=30.0,
            )
            if resp.status_code in (204, 404):
                return True
            logger.warning(
                "Destroy sandbox %s returned %s: %s",
                container_id[:12],
                resp.status_code,
                resp.text,
            )
            return False
    except Exception as exc:
        logger.warning("Failed to destroy sandbox %s: %s", container_id[:12], exc)
        return False


async def _resolve_context(session: Session, db: AsyncSession) -> dict:
    """Build the full context dict for a factory-graph run.

    Resolves agent config, environment config, vault credentials, and
    secrets from the DB.  Returns a dict that will become
    ``PlatformContext`` inside the factory graph.
    """

    agent = None
    if session.agent_id:
        agent_row = await db.execute(
            select(Agent).where(
                Agent.id == session.agent_id, Agent.archived_at.is_(None)
            )
        )
        agent = agent_row.scalar_one_or_none()
        if agent is None:
            raise HTTPException(
                status_code=400, detail="Referenced agent not found or archived"
            )

    environment = {}
    env = None
    repo_secrets: dict[str, str] = {}
    if session.environment_id:
        env_row = await db.execute(
            select(Environment).where(
                Environment.id == session.environment_id,
                Environment.archived_at.is_(None),
            )
        )
        env = env_row.scalar_one_or_none()
        if env is None:
            raise HTTPException(
                status_code=400, detail="Referenced environment not found or archived"
            )

        # Resolve repository secrets with scope priority
        for repo in env.repositories or []:
            secret_name = repo.get("auth_secret_name")
            if secret_name:
                secret_row = await db.execute(
                    select(Secret).where(
                        Secret.name == secret_name,
                        Secret.scope.in_(
                            [
                                "global",
                                f"environment:{env.id}",
                                f"agent:{session.agent_id or ''}",
                            ]
                        ),
                    )
                )
                matched = sorted(
                    secret_row.scalars().all(),
                    key=lambda s: {
                        "global": 0,
                        f"environment:{env.id}": 1,
                        f"agent:{session.agent_id or ''}": 2,
                    }.get(s.scope, 99),
                    reverse=True,
                )
                if matched:
                    try:
                        repo_secrets[secret_name] = decrypt(matched[0].encrypted_value)
                    except Exception:
                        logger.warning("Failed to decrypt repo secret %s", secret_name)

        merged_repositories = (env.repositories or []) + (session.repositories or [])
        merged_skill_repos = (env.skill_repos or []) + (session.skill_repos or [])

        environment = {
            "id": env.id,
            "packages": env.packages or {},
            "networking": env.networking or {},
            "resource_limits": env.resource_limits or {},
            "repositories": merged_repositories,
            "skill_repos": merged_skill_repos,
            "ip_subnet": env.ip_subnet,
            "base_image": env.base_image,
        }

    vault_credentials: dict[str, str] = {}
    vault_ids = [v.id for v in session.vaults]
    if vault_ids:
        creds_result = await db.execute(
            select(Credential)
            .join(Vault, Credential.vault_id == Vault.id)
            .where(
                Credential.vault_id.in_(vault_ids),
                Credential.archived_at.is_(None),
                Vault.archived_at.is_(None),
            )
        )
        for cred in creds_result.scalars().all():
            try:
                token = decrypt(cred.encrypted_token)
                vault_credentials[cred.id] = token
            except Exception:
                logger.warning(
                    "Failed to decrypt credential %s for vault %s",
                    cred.id,
                    cred.vault_id,
                )

    secrets_dict: dict[str, str] = {}
    scopes = ["global"]
    if session.environment_id:
        scopes.append(f"environment:{session.environment_id}")
    if agent:
        scopes.append(f"agent:{agent.id}")

    scope_priority = {s: i for i, s in enumerate(scopes)}

    secrets_result = await db.execute(select(Secret).where(Secret.scope.in_(scopes)))
    all_secrets = sorted(
        secrets_result.scalars().all(),
        key=lambda s: scope_priority.get(s.scope, 99),
    )
    for secret in all_secrets:
        try:
            value = decrypt(secret.encrypted_value)
            secrets_dict[secret.name] = value
        except Exception:
            logger.warning("Failed to decrypt secret %s", secret.id)

    if "SANDBOX_API_KEY" not in secrets_dict:
        env_sandbox_key = os.environ.get("SANDBOX_API_KEY")
        if env_sandbox_key:
            secrets_dict["SANDBOX_API_KEY"] = env_sandbox_key

    resolved_model = ""
    if agent and agent.model_id:
        model_row = await db.execute(
            select(LLMModel).where(
                LLMModel.id == agent.model_id, LLMModel.archived_at.is_(None)
            )
        )
        llm_model = model_row.scalar_one_or_none()
        if llm_model:
            resolved_model = f"{llm_model.provider}:{llm_model.provider_model}"

    if not resolved_model or ":" not in resolved_model:
        raise HTTPException(
            status_code=400,
            detail=f"Agent model is not configured correctly (resolved: {resolved_model!r}). "
            "Ensure the agent has a valid model_id referencing a registered LLM model.",
        )

    agent_config = {}
    if agent:
        merged_skill_repos = []
        if env and env.skill_repos:
            merged_skill_repos.extend(env.skill_repos)
        if session.skill_repos:
            merged_skill_repos.extend(session.skill_repos)
        skills_paths: list[str] = ["/workspace/.agents/skills/"] if merged_skill_repos else []
        agent_config = {
            "model": resolved_model,
            "system_prompt": agent.system_prompt,
            "tools": agent.tools or [],
            "mcp_servers": agent.mcp_servers or [],
            "skills": skills_paths,
        }

    return {
        "agent": agent_config,
        "environment": environment,
        "secrets": secrets_dict,
        "vault_credentials": vault_credentials,
        "sandbox_url": _sandbox_url(),
        "sandbox_id": session.sandbox_container_id or "",
        "status_callback_url": f"http://localhost:2026/internal/sessions/{session.id}/status",
        "session_id": session.id,
        "agent_id": session.agent_id or "",
        "repo_secrets": repo_secrets,
        "platform_url": "http://localhost:2026",
    }


async def _save_event(
    session_id: str,
    run_id: str | None,
    event_type: str,
    payload: dict,
) -> Event:
    """Save an event to the DB using a standalone session.

    Used by the background stream consumer which runs outside FastAPI DI.
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        event = Event(
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
        )
        db.add(event)
        await db.commit()
        return event


async def _load_seen_ids(session_id: str) -> tuple[set[str], set[str], set[str]]:
    """Load previously emitted AI message IDs and tool IDs from DB for deduplication.

    Called at the start of each run's stream consumer so that AI messages
    and tool calls already synthesized in prior runs are skipped (LangGraph
    `values` events contain the full conversation history).

    Returns:
        (seen_msg_ids, seen_tool_use_ids, seen_tool_result_ids)
    """
    seen_msg_ids: set[str] = set()
    seen_tool_use_ids: set[str] = set()
    seen_tool_result_ids: set[str] = set()
    session_factory = get_session_factory()
    async with session_factory() as db:
        # AI messages and thinking
        stmt1 = (
            select(Event)
            .where(
                Event.session_id == session_id,
                Event.event_type.in_(["agent.message", "agent.thinking"]),
            )
        )
        result1 = await db.execute(stmt1)
        for event in result1.scalars().all():
            msg_id = event.payload.get("message_id") if event.payload else None
            if msg_id:
                seen_msg_ids.add(msg_id)

        # Tool calls
        stmt2 = (
            select(Event)
            .where(
                Event.session_id == session_id,
                Event.event_type == "agent.tool_use",
            )
        )
        result2 = await db.execute(stmt2)
        for event in result2.scalars().all():
            tool_id = event.payload.get("tool_use_id") if event.payload else None
            if tool_id:
                seen_tool_use_ids.add(tool_id)

        # Tool results
        stmt3 = (
            select(Event)
            .where(
                Event.session_id == session_id,
                Event.event_type == "agent.tool_result",
            )
        )
        result3 = await db.execute(stmt3)
        for event in result3.scalars().all():
            tool_id = event.payload.get("tool_use_id") if event.payload else None
            if tool_id:
                seen_tool_result_ids.add(tool_id)

    return seen_msg_ids, seen_tool_use_ids, seen_tool_result_ids


def _is_cma_event_type(event_type: str) -> bool:
    """Return True if event_type is a CMA event (not a raw LangGraph event)."""
    return event_type.startswith(("user.", "agent.", "session.", "span."))


def _synthesize_cma_events(
    raw_event_type: str,
    raw_data: dict,
    run_id: str,
    raw_event_id: str,
    seen_msg_ids: set[str],
    seen_tool_use_ids: set[str],
    seen_tool_result_ids: set[str],
    usage_emitted: bool,
) -> tuple[list[dict], set[str], set[str], set[str], bool]:
    """Transform a raw LangGraph event into one or more CMA events.

    Returns:
        (cma_events, updated_seen_msg_ids, updated_seen_tool_use_ids, updated_seen_tool_result_ids, updated_usage_emitted)
    """
    cma_events: list[dict] = []
    updated_seen = set(seen_msg_ids)
    updated_seen_tool_use = set(seen_tool_use_ids)
    updated_seen_tool_result = set(seen_tool_result_ids)
    updated_usage = usage_emitted

    if raw_event_type == "values":
        messages = raw_data.get("messages", [])
        for idx, msg in enumerate(messages):
            msg_type = msg.get("type") or msg.get("_type")

            # ---- AI messages: thinking + content ----
            if msg_type == "ai":
                msg_id = msg.get("id") or msg.get("_id")
                if not msg_id:
                    msg_id = f"{run_id}-msg-{idx}"
                if msg_id not in updated_seen:
                    updated_seen.add(msg_id)

                    reasoning = msg.get("additional_kwargs", {}).get("reasoning_content", "")
                    if reasoning:
                        cma_events.append({
                            "event_type": "agent.thinking",
                            "payload": {
                                "message_id": msg_id,
                                "content": reasoning,
                            },
                            "id": f"{raw_event_id}-thinking-{idx}",
                        })

                    content = msg.get("content", "")
                    if content:
                        cma_events.append({
                            "event_type": "agent.message",
                            "payload": {
                                "message_id": msg_id,
                                "content": content,
                                "role": "assistant",
                            },
                            "id": f"{raw_event_id}-msg-{idx}",
                        })

                # Tool calls attached to this AI message
                # Extracted OUTSIDE the msg_id dedup block because tool_calls
                # may be added to an already-seen AI message in a later values event.
                tool_calls = msg.get("tool_calls", [])
                for tidx, tc in enumerate(tool_calls):
                    tool_call_id = tc.get("id")
                    if not tool_call_id:
                        continue
                    if tool_call_id in updated_seen_tool_use:
                        continue
                    updated_seen_tool_use.add(tool_call_id)
                    cma_events.append({
                        "event_type": "agent.tool_use",
                        "payload": {
                            "tool_use_id": tool_call_id,
                            "tool_name": tc.get("name") or tc.get("function", {}).get("name") or "unknown_tool",
                            "input": tc.get("args") or tc.get("arguments") or tc.get("function", {}).get("arguments") or {},
                        },
                        "id": f"{raw_event_id}-tool-{tidx}",
                    })

            # ---- Tool results ----
            elif msg_type == "tool":
                tool_call_id = msg.get("tool_call_id")
                if not tool_call_id:
                    tool_call_id = msg.get("id") or f"{run_id}-tool-{idx}"
                if tool_call_id not in updated_seen_tool_result:
                    updated_seen_tool_result.add(tool_call_id)
                    cma_events.append({
                        "event_type": "agent.tool_result",
                        "payload": {
                            "tool_use_id": tool_call_id,
                            "tool_name": msg.get("name") or msg.get("tool_name") or "unknown_tool",
                            "output": msg.get("content") or msg.get("output") or msg.get("result") or msg,
                            "status": "success",
                        },
                        "id": f"{raw_event_id}-toolres-{idx}",
                    })

        usage = raw_data.get("usage_metadata")
        if usage and not updated_usage:
            updated_usage = True
            cma_events.append({
                "event_type": "span.model_request_end",
                "payload": {
                    "model_usage": {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                },
                "id": f"{raw_event_id}-usage",
            })

    elif raw_event_type == "on_tool_start":
        tool_use_id = raw_data.get("id") or f"{raw_event_id}-tool"
        cma_events.append({
            "event_type": "agent.tool_use",
            "payload": {
                "tool_use_id": tool_use_id,
                "tool_name": raw_data.get("name") or "unknown_tool",
                "input": raw_data.get("args") or raw_data.get("input") or {},
            },
            "id": raw_event_id,
        })

    elif raw_event_type == "on_tool_end":
        tool_use_id = raw_data.get("id") or f"{raw_event_id}-tool"
        cma_events.append({
            "event_type": "agent.tool_result",
            "payload": {
                "tool_use_id": tool_use_id,
                "tool_name": raw_data.get("name") or "unknown_tool",
                "output": raw_data.get("output") or raw_data.get("result") or raw_data,
                "status": "success",
            },
            "id": raw_event_id,
        })

    elif raw_event_type == "error":
        cma_events.append({
            "event_type": "session.error",
            "payload": {
                "error": {
                    "type": "run_error",
                    "message": raw_data.get("detail") or raw_data.get("error") or str(raw_data),
                    "retry_status": "fatal",
                },
            },
            "id": raw_event_id,
        })

    elif raw_event_type == "end":
        cma_events.append({
            "event_type": "session.status_idle",
            "payload": {
                "stop_reason": "completed",
            },
            "id": raw_event_id,
        })

    return cma_events, updated_seen, updated_seen_tool_use, updated_seen_tool_result, updated_usage


async def _consume_run_stream(session_id: str, thread_id: str, run_id: str):
    """Background task: consume Aegra run stream, save raw + CMA to DB, publish CMA to Redis.

    This runs as an asyncio.create_task() after POST /events creates the run.
    Uses direct HTTP to Aegra's stream endpoint to avoid SDK/request-context issues.

    Raw LangGraph events are saved to DB for audit but never published to Redis.
    Only synthesized CMA events are published to the Redis Stream for live SSE.
    """
    logger.info("[consume] starting session=%s run=%s", session_id, run_id)
    bus = RedisStreamBus()
    seen_msg_ids, seen_tool_use_ids, seen_tool_result_ids = await _load_seen_ids(session_id)
    usage_emitted = False
    tool_counter = 0

    async def _save_silent(event_type: str, payload: dict) -> Event | None:
        try:
            return await _save_event(session_id, run_id, event_type, payload)
        except Exception as exc:
            logger.error("[consume] save failed: %s", exc)
            return None

    async def _publish_cma(event_type: str, payload: dict, event_id: str | None = None):
        """Save CMA event to DB and publish to Redis Stream."""
        saved = await _save_silent(event_type, payload)
        if saved is None:
            return
        try:
            await bus.append(session_id, {
                "id": saved.id,
                "type": event_type,
                "data": payload,
                "run_id": run_id,
                "timestamp": saved.created_at.isoformat() if saved.created_at else datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.error("[consume] CMA publish failed: %s", exc)

    try:
        url = f"http://localhost:2026/threads/{thread_id}/runs/{run_id}/stream"
        logger.info("[consume] GET %s", url)

        async with httpx.AsyncClient() as http_client:
            async with http_client.stream(
                "GET",
                url,
                params={"cancel_on_disconnect": "false"},
                headers={"Accept": "text/event-stream"},
                timeout=httpx.Timeout(60.0, read=300.0),
            ) as resp:
                logger.info("[consume] response status=%s", resp.status_code)
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(f"Stream HTTP {resp.status_code}: {body.decode()}")

                buffer = ""
                async for raw in resp.aiter_text():
                    buffer += raw
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        event = _parse_sse_block(block)
                        if not event:
                            continue

                        raw_event_type = event.get("event", "message")
                        raw_data_str = event.get("data", "")
                        raw_event_id = event.get("id", "")
                        try:
                            raw_data = json.loads(raw_data_str) if raw_data_str else {}
                        except json.JSONDecodeError:
                            raw_data = {"raw": raw_data_str}
                        if not isinstance(raw_data, dict):
                            raw_data = {"raw": str(raw_data)}

                        logger.debug("[consume] raw_event=%s data_keys=%s", raw_event_type, list(raw_data.keys()))

                        # 1. Save raw event to DB (audit trail)
                        await _save_silent(raw_event_type, raw_data)

                        # 2. Synthesize and publish CMA events
                        cma_events, seen_msg_ids, seen_tool_use_ids, seen_tool_result_ids, usage_emitted = _synthesize_cma_events(
                            raw_event_type,
                            raw_data,
                            run_id,
                            raw_event_id or f"evt-{tool_counter}",
                            seen_msg_ids,
                            seen_tool_use_ids,
                            seen_tool_result_ids,
                            usage_emitted,
                        )
                        tool_counter += 1

                        for cma in cma_events:
                            await _publish_cma(
                                cma["event_type"],
                                cma["payload"],
                                cma.get("id"),
                            )

        logger.info("[consume] stream ended session=%s run=%s", session_id, run_id)

    except Exception as exc:
        logger.error("[consume] error session=%s run=%s: %s", session_id, run_id, exc, exc_info=True)
        # Emit CMA error + idle events on consumer failure
        error_payload = {
            "error": {
                "type": "consumer_error",
                "message": f"{type(exc).__name__}: {exc}",
                "retry_status": "fatal",
            },
        }
        await _publish_cma("session.error", error_payload)
        await _publish_cma("session.status_idle", {"stop_reason": "error"})


def _parse_sse_block(text: str) -> dict | None:
    """Parse one SSE event block into a dict."""
    lines = text.strip().split("\n")
    event: dict[str, str] = {}
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("event:"):
            event["event"] = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif line.startswith("id:"):
            event["id"] = line[3:].strip()
    if data_lines:
        event["data"] = "\n".join(data_lines)
    return event if data_lines or "event" in event else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a session: validate refs, create DB record + Aegra thread + sandbox.

    Creates DB record FIRST (rollback-safe) — if Aegra thread creation
    fails, the record exists with status=failed for cleanup.
    """
    # Validate agent exists
    if body.agent_id:
        agent_row = await db.execute(
            select(Agent).where(Agent.id == body.agent_id, Agent.archived_at.is_(None))
        )
        if agent_row.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Agent not found or archived")

    # Validate environment exists
    if body.environment_id:
        env_row = await db.execute(
            select(Environment).where(
                Environment.id == body.environment_id,
                Environment.archived_at.is_(None),
            )
        )
        if env_row.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=400, detail="Environment not found or archived"
            )

    # Validate vault_ids reference existing, non-archived vaults
    if body.vault_ids:
        vaults_result = await db.execute(
            select(Vault).where(
                Vault.id.in_(body.vault_ids),
                Vault.archived_at.is_(None),
            )
        )
        found_ids = {v.id for v in vaults_result.scalars().all()}
        missing = set(body.vault_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Vaults not found or archived: {sorted(missing)}",
            )

    session = Session(
        agent_id=body.agent_id,
        environment_id=body.environment_id,
        title=body.title,
        repositories=body.repositories,
        skill_repos=body.skill_repos,
        status="creating",
    )
    db.add(session)
    await db.flush()

    if body.vault_ids:
        for vid in body.vault_ids:
            db.add(SessionVault(session_id=session.id, vault_id=vid))
        await db.flush()
        await db.refresh(session, attribute_names=["vaults"])

    # Create Aegra thread
    try:
        client = _get_aegra_client()
        thread = await client.threads.create()
        session.aegra_thread_id = thread["thread_id"]
    except Exception as exc:
        session.status = "failed"
        await db.flush()
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail=f"Failed to create Aegra thread: {exc}",
            headers={"X-Session-Id": session.id},
        )

    session.status = "idle"
    await db.flush()
    await db.refresh(session)
    await db.commit()
    return _to_response(session)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    status: str | None = None,
    agent_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Session)
        .options(selectinload(Session.vaults))
        .where(Session.archived_at.is_(None))
    )
    count_stmt = (
        select(func.count()).select_from(Session).where(Session.archived_at.is_(None))
    )

    if status:
        stmt = stmt.where(Session.status == status)
        count_stmt = count_stmt.where(Session.status == status)
    if agent_id:
        stmt = stmt.where(Session.agent_id == agent_id)
        count_stmt = count_stmt.where(Session.agent_id == agent_id)

    stmt = stmt.order_by(Session.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    count = (await db.execute(count_stmt)).scalar_one()

    return SessionListResponse(items=[_to_response(s) for s in sessions], count=count)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await _load_session(session_id, db)
    return _to_response(session)


@router.post("/{session_id}/events", response_model=SessionEventResponse)
async def send_events(
    session_id: str,
    body: SessionEventCreate,
    db: AsyncSession = Depends(get_db),
):
    """Send events to a session.

    Resolves config, creates an Aegra run, and starts a background task
    to consume the run's stream. Returns the run_id immediately.

    The background consumer saves every chunk to the DB and publishes
    to Redis so the session-level SSE endpoint can tail live events.
    """
    session = await _load_session(session_id, db)

    if not session.aegra_thread_id:
        raise HTTPException(
            status_code=400,
            detail="Session has no Aegra thread. Was it created correctly?",
        )

    if not session.agent_id:
        raise HTTPException(
            status_code=400,
            detail="Session has no agent configured. Create a session with an agent_id first.",
        )

    if session.status != "idle":
        raise HTTPException(
            status_code=409,
            detail=f"Session is not idle (current status: {session.status}). "
            "Wait for the current run to complete before sending new events.",
        )

    context = await _resolve_context(session, db)

    messages = []
    bus = RedisStreamBus()
    for event in body.events:
        for content_block in event.content:
            messages.append({"type": "human", "content": content_block.text})
            # Persist user message so it survives reloads
            try:
                saved = await _save_event(session_id, None, "user.message", {
                    "type": "human",
                    "content": content_block.text,
                })
                # Also push to Redis Stream so live SSE consumers see it immediately
                try:
                    await bus.append(session_id, {
                        "id": saved.id,
                        "type": "user.message",
                        "data": {"type": "human", "content": content_block.text},
                        "run_id": None,
                        "timestamp": saved.created_at.isoformat() if saved.created_at else datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as exc:
                    logger.warning("Failed to append user message to stream for session %s: %s", session_id, exc)
            except Exception as exc:
                logger.warning("Failed to persist user message for session %s: %s", session_id, exc)

    try:
        client = _get_aegra_client()
        run = await client.runs.create(
            thread_id=session.aegra_thread_id,
            assistant_id="agent",
            input={"messages": messages},
            context=context,
            multitask_strategy="reject",
        )
        run_id = run["run_id"]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to create Aegra run: {exc}",
        )

    # Start background consumer to stream events into DB + Redis
    asyncio.create_task(
        _consume_run_stream(session.id, session.aegra_thread_id, run_id)
    )

    return SessionEventResponse(
        run_id=run_id, thread_id=session.aegra_thread_id
    )


@router.get("/{session_id}/events", response_model=EventListResponse)
async def list_session_events(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all events for a session.

    Query params:
      order: asc (chronological, default) or desc (newest first).

    Used by the frontend for the "All events" panel and for reconnect
    deduplication on SSE reconnect.
    """
    session = await _load_session(session_id, db)

    sort = Event.created_at.asc() if order == "asc" else Event.created_at.desc()
    stmt = (
        select(Event)
        .where(Event.session_id == session_id)
        .order_by(sort)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    count_stmt = select(func.count()).select_from(Event).where(Event.session_id == session_id)
    count = (await db.execute(count_stmt)).scalar_one()

    return EventListResponse(
        items=[
            EventResponse(
                id=e.id,
                session_id=e.session_id,
                run_id=e.run_id,
                event_type=e.event_type,
                payload=e.payload,
                created_at=e.created_at,
            )
            for e in events
        ],
        count=count,
    )


@router.get("/{session_id}/events/stream")
async def stream_session_events(
    session_id: str,
    since: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Session-level SSE endpoint.

    Tails live events from Redis Streams (XREAD). Optionally sends a
    delta warm-up of recent events from the DB if the client provides a
    `since` query param (ISO timestamp of the last event it already has).

    The client should open this stream immediately on page load, before
    sending any events, to avoid missing early chunks.
    """
    session = await _load_session(session_id, db)

    if not session.aegra_thread_id:
        raise HTTPException(
            status_code=400,
            detail="Session has no Aegra thread.",
        )

    bus = RedisStreamBus()

    async def event_generator() -> AsyncIterator[str]:
        last_id = "$"  # Only new messages after we start reading
        try:
            # Delta warm-up: only events the client hasn't seen yet
            if since:
                try:
                    since_dt = datetime.fromisoformat(since)
                except ValueError:
                    since_dt = None

                if since_dt:
                    stmt = (
                        select(Event)
                        .where(
                            Event.session_id == session_id,
                            Event.created_at >= since_dt,
                        )
                        .order_by(Event.created_at.asc())
                    )
                    result = await db.execute(stmt)
                    for event in result.scalars().all():
                        if not _is_cma_event_type(event.event_type):
                            continue
                        payload = {
                            "id": event.id,
                            "type": event.event_type,
                            "data": event.payload,
                            "run_id": event.run_id,
                            "timestamp": event.created_at.isoformat() if event.created_at else None,
                        }
                        yield f"data: {json.dumps(payload, default=str)}\n\n"

            # Tail live events from Redis Stream
            while True:
                try:
                    messages = await bus.read(session_id, last_id=last_id, block_ms=100, count=100)
                except RedisTimeoutError:
                    # No new messages within block_ms — send keepalive
                    yield ":keepalive\n\n"
                    continue
                except Exception as exc:
                    logger.error("SSE stream read error for session %s: %s", session_id, exc)
                    yield f"data: {json.dumps({'type': 'error', 'data': {'error': 'Stream read error', 'detail': str(exc)}})}\n\n"
                    raise

                if messages:
                    for data in messages:
                        yield f"data: {json.dumps(data, default=str)}\n\n"
                        last_id = data.get("_stream_id", last_id)
                else:
                    # No new messages (non-blocking return) — keepalive
                    yield ":keepalive\n\n"

        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception as exc:
            logger.error("SSE generator error for session %s: %s", session_id, exc)
            yield f"data: {json.dumps({'type': 'error', 'data': {'error': 'Stream error', 'detail': str(exc)}})}\n\n"
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{session_id}/stream")
async def stream_response(
    request: Request,
    session_id: str,
    run_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """DEPRECATED: Use GET /{session_id}/events/stream instead.

    Kept for backward compatibility with existing API consumers.
    """
    session = await _load_session(session_id, db)

    if not session.aegra_thread_id:
        raise HTTPException(
            status_code=400,
            detail="Session has no Aegra thread.",
        )

    last_event_id = request.headers.get("last-event-id")
    client = _get_aegra_client()

    async def event_generator() -> AsyncIterator[str]:
        try:
            if run_id:
                stream = client.runs.join_stream(
                    thread_id=session.aegra_thread_id,
                    run_id=run_id,
                    last_event_id=last_event_id,
                )
            else:
                stream = client.runs.stream(
                    thread_id=session.aegra_thread_id,
                    assistant_id="agent",
                )

            yield ":keepalive\n\n"

            async for chunk in stream:
                event_type = getattr(chunk, "event", "message")
                data = getattr(chunk, "data", chunk)
                yield f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
                yield ":keepalive\n\n"
        except Exception as exc:
            error_detail = "Stream error occurred"
            if hasattr(exc, "status_code"):
                if exc.status_code == 404:
                    error_detail = "Run not found"
                elif exc.status_code == 400:
                    error_detail = "Run does not belong to this session"
            logger.error("Stream error for session %s: %s", session_id, exc)
            yield f"event: error\ndata: {json.dumps({'error': error_detail})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{session_id}/interrupt")
async def interrupt_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Interrupt the active run — CMA user.interrupt.

    Cancels the active Aegra run, updates session status to idle,
    and emits CMA events: user.interrupt, session.status_idle.
    """
    session = await _load_session(session_id, db)

    if session.status != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Session is not running (current status: {session.status}).",
        )

    if not session.aegra_thread_id:
        raise HTTPException(
            status_code=400,
            detail="Session has no Aegra thread.",
        )

    bus = RedisStreamBus()

    # 1. Save and publish user.interrupt CMA event
    saved_interrupt = await _save_event(session_id, None, "user.interrupt", {"reason": "user_requested"})
    try:
        await bus.append(session_id, {
            "id": saved_interrupt.id,
            "type": "user.interrupt",
            "data": {"reason": "user_requested"},
            "run_id": None,
            "timestamp": saved_interrupt.created_at.isoformat() if saved_interrupt.created_at else datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning("Failed to publish interrupt event to stream: %s", exc)

    # 2. Cancel active Aegra runs
    client = _get_aegra_client()
    try:
        active_runs = await client.runs.list(thread_id=session.aegra_thread_id)
        for run in active_runs:
            if run.get("status") in ("pending", "running"):
                try:
                    await client.runs.cancel(
                        thread_id=session.aegra_thread_id,
                        run_id=run["run_id"],
                    )
                except Exception as exc:
                    logger.warning("Failed to cancel run %s: %s", run.get("run_id"), exc)
    except Exception as exc:
        logger.warning("Failed to list runs for interrupt: %s", exc)

    # 3. Update session status
    session.status = "idle"
    session.stop_reason = "interrupted"
    await db.flush()
    await db.commit()

    # 4. Emit session.status_idle CMA event
    saved_idle = await _save_event(session_id, None, "session.status_idle", {"stop_reason": "interrupted"})
    try:
        await bus.append(session_id, {
            "id": saved_idle.id,
            "type": "session.status_idle",
            "data": {"stop_reason": "interrupted"},
            "run_id": None,
            "timestamp": saved_idle.created_at.isoformat() if saved_idle.created_at else datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning("Failed to publish status_idle event to stream: %s", exc)

    return {"status": "interrupted", "stop_reason": "interrupted"}


async def _archive_single_session(session: Session, db: AsyncSession) -> bool:
    """Archive one session: destroy sandbox, delete Aegra thread, mark DB archived.

    Returns True if sandbox was destroyed successfully (or had none), False otherwise.
    """
    if session.aegra_thread_id:
        try:
            client = _get_aegra_client()
            await client.threads.delete(session.aegra_thread_id)
        except Exception as exc:
            logger.warning(
                "Failed to archive Aegra thread %s: %s",
                session.aegra_thread_id,
                exc,
            )

    sandbox_destroyed = True
    if session.sandbox_container_id:
        sandbox_destroyed = await _destroy_sandbox(session.sandbox_container_id)

    session.status = "archived"
    session.archived_at = datetime.now(timezone.utc)
    await db.flush()
    return sandbox_destroyed


@router.post("/{session_id}/archive")
async def archive_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Archive a session: destroy sandbox, delete Aegra thread, mark DB archived.

    Returns:
        204 No Content — full success (sandbox destroyed + DB archived)
        202 Accepted — partial success (DB archived but sandbox destruction failed)
    """
    from fastapi.responses import Response

    session = await _load_session(session_id, db)
    sandbox_destroyed = await _archive_single_session(session, db)
    await db.commit()

    if not sandbox_destroyed:
        return Response(
            status_code=202,
            headers={"Warning": f'Sandbox destruction failed for session {session_id}'},
        )
    return Response(status_code=204)


class _BulkArchiveSessionsResponse(BaseModel):
    archived: list[str]
    failed: list[str]


class _BulkArchiveRequest(BaseModel):
    ids: list[str]


@router.post("/archive", response_model=_BulkArchiveSessionsResponse)
async def bulk_archive_sessions(
    body: _BulkArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")

    archived: list[str] = []
    failed: list[str] = []

    for sid in body.ids:
        try:
            stmt = (
                select(Session)
                .options(selectinload(Session.vaults))
                .where(Session.id == sid, Session.archived_at.is_(None))
            )
            result = await db.execute(stmt)
            session = result.scalar_one_or_none()
            if session is None:
                failed.append(sid)
                continue
            await _archive_single_session(session, db)
            archived.append(sid)
        except Exception as exc:
            logger.warning("Failed to archive session %s: %s", sid, exc)
            failed.append(sid)

    await db.commit()
    return _BulkArchiveSessionsResponse(archived=archived, failed=failed)
