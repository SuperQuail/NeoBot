"""新增用户头像本地存储字段

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-12

spec(5) §4.9（R33–R37 / D13）：本体级头像存储 AvatarStore 需要为
「聊过天的用户」保存一份本地头像。字段**直接加在 user_data 上**，理由是
「有 user_data 行 = 认识该用户」——它天然覆盖「聊过天的人」，不需要另建
一张头像表，也就不会出现「资料有行、头像没行」的两处数据不一致。

三列语义：

- avatar_path：本地 PNG 路径（<DATA_DIR>/avatars/<user_id>.png）；
  NULL = 尚无本地头像。获取失败时**原样保留**（宁可旧头像，不要空头像）。
- avatar_fetched_at：上次**成功**获取头像的 UTC 时间；获取失败时不改写。
  惰性刷新按它判定「是否超过 refresh_days」。
- avatar_fail_count：连续失败次数，成功一次清零；默认 0（server_default
  保证既有行与不显式赋值的新行都拿到 0）。

downgrade 只移除这三列，既有用户资料不受影响，可往返。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_data", sa.Column("avatar_path", sa.String(), nullable=True))
    op.add_column(
        "user_data",
        sa.Column("avatar_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_data",
        sa.Column(
            "avatar_fail_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_data", "avatar_fail_count")
    op.drop_column("user_data", "avatar_fetched_at")
    op.drop_column("user_data", "avatar_path")
