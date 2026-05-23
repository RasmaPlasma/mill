"""SQLAlchemy ORM models for the platform database.

Tables: agents, environments, sessions, vaults, credentials, secrets, session_vaults.
Uses SQLAlchemy 2.0 Mapped column style.

These tables live in the same PostgreSQL database as Aegra's checkpoint
tables but are managed by a separate Alembic instance with
version_table="platform_alembic_version" to avoid collisions.

All primary keys and foreign keys use Text columns with ULID strings
(e.g., agent_01HqR2k7vXbZ9mNpL3wYcT8f). IDs are generated in Python.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from db.ulid import generate


def _agent_id() -> str:
    return generate("agent")


def _env_id() -> str:
    return generate("environment")


def _session_id() -> str:
    return generate("session")


def _vault_id() -> str:
    return generate("vault")


def _cred_id() -> str:
    return generate("credential")


def _secret_id() -> str:
    return generate("secret")


def _llm_model_id() -> str:
    return generate("llm_model")


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Declarative base for all platform models."""

    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_agent_id
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("llm_models.id"), nullable=True
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    mcp_servers: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="agent"
    )
    llm_model: Mapped["LLMModel | None"] = relationship(
        "LLMModel", lazy="joined"
    )


class LLMModel(Base):
    __tablename__ = "llm_models"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_llm_model_id
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_model: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_env_id
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    packages: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    networking: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default='{"type":"limited","allowed_hosts":[],"allow_package_managers":false}',
    )
    resource_limits: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default='{"memory":"1g","cpus":1.0,"pids_limit":256}',
    )
    repositories: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    skill_repos: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    base_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_subnet: Mapped[str | None] = mapped_column(Text, nullable=True)
    dockerfile_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="environment"
    )


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_agent_id", "agent_id"),
        Index("ix_sessions_environment_id", "environment_id"),
        Index("ix_sessions_aegra_thread_id", "aegra_thread_id"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_session_id
    )
    agent_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("agents.id"), nullable=True
    )
    environment_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("environments.id"), nullable=True
    )
    aegra_thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sandbox_container_id: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    last_exec_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    repositories: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    skill_repos: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="idle", server_default="idle"
    )
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    agent: Mapped["Agent | None"] = relationship(
        back_populates="sessions"
    )
    environment: Mapped["Environment | None"] = relationship(
        back_populates="sessions"
    )
    vaults: Mapped[list["Vault"]] = relationship(
        "Vault",
        secondary="session_vaults",
        back_populates="sessions",
        lazy="selectin",
    )


class Vault(Base):
    __tablename__ = "vaults"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_vault_id
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    credentials: Mapped[list["Credential"]] = relationship(
        back_populates="vault", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        secondary="session_vaults",
        back_populates="vaults",
    )


class Credential(Base):
    __tablename__ = "credentials"
    __table_args__ = (
        Index("ix_credentials_vault_id", "vault_id"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_cred_id
    )
    vault_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("vaults.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    mcp_server_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_token: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    token_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    vault: Mapped["Vault"] = relationship(
        back_populates="credentials"
    )


class Secret(Base):
    __tablename__ = "secrets"
    __table_args__ = (
        UniqueConstraint("name", "scope", name="uq_secret_name_scope"),
        Index("ix_secrets_scope", "scope"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=_secret_id
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_value: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    scope: Mapped[str] = mapped_column(
        Text, nullable=False, default="global", server_default="global"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now()
    )


class Event(Base):
    """Events table — stores every raw chunk from Aegra/LangGraph runs.

    Enables history replay for session-level SSE and the "All events" panel.
    Events are keyed by session_id for fast lookup.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_session_id", "session_id"),
        Index("ix_events_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SessionVault(Base):
    """Many-to-many join table: sessions ↔ vaults.

    Both foreign keys have ON DELETE CASCADE so that archiving a session
    or a vault automatically removes the association.
    """

    __tablename__ = "session_vaults"
    __table_args__ = (PrimaryKeyConstraint("session_id", "vault_id"),)

    session_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    vault_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("vaults.id", ondelete="CASCADE"),
        nullable=False,
    )
