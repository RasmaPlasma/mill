"""Pydantic schemas for agent CRUD operations."""

from datetime import datetime

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    model_id: str | None = None
    system_prompt: str | None = None
    tools: list[str] = []
    mcp_servers: list[dict] = []
    description: str | None = None
    metadata: dict = {}


class AgentUpdate(BaseModel):
    name: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    mcp_servers: list[dict] | None = None
    description: str | None = None
    metadata: dict | None = None


class AgentResponse(BaseModel):
    id: str
    name: str
    model_id: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    tools: list = []
    mcp_servers: list = []
    description: str | None = None
    metadata: dict = {}
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    count: int
