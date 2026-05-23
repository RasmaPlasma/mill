"""make agents model nullable

Revision ID: 1fcc798e2bef
Revises: 003
Create Date: 2026-05-09 22:34:11.878305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1fcc798e2bef'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("agents", "model", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("agents", "model", existing_type=sa.Text(), nullable=False)
