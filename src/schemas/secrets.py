"""Pydantic schemas for secret operations."""

from datetime import datetime

from pydantic import BaseModel, field_validator
from ulid import ULID


class SecretCreate(BaseModel):
    name: str
    value: str
    scope: str = "global"
    description: str | None = None

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if v == "global":
            return v

        prefix, _, suffix = v.partition(":")
        if prefix == "agent" and suffix.startswith("agent_") and len(suffix) == 32:
            try:
                ULID.from_str(suffix[6:].upper())
                return v
            except ValueError:
                pass
        if prefix == "environment" and suffix.startswith("env_") and len(suffix) == 30:
            try:
                ULID.from_str(suffix[4:].upper())
                return v
            except ValueError:
                pass

        raise ValueError(
            f"scope must be 'global', 'agent:{{ulid}}', or 'environment:{{ulid}}', got: {v!r}"
        )


class SecretResponse(BaseModel):
    id: str
    name: str
    scope: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SecretListResponse(BaseModel):
    items: list[SecretResponse]
    count: int
