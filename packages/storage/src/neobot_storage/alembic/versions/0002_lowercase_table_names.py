"""lowercase table names

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-21 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite treats table names as case-insensitive, so we need a two-step rename
    for old, tmp, new in [
        ("USER_DATA", "_tmp_user_data", "user_data"),
        ("GROUP_DATA", "_tmp_group_data", "group_data"),
        ("EVENT_DATA", "_tmp_event_data", "event_data"),
    ]:
        op.rename_table(old, tmp)
        op.rename_table(tmp, new)


def downgrade() -> None:
    for old, tmp, new in [
        ("user_data", "_tmp_user_data", "USER_DATA"),
        ("group_data", "_tmp_group_data", "GROUP_DATA"),
        ("event_data", "_tmp_event_data", "EVENT_DATA"),
    ]:
        op.rename_table(old, tmp)
        op.rename_table(tmp, new)
