"""Pydantic schemas for vault and credential operations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class VaultCreate(BaseModel):
    display_name: str
    metadata: dict = {}


class VaultUpdate(BaseModel):
    display_name: str | None = None
    metadata: dict | None = None


class CredentialCreate(BaseModel):
    display_name: str
    mcp_server_url: str
    auth_type: Literal["mcp_oauth", "static_bearer"]
    token: str
    refresh_token: str | None = None
    token_endpoint: str | None = None
    client_id: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None


class CredentialRotate(BaseModel):
    token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None


class CredentialResponse(BaseModel):
    id: str
    vault_id: str
    display_name: str
    mcp_server_url: str
    auth_type: str
    token_endpoint: str | None = None
    client_id: str | None = None
    scope: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class VaultResponse(BaseModel):
    id: str
    display_name: str
    metadata: dict = {}
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None
    credentials: list[CredentialResponse] = []

    model_config = {"from_attributes": True}


class VaultListResponse(BaseModel):
    items: list[VaultResponse]
    count: int
