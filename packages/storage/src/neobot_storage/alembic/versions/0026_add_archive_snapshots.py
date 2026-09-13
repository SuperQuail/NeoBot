"""新增档案压缩快照表

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-12

spec(4) Part C（D15）：AI 压缩在改写档案之前把原文原样留一份，
面板「压缩历史」只读展示（不提供一键恢复）。

保留策略由服务层执行：同一 (table_name, key) 只留最近 10 份
（``MAX_ARCHIVE_SNAPSHOTS_PER_KEY``），全表另有 2000 份兜底
（``MAX_ARCHIVE_SNAPSHOTS``）。因此索引为
``(table_name, key, created_at)`` 复合索引 + ``created_at`` 索引。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0026'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('archive_snapshots',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('table_name', sa.String(), nullable=False),
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('total_chars', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('reason', sa.String(), nullable=False, server_default='manual'),
    sa.Column('operator_ip', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_archive_snapshots_table_name_key_created_at',
        'archive_snapshots',
        ['table_name', 'key', 'created_at'],
        unique=False,
    )
    op.create_index('ix_archive_snapshots_created_at', 'archive_snapshots', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_archive_snapshots_created_at', table_name='archive_snapshots')
    op.drop_index('ix_archive_snapshots_table_name_key_created_at', table_name='archive_snapshots')
    op.drop_table('archive_snapshots')
