"""add_bilibili_links

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-19

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0020'
down_revision: Union[str, None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bilibili_links',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bilibili_uid', sa.Integer(), nullable=False),
        sa.Column('qq_number', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bilibili_uid', 'qq_number', name='uq_bilibili_links_uid_qq'),
    )
    op.create_index('ix_bilibili_links_bilibili_uid', 'bilibili_links', ['bilibili_uid'])
    op.create_index('ix_bilibili_links_qq_number', 'bilibili_links', ['qq_number'])


def downgrade() -> None:
    op.drop_index('ix_bilibili_links_qq_number', table_name='bilibili_links')
    op.drop_index('ix_bilibili_links_bilibili_uid', table_name='bilibili_links')
    op.drop_table('bilibili_links')
