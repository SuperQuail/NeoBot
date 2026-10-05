"""新增聊天图片引用索引表

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-06

图片解析结果按**内容哈希**存在 `images` 表；而「拉不到」的图片（设备侧聊天记录
已被清理 / 图片过久被回收）拿不到字节，算不出哈希，也就反查不到描述。`image_refs`
按「引用摘要」冗余存一份描述，专供图片过期时回显 —— 见
`app/src/neobot_app/image/unavailable.py`。

三列语义：

- source_ref：引用键（`file:<id>` / `url:<...>` / `msg:<id>:<index>`）的 sha1 前
  32 位。存摘要不存原文：临时 URL 可能带 rkey 一类令牌，file id 也没有长期价值。
- analysis_text：当时视觉模型给出的描述原文（回显用）。
- updated_at：清理按它做保留期；同一引用重复写入只留最新一份。

downgrade 只删表，既有 `images` 数据不受影响，可往返。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_refs",
        sa.Column("source_ref", sa.String(), nullable=False),
        sa.Column("analysis_text", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_ref"),
    )
    op.create_index("ix_image_refs_updated_at", "image_refs", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_image_refs_updated_at", table_name="image_refs")
    op.drop_table("image_refs")
