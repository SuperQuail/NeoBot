"""用量表新增计费来源与分项列

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-12

spec(4) Part A：可脚本化的消耗计费。
``cost_cny`` 的语义与类型**完全不变**（仍是可直接 SUM 的标量），因此
``repositories/usage.py`` 的 4 个聚合 SQL、报表与面板既有数值零改动。

- ``cost_source``：闭集 builtin / script:<name> / fallback:missing|error|timeout；
  带 server_default 以便存量行自动填充为 builtin；
- ``cost_detail``：脚本返回的 components / note，压缩为单行 JSON，可为 NULL。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'model_usage_records',
        sa.Column('cost_source', sa.String(), nullable=False, server_default='builtin'),
    )
    op.add_column(
        'model_usage_records',
        sa.Column('cost_detail', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('model_usage_records', 'cost_detail')
    op.drop_column('model_usage_records', 'cost_source')
