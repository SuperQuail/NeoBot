"""add images table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("original_width", sa.Integer(), nullable=True),
        sa.Column("original_height", sa.Integer(), nullable=True),
        sa.Column("processed_width", sa.Integer(), nullable=True),
        sa.Column("processed_height", sa.Integer(), nullable=True),
        sa.Column("analysis_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash", name="uq_images_file_hash"),
    )
    op.create_index("ix_images_updated_at", "images", ["updated_at"])
    op.create_index("ix_images_source", "images", ["source"])


def downgrade() -> None:
    op.drop_index("ix_images_source", table_name="images")
    op.drop_index("ix_images_updated_at", table_name="images")
    op.drop_table("images")
