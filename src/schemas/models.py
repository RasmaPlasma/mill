"""Pydantic schemas for LLM model registry CRUD operations."""

from datetime import datetime

from pydantic import BaseModel


class LLMModelCreate(BaseModel):
    display_name: str
    provider: str
    provider_model: str
    description: str | None = None


class LLMModelUpdate(BaseModel):
    display_name: str | None = None
    provider: str | None = None
    provider_model: str | None = None
    description: str | None = None


class LLMModelResponse(BaseModel):
    id: str
    display_name: str
    provider: str
    provider_model: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class LLMModelListResponse(BaseModel):
    items: list[LLMModelResponse]
    count: int
