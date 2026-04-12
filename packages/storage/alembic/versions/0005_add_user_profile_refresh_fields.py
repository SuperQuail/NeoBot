"""add user profile refresh fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-12
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_data", sa.Column("known_gender", sa.Text(), nullable=True))
    op.add_column(
        "user_data",
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_data", "fetched_at")
    op.drop_column("user_data", "known_gender")
