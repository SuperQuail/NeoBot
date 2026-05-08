"""add_cache_hit_tokens_to_usage

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-07

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'model_usage_records',
        sa.Column('cache_hit_tokens', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'model_usage_records',
        sa.Column('cache_miss_tokens', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('model_usage_records', 'cache_miss_tokens')
    op.drop_column('model_usage_records', 'cache_hit_tokens')
