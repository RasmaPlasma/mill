"""Add repositories, ip_subnet, base_image to environments.

Revision ID: 002
Revises: 001
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "environments",
        sa.Column("repositories", JSONB, server_default="[]", nullable=False),
    )
    op.add_column(
        "environments",
        sa.Column("ip_subnet", sa.Text, nullable=True),
    )
    op.add_column(
        "environments",
        sa.Column("base_image", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_environments_ip_subnet",
        "environments",
        ["ip_subnet"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_environments_ip_subnet", table_name="environments")
    op.drop_column("environments", "base_image")
    op.drop_column("environments", "ip_subnet")
    op.drop_column("environments", "repositories")
