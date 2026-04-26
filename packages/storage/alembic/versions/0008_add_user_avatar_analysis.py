"""add user avatar analysis

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_data", sa.Column("avatar_analysis", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_data", "avatar_analysis")
