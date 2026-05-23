"""Secret CRUD routes — /v1/secrets.

Secrets are general-purpose key-value pairs for API keys, env vars, etc.
Values are encrypted at rest and NEVER returned in API responses.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.crypto import encrypt
from db.engine import get_db
from db.models import Secret
from schemas.secrets import SecretCreate, SecretListResponse, SecretResponse

router = APIRouter(prefix="/v1/secrets", tags=["Secrets"])


def _to_response(secret: Secret) -> SecretResponse:
    return SecretResponse(
        id=secret.id,
        name=secret.name,
        scope=secret.scope,
        description=secret.description,
        created_at=secret.created_at,
        updated_at=secret.updated_at,
    )


@router.post("", response_model=SecretResponse, status_code=201)
async def create_secret(
    body: SecretCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update a secret (upsert on name + scope)."""
    # Check if secret with same name+scope exists
    stmt = select(Secret).where(Secret.name == body.name, Secret.scope == body.scope)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Update existing secret
        existing.encrypted_value = encrypt(body.value)
        existing.description = body.description
        await db.flush()
        await db.refresh(existing)
        return _to_response(existing)

    secret = Secret(
        name=body.name,
        encrypted_value=encrypt(body.value),
        scope=body.scope,
        description=body.description,
    )
    db.add(secret)
    await db.flush()
    await db.refresh(secret)
    await db.commit()
    return _to_response(secret)


@router.get("", response_model=SecretListResponse)
async def list_secrets(
    scope: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List secret metadata. Values are NEVER returned."""
    stmt = select(Secret).order_by(Secret.name).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(Secret)

    if scope:
        stmt = stmt.where(Secret.scope == scope)
        count_stmt = count_stmt.where(Secret.scope == scope)

    result = await db.execute(stmt)
    secrets = result.scalars().all()

    count = (await db.execute(count_stmt)).scalar_one()

    return SecretListResponse(
        items=[_to_response(s) for s in secrets], count=count
    )


@router.delete("/{secret_id}", status_code=204)
async def delete_secret(
    secret_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Secret).where(Secret.id == secret_id)
    result = await db.execute(stmt)
    secret = result.scalar_one_or_none()
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret not found")

    await db.delete(secret)
    await db.flush()
    await db.commit()
