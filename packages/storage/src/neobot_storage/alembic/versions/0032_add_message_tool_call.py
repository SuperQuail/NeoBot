"""messages 表新增工具调用元数据列

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-11

工具调用（发送/非发送工具）的元数据需要跟触发它的那条消息一起持久化：软重启后
从本地历史补齐上下文时，才能看到「这条回复是哪个工具产生的」。列类型是 Text 的
JSON 字符串（NULL = 该消息没有关联工具调用）：

- 不建独立表：工具调用与消息是 1:1，且只按消息读取，独立表只会多一次 join；
- 存 JSON 文本而不是拆列：不同工具的参数/结果形状各异，storage 不解释内容，
  schema 只保证「能原样取回」；
- nullable：历史消息（升级前）与普通聊天消息都没有该字段。

downgrade 只删该列，既有消息行不受影响，可往返。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("tool_call_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "tool_call_json")
