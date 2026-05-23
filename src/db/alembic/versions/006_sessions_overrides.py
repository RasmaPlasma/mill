"""Add repositories and skill_repos to sessions table.

Revision ID: 006
Revises: 005
Create Date: 2026-05-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("repositories", sa.JSON, server_default="[]", nullable=False),
    )
    op.add_column(
        "sessions",
        sa.Column("skill_repos", sa.JSON, server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("sessions", "skill_repos")
    op.drop_column("sessions", "repositories")
