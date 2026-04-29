"""add creator images table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-25
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creator_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("image_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("original_width", sa.Integer(), nullable=True),
        sa.Column("original_height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id", name="uq_creator_images_image_id"),
    )
    op.create_index(
        "ix_creator_images_source_updated_at",
        "creator_images",
        ["source", "updated_at"],
    )
    op.create_index("ix_creator_images_file_hash", "creator_images", ["file_hash"])


def downgrade() -> None:
    op.drop_index("ix_creator_images_file_hash", table_name="creator_images")
    op.drop_index("ix_creator_images_source_updated_at", table_name="creator_images")
    op.drop_table("creator_images")
