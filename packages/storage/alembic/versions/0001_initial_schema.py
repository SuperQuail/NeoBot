"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-21 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "USER_DATA",
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("nick_name", sa.Text()),
        sa.Column("relation_ship", sa.Text()),
        sa.Column("profile", sa.Text()),
        sa.Column("birthday", sa.Text()),
        sa.Column("sex", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("labs", sa.Text()),
        sa.Column("remark", sa.Text()),
        sa.Column("age", sa.Integer()),
        sa.Column("long_nick", sa.Text()),
    )

    op.create_table(
        "GROUP_DATA",
        sa.Column("group_id", sa.String(), primary_key=True),
        sa.Column("group_name", sa.Text()),
        sa.Column("profile", sa.Text()),
        sa.Column("is_quite", sa.Boolean(), server_default=sa.false()),
    )

    op.create_table(
        "EVENT_DATA",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("event_message", sa.Text()),
        sa.Column("embedded_data", sa.Text()),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(), nullable=False, unique=True),
        sa.Column("conversation_kind", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("sender_id", sa.String(), nullable=False),
        sa.Column("sender_name", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_kind", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("speaker_id", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("memories")
    op.drop_table("messages")
    op.drop_table("EVENT_DATA")
    op.drop_table("GROUP_DATA")
    op.drop_table("USER_DATA")
