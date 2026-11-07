"""新增跨聊天交互会话表

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-07

跨聊天交互（cross_chat_send）此前只有进程内 `_tasks` 字典，重启即丢，agent
也无法在后续轮次回看自己做过哪些跨聊天交互。本表按「发起方聊天流 + 目标聊天流」
这一对做唯一约束，保存最近一次交互的 task_id / 模式 / 状态 / 回传内容。

`boot_id` 是写入时进程的启动标识：查询只返回与当前进程一致的记录，因此重启后
旧的 session 不会显示（数据仍留在库里，等待后续清理策略）。这只影响可见性，
不改变投递与回传的任何行为。

downgrade 只删表，其它表不受影响，可往返。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cross_chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("origin_kind", sa.String(), nullable=False),
        sa.Column("origin_id", sa.String(), nullable=False),
        sa.Column("target_kind", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("mode", sa.String(), nullable=False, server_default=sa.text("'fire_and_forget'")),
        sa.Column("notification_mode", sa.String(), nullable=False, server_default=sa.text("'no_response'")),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("reply", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("boot_id", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "origin_kind", "origin_id", "target_kind", "target_id",
            name="uq_cross_chat_sessions_pair",
        ),
    )
    op.create_index("ix_cross_chat_sessions_origin", "cross_chat_sessions", ["origin_kind", "origin_id"])
    op.create_index("ix_cross_chat_sessions_boot_id", "cross_chat_sessions", ["boot_id"])


def downgrade() -> None:
    op.drop_index("ix_cross_chat_sessions_boot_id", table_name="cross_chat_sessions")
    op.drop_index("ix_cross_chat_sessions_origin", table_name="cross_chat_sessions")
    op.drop_table("cross_chat_sessions")
