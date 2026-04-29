"""add favorability to user_data

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-26
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_data", sa.Column("favorability", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("user_data", "favorability")
