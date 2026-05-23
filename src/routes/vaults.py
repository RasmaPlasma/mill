"""Vault and credential routes — /v1/vaults."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.crypto import encrypt
from db.engine import get_db
from db.models import Credential, Vault
from schemas.vaults import (
    CredentialCreate,
    CredentialResponse,
    CredentialRotate,
    VaultCreate,
    VaultListResponse,
    VaultResponse,
    VaultUpdate,
)

router = APIRouter(prefix="/v1/vaults", tags=["Vaults"])


class _BulkArchiveRequest(BaseModel):
    ids: list[str]


def _cred_to_response(cred: Credential) -> CredentialResponse:
    """Credential response — token fields are NEVER included."""
    return CredentialResponse(
        id=cred.id,
        vault_id=cred.vault_id,
        display_name=cred.display_name,
        mcp_server_url=cred.mcp_server_url,
        auth_type=cred.auth_type,
        token_endpoint=cred.token_endpoint,
        client_id=cred.client_id,
        scope=cred.scope,
        expires_at=cred.expires_at,
        created_at=cred.created_at,
        updated_at=cred.updated_at,
        archived_at=cred.archived_at,
    )


def _vault_to_response(vault: Vault, creds: list[Credential] | None = None) -> VaultResponse:
    return VaultResponse(
        id=vault.id,
        display_name=vault.display_name,
        metadata=vault.metadata_ or {},
        created_at=vault.created_at,
        updated_at=vault.updated_at,
        archived_at=vault.archived_at,
        credentials=[_cred_to_response(c) for c in (creds or [])],
    )


async def _load_vault(vault_id: str, db: AsyncSession) -> Vault:
    stmt = select(Vault).where(Vault.id == vault_id, Vault.archived_at.is_(None))
    result = await db.execute(stmt)
    vault = result.scalar_one_or_none()
    if vault is None:
        raise HTTPException(status_code=404, detail="Vault not found")
    return vault


async def _load_vault_with_creds(vault_id: str, db: AsyncSession) -> tuple[Vault, list[Credential]]:
    vault = await _load_vault(vault_id, db)
    creds_stmt = (
        select(Credential)
        .where(Credential.vault_id == vault_id, Credential.archived_at.is_(None))
        .order_by(Credential.created_at)
    )
    creds = (await db.execute(creds_stmt)).scalars().all()
    return vault, creds


@router.post("", response_model=VaultResponse, status_code=201)
async def create_vault(
    body: VaultCreate,
    db: AsyncSession = Depends(get_db),
):
    vault = Vault(
        display_name=body.display_name,
        metadata_=body.metadata,
    )
    db.add(vault)
    await db.flush()
    await db.refresh(vault)
    await db.commit()
    return _vault_to_response(vault)


@router.get("", response_model=VaultListResponse)
async def list_vaults(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Vault)
        .where(Vault.archived_at.is_(None))
        .order_by(Vault.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    vaults = result.scalars().all()

    count_stmt = select(func.count()).select_from(Vault).where(Vault.archived_at.is_(None))
    count = (await db.execute(count_stmt)).scalar_one()

    return VaultListResponse(
        items=[_vault_to_response(v) for v in vaults], count=count
    )


@router.get("/{vault_id}", response_model=VaultResponse)
async def get_vault(
    vault_id: str,
    db: AsyncSession = Depends(get_db),
):
    vault, creds = await _load_vault_with_creds(vault_id, db)
    return _vault_to_response(vault, creds)


@router.patch("/{vault_id}", response_model=VaultResponse)
async def update_vault(
    vault_id: str,
    body: VaultUpdate,
    db: AsyncSession = Depends(get_db),
):
    vault = await _load_vault(vault_id, db)

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Map 'metadata' key to 'metadata_' column attribute
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for field, value in update_data.items():
        setattr(vault, field, value)

    await db.flush()
    await db.refresh(vault)
    await db.commit()

    _, creds = await _load_vault_with_creds(vault_id, db)
    return _vault_to_response(vault, creds)


@router.post("/{vault_id}/archive", status_code=204)
async def archive_vault(
    vault_id: str,
    db: AsyncSession = Depends(get_db),
):
    vault = await _load_vault(vault_id, db)
    vault.archived_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()


@router.post("/archive", status_code=204)
async def bulk_archive_vaults(
    body: _BulkArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    stmt = (
        update(Vault)
        .where(Vault.id.in_(body.ids), Vault.archived_at.is_(None))
        .values(archived_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session="fetch")
    )
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="No vaults found to archive")
    return None


@router.post("/{vault_id}/credentials", response_model=CredentialResponse, status_code=201)
async def add_credential(
    vault_id: str,
    body: CredentialCreate,
    db: AsyncSession = Depends(get_db),
):
    # Verify vault exists
    await _load_vault(vault_id, db)

    # Check unique constraint: one credential per MCP URL per vault
    dup_stmt = select(Credential).where(
        Credential.vault_id == vault_id,
        Credential.mcp_server_url == body.mcp_server_url,
        Credential.archived_at.is_(None),
    )
    dup_result = await db.execute(dup_stmt)
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Credential for MCP server URL '{body.mcp_server_url}' already exists in this vault",
        )

    cred = Credential(
        vault_id=vault_id,
        display_name=body.display_name,
        mcp_server_url=body.mcp_server_url,
        auth_type=body.auth_type,
        encrypted_token=encrypt(body.token),
        encrypted_refresh_token=encrypt(body.refresh_token) if body.refresh_token else None,
        token_endpoint=body.token_endpoint,
        client_id=body.client_id,
        scope=body.scope,
        expires_at=body.expires_at,
    )
    db.add(cred)
    await db.flush()
    await db.refresh(cred)
    await db.commit()
    return _cred_to_response(cred)


@router.patch(
    "/{vault_id}/credentials/{credential_id}",
    response_model=CredentialResponse,
)
async def rotate_credential(
    vault_id: str,
    credential_id: str,
    body: CredentialRotate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Credential).where(
        Credential.id == credential_id,
        Credential.vault_id == vault_id,
        Credential.archived_at.is_(None),
    )
    result = await db.execute(stmt)
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="Credential not found")

    cred.encrypted_token = encrypt(body.token)
    if body.refresh_token is not None:
        cred.encrypted_refresh_token = encrypt(body.refresh_token)
    if body.expires_at is not None:
        cred.expires_at = body.expires_at

    await db.flush()
    await db.refresh(cred)
    await db.commit()
    return _cred_to_response(cred)
