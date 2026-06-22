"""add archive_memories table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-22 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "archive_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("tags", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("table_name", "key", name="uq_archive_memories_table_key"),
    )
    
    # 创建索引和唯一约束
    op.create_index(
        "ix_archive_memories_table_name_updated_at",
        "archive_memories",
        ["table_name", "updated_at"],
    )
def downgrade() -> None:
    op.drop_index("ix_archive_memories_table_name_updated_at", "archive_memories")
    op.drop_table("archive_memories")
