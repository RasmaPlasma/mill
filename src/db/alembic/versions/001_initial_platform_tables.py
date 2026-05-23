"""Initial platform tables with ULID Text primary keys.

Revision ID: 001
Revises: None
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agents ---
    op.create_table(
        "agents",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("tools", JSONB, server_default="[]"),
        sa.Column("mcp_servers", JSONB, server_default="[]"),
        sa.Column("skills", JSONB, server_default="[]"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("version", sa.BigInteger, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- environments ---
    op.create_table(
        "environments",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("packages", JSONB, server_default="{}"),
        sa.Column(
            "networking",
            JSONB,
            server_default='{"type":"limited","allowed_hosts":[],"allow_package_managers":false}',
        ),
        sa.Column(
            "resource_limits",
            JSONB,
            server_default='{"memory":"1g","cpus":1.0,"pids_limit":256}',
        ),
        sa.Column("dockerfile_cache", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_environments_name_active "
        "ON environments (name) WHERE archived_at IS NULL"
    )

    # --- vaults ---
    op.create_table(
        "vaults",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- credentials ---
    op.create_table(
        "credentials",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("vault_id", sa.Text, sa.ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("mcp_server_url", sa.Text, nullable=False),
        sa.Column("auth_type", sa.Text, nullable=False),
        sa.Column("encrypted_token", sa.LargeBinary, nullable=False),
        sa.Column("encrypted_refresh_token", sa.LargeBinary, nullable=True),
        sa.Column("token_endpoint", sa.Text, nullable=True),
        sa.Column("client_id", sa.Text, nullable=True),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_credential_vault_url_active "
        "ON credentials (vault_id, mcp_server_url) WHERE archived_at IS NULL"
    )
    op.create_index("ix_credentials_vault_id", "credentials", ["vault_id"])

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("agent_id", sa.Text, sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("environment_id", sa.Text, sa.ForeignKey("environments.id"), nullable=True),
        sa.Column("aegra_thread_id", sa.Text, nullable=True),
        sa.Column("sandbox_container_id", sa.Text, nullable=True),
        sa.Column("last_exec_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="idle"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_agent_id", "sessions", ["agent_id"])
    op.create_index("ix_sessions_environment_id", "sessions", ["environment_id"])
    op.create_index("ix_sessions_aegra_thread_id", "sessions", ["aegra_thread_id"])

    # --- session_vaults (join table) ---
    op.create_table(
        "session_vaults",
        sa.Column("session_id", sa.Text, sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vault_id", sa.Text, sa.ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "vault_id"),
    )

    # --- secrets ---
    op.create_table(
        "secrets",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("encrypted_value", sa.LargeBinary, nullable=False),
        sa.Column("scope", sa.Text, nullable=False, server_default="global"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "scope", name="uq_secret_name_scope"),
    )
    op.create_index("ix_secrets_scope", "secrets", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_secrets_scope", table_name="secrets")
    op.drop_table("secrets")
    op.drop_table("session_vaults")
    op.drop_index("ix_sessions_aegra_thread_id", table_name="sessions")
    op.drop_index("ix_sessions_environment_id", table_name="sessions")
    op.drop_index("ix_sessions_agent_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_credentials_vault_id", table_name="credentials")
    op.execute("DROP INDEX IF EXISTS uq_credential_vault_url_active")
    op.drop_table("credentials")
    op.drop_table("vaults")
    op.execute("DROP INDEX IF EXISTS uq_environments_name_active")
    op.drop_table("environments")
    op.drop_table("agents")
