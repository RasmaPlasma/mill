"""Add llm_models table and agents.model_id FK.

Revision ID: 003
Revises: 002
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_models",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("provider_model", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column("model_id", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_agents_model_id",
        "agents",
        ["model_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_agents_llm_models",
        "agents",
        "llm_models",
        ["model_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_agents_llm_models", "agents", type_="foreignkey")
    op.drop_index("ix_agents_model_id", table_name="agents")
    op.drop_column("agents", "model_id")
    op.drop_table("llm_models")
