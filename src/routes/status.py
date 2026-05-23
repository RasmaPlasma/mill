"""Internal session status and cleanup callbacks.

POST /internal/sessions/:id/status     — Called by the factory graph to update session status.
POST /internal/sessions/:id/last-exec  — Called by sandbox-service after each exec.
POST /internal/sessions/:id/cleanup    — Called by sandbox-service when cleaning up zombie containers.
GET  /internal/sessions/stale           — Called by sandbox-service to find sessions with inactive sandboxes.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import Session
from schemas.sessions import StatusUpdate

router = APIRouter(prefix="/internal/sessions", tags=["Internal"])


class SandboxIdUpdate(BaseModel):
    container_id: str


@router.post("/{session_id}/status")
async def update_session_status(
    session_id: str,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update session status.

    Called by the factory graph via the status_callback_url in the context.
    Status values: idle, running, creating, failed, archived, terminated.
    """
    stmt = select(Session).where(
        Session.id == session_id, Session.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = body.status
    if body.stop_reason is not None:
        session.stop_reason = body.stop_reason
    # updated_at auto-updates via onupdate=func.now() on the model
    await db.flush()
    await db.commit()

    return {"status": session.status, "stop_reason": session.stop_reason}


@router.post("/{session_id}/sandbox", status_code=204)
async def update_session_sandbox_id(
    session_id: str,
    body: SandboxIdUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Store the sandbox container ID on the session row.

    Called by LazyDockerSandboxBackend after it creates a new container
    on the first tool call. Updates both the container ID and the
    last_exec_at timestamp so the cleanup job knows the container is active.
    """
    stmt = select(Session).where(
        Session.id == session_id, Session.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        return

    session.sandbox_container_id = body.container_id
    session.last_exec_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()


@router.post("/{session_id}/cleanup", status_code=204)
async def cleanup_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle cleanup of a session whose sandbox was destroyed externally.

    Called by the sandbox-service's zombie cleanup job when it finds a
    container with platform.managed=true but no matching active session,
    or when the session is archived.

    Sets the session to failed status and clears the sandbox container ID.
    """
    stmt = select(Session).where(
        Session.id == session_id, Session.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        # Session already archived or not found — nothing to clean up
        return

    session.status = "failed"
    session.sandbox_container_id = None
    await db.flush()
    await db.commit()


class LastExecUpdate(BaseModel):
    container_id: str


@router.post("/{session_id}/last-exec", status_code=204)
async def update_last_exec(
    session_id: str,
    body: LastExecUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the last_exec_at timestamp for a session.

    Called by sandbox-service after each exec_command to track
    container activity. The cleanup job uses this to determine
    which sandboxes have been inactive for 15+ minutes.
    """
    stmt = select(Session).where(
        Session.id == session_id, Session.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        # Session not found — may have been archived between exec and callback
        return

    # Only update if the container_id matches (prevent stale callbacks)
    if session.sandbox_container_id == body.container_id:
        session.last_exec_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()


class StaleSession(BaseModel):
    session_id: str
    sandbox_container_id: str


@router.get("/stale", response_model=list[StaleSession])
async def get_stale_sessions(
    idle_seconds: int = 900,
    db: AsyncSession = Depends(get_db),
):
    """Find sessions with sandbox containers inactive for more than idle_seconds.

    Called by sandbox-service's inactivity detection job.
    Default threshold: 900 seconds (15 minutes).
    """
    cutoff = datetime.now(timezone.utc).timestamp() - idle_seconds

    stmt = select(Session).where(
        Session.archived_at.is_(None),
        Session.sandbox_container_id.isnot(None),
        Session.status.in_(["idle", "running"]),
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    stale = []
    for session in sessions:
        # If last_exec_at is None, use created_at as fallback
        last_active = session.last_exec_at or session.created_at
        if last_active and last_active.timestamp() < cutoff:
            stale.append(StaleSession(
                session_id=session.id,
                sandbox_container_id=session.sandbox_container_id,
            ))

    return stale
