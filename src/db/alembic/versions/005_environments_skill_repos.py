"""Drop agents.skills, add environments.skill_repos.

Revision ID: 005
Revises: 1fcc798e2bef
Create Date: 2026-05-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "1fcc798e2bef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop agents.skills (dead column)
    op.drop_column("agents", "skills")

    # Add environments.skill_repos
    op.add_column(
        "environments",
        sa.Column("skill_repos", sa.JSON, server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("environments", "skill_repos")
    op.add_column(
        "agents",
        sa.Column("skills", sa.JSON, server_default="[]", nullable=False),
    )
