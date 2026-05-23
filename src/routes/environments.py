"""Environment CRUD routes — /v1/environments."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db, get_session_factory
from db.models import Environment
from schemas.environments import (
    EnvironmentCreate,
    EnvironmentListResponse,
    EnvironmentResponse,
    EnvironmentUpdate,
)

router = APIRouter(prefix="/v1/environments", tags=["Environments"])

logger = logging.getLogger(__name__)


class _BulkArchiveRequest(BaseModel):
    ids: list[str]


async def _trigger_env_build(env_id: str, packages: dict, base_image: str | None, ip_subnet: str | None) -> None:
    """Fire a background image build for an environment and store the tag.

    Uses a standalone DB session so the update survives the request lifecycle.
    Failures are logged but never raised — the lazy backend will build on
    demand if the pre-build fails.
    """
    sandbox_url = os.environ.get("SANDBOX_SERVICE_URL", "http://sandbox-service:8090")
    api_key = os.environ.get("SANDBOX_API_KEY", "")
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{sandbox_url}/images/build",
                json={
                    "environment_id": env_id,
                    "packages": packages,
                    "base_image": base_image,
                    "ip_subnet": ip_subnet,
                },
                headers=headers,
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            image_tag = data.get("image_tag")
            if image_tag:
                session_factory = get_session_factory()
                async with session_factory() as db:
                    stmt = select(Environment).where(Environment.id == env_id)
                    result = await db.execute(stmt)
                    row = result.scalar_one_or_none()
                    if row:
                        row.dockerfile_cache = image_tag
                        await db.commit()
    except Exception as exc:
        logger.warning("Background image build failed for env %s: %s", env_id, exc)


def _to_response(env: Environment) -> EnvironmentResponse:
    return EnvironmentResponse(
        id=env.id,
        name=env.name,
        packages=env.packages or {},
        networking=env.networking or {},
        resource_limits=env.resource_limits or {},
        repositories=env.repositories or [],
        skill_repos=env.skill_repos or [],
        base_image=env.base_image,
        ip_subnet=env.ip_subnet,
        dockerfile_cache=env.dockerfile_cache,
        created_at=env.created_at,
        updated_at=env.updated_at,
        archived_at=env.archived_at,
    )


@router.post("", response_model=EnvironmentResponse, status_code=201)
async def create_environment(
    body: EnvironmentCreate,
    db: AsyncSession = Depends(get_db),
):
    # Check name uniqueness among non-archived environments
    existing = await db.execute(
        select(Environment).where(
            Environment.name == body.name,
            Environment.archived_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Environment with name '{body.name}' already exists",
        )

    env = Environment(
        name=body.name,
        packages=body.packages.model_dump(),
        networking=body.networking.model_dump(),
        resource_limits=body.resource_limits.model_dump(),
        repositories=[r.model_dump() for r in body.repositories],
        skill_repos=[r.model_dump() for r in body.skill_repos],
        base_image=body.base_image,
    )
    db.add(env)
    await db.flush()
    await db.refresh(env)
    await db.commit()

    # Fire background image build so first tool call doesn't wait for it
    asyncio.create_task(
        _trigger_env_build(
            env.id, env.packages or {}, env.base_image, env.ip_subnet
        )
    )

    return _to_response(env)


@router.get("", response_model=EnvironmentListResponse)
async def list_environments(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Environment)
        .where(Environment.archived_at.is_(None))
        .order_by(Environment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    envs = result.scalars().all()

    count_stmt = (
        select(func.count())
        .select_from(Environment)
        .where(Environment.archived_at.is_(None))
    )
    count = (await db.execute(count_stmt)).scalar_one()

    return EnvironmentListResponse(items=[_to_response(e) for e in envs], count=count)


@router.get("/{env_id}", response_model=EnvironmentResponse)
async def get_environment(
    env_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Environment).where(
        Environment.id == env_id, Environment.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return _to_response(env)


@router.patch("/{env_id}", response_model=EnvironmentResponse)
async def update_environment(
    env_id: str,
    body: EnvironmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Environment).where(
        Environment.id == env_id, Environment.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Check name uniqueness if name is being changed
    if "name" in update_data and update_data["name"] != env.name:
        dup = await db.execute(
            select(Environment).where(
                Environment.name == update_data["name"],
                Environment.archived_at.is_(None),
                Environment.id != env_id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Environment with name '{update_data['name']}' already exists",
            )

    for field, value in update_data.items():
        if field == "repositories" and value is not None:
            setattr(env, field, [r.model_dump() for r in value])
        elif field == "skill_repos" and value is not None:
            setattr(env, field, [r.model_dump() for r in value])
        else:
            setattr(env, field, value)

    # Invalidate cached build key when packages or base image change, then
    # fire a background rebuild so the new image is ready before first use.
    should_rebuild = any(k in update_data for k in ("packages", "base_image"))
    if should_rebuild:
        env.dockerfile_cache = None

    await db.flush()
    await db.refresh(env)
    await db.commit()

    if should_rebuild:
        asyncio.create_task(
            _trigger_env_build(
                env.id, env.packages or {}, env.base_image, env.ip_subnet
            )
        )

    return _to_response(env)


@router.post("/{env_id}/build")
async def build_environment_image(
    env_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an image build for an environment.

    Returns immediately; the build runs in the background.
    """
    stmt = select(Environment).where(
        Environment.id == env_id, Environment.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    asyncio.create_task(
        _trigger_env_build(
            env.id, env.packages or {}, env.base_image, env.ip_subnet
        )
    )
    return {"status": "build_triggered", "environment_id": env_id}


@router.post("/{env_id}/archive", status_code=204)
async def archive_environment(
    env_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Environment).where(
        Environment.id == env_id, Environment.archived_at.is_(None)
    )
    result = await db.execute(stmt)
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    env.archived_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()


@router.post("/archive", status_code=204)
async def bulk_archive_environments(
    body: _BulkArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    stmt = (
        update(Environment)
        .where(Environment.id.in_(body.ids), Environment.archived_at.is_(None))
        .values(archived_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session="fetch")
    )
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="No environments found to archive")
    return None
