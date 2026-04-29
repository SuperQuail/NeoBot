"""add emojis table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emojis",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("original_width", sa.Integer(), nullable=True),
        sa.Column("original_height", sa.Integer(), nullable=True),
        sa.Column("analysis_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash", name="uq_emojis_file_hash"),
    )
    op.create_index("ix_emojis_updated_at", "emojis", ["updated_at"])
    op.create_index("ix_emojis_file_name", "emojis", ["file_name"])


def downgrade() -> None:
    op.drop_index("ix_emojis_file_name", table_name="emojis")
    op.drop_index("ix_emojis_updated_at", table_name="emojis")
    op.drop_table("emojis")
