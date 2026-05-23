"""Pydantic schemas for session management operations."""

from datetime import datetime

from pydantic import BaseModel, field_validator


class SessionCreate(BaseModel):
    agent_id: str | None = None
    environment_id: str | None = None
    vault_ids: list[str] = []
    title: str | None = None
    repositories: list[dict] = []
    skill_repos: list[dict] = []


class EventContent(BaseModel):
    type: str = "text"
    text: str


class SessionEvent(BaseModel):
    type: str = "user.message"
    content: list[EventContent]


class SessionEventCreate(BaseModel):
    events: list[SessionEvent]


class SessionEventResponse(BaseModel):
    run_id: str
    thread_id: str


class StatusUpdate(BaseModel):
    status: str
    stop_reason: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"idle", "running", "archived", "terminated", "creating", "failed", "interrupted"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got: {v!r}")
        return v


class SessionResponse(BaseModel):
    id: str
    agent_id: str | None = None
    environment_id: str | None = None
    vault_ids: list[str] = []
    aegra_thread_id: str | None = None
    sandbox_container_id: str | None = None
    last_exec_at: datetime | None = None
    title: str | None = None
    repositories: list[dict] = []
    skill_repos: list[dict] = []
    status: str = "idle"
    stop_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: int
    session_id: str
    run_id: str | None = None
    event_type: str
    payload: dict
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list[EventResponse]
    count: int


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    count: int
