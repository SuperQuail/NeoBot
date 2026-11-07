"""跨聊天会话唯一键改为含 boot_id

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-07

0030 的唯一键是 (origin, target) 四项。这带来两个问题：

1. 同一对聊天流第二次投递时走 on conflict 更新，上一次的 `reply` 会被沿用
   （INSERT 里的 reply 在冲突分支不生效），agent 看到「新任务的 id + 旧任务的回复」；
2. 唯一键不含 `boot_id`，而更新时又写 `boot_id`，于是新进程写同一对会把旧进程
   的行「接管」过去——两代进程重叠时，旧进程查不到自己刚产生的记录。

改成 (origin, target, boot_id)：同进程内复用一行并重置 reply，不同进程各留各的行，
「重启后旧记录不再显示」由查询侧的 boot_id 过滤保证，不再靠覆盖实现。

SQLite 不能直接改表级 UNIQUE，用 batch 模式重建表；数据原样搬运。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    "id", "origin_kind", "origin_id", "target_kind", "target_id",
    "task_id", "mode", "notification_mode", "status", "reply", "boot_id",
    "created_at", "updated_at",
)


def upgrade() -> None:
    with op.batch_alter_table(
        "cross_chat_sessions", recreate="always", naming_convention={}
    ) as batch:
        batch.drop_constraint("uq_cross_chat_sessions_pair", type_="unique")
        batch.create_unique_constraint(
            "uq_cross_chat_sessions_pair",
            ["origin_kind", "origin_id", "target_kind", "target_id", "boot_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "cross_chat_sessions", recreate="always", naming_convention={}
    ) as batch:
        batch.drop_constraint("uq_cross_chat_sessions_pair", type_="unique")
        batch.create_unique_constraint(
            "uq_cross_chat_sessions_pair",
            ["origin_kind", "origin_id", "target_kind", "target_id"],
        )
