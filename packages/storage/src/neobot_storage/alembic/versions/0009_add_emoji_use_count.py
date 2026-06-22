"""add emoji use_count

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-25
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("emojis", sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("emojis", "use_count")
