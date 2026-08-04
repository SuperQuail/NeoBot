"""add_model_usage_records

Revision ID: 017c3c17654f
Revises: 0012
Create Date: 2026-05-04 21:39:46.559305

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '017c3c17654f'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('model_usage_records',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('module_name', sa.String(), nullable=False),
    sa.Column('model_name', sa.String(), nullable=False),
    sa.Column('provider_name', sa.String(), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('conversation_kind', sa.String(), nullable=True),
    sa.Column('conversation_id', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_usage_records_created_at', 'model_usage_records', ['created_at'], unique=False)
    op.create_index('ix_usage_records_module', 'model_usage_records', ['module_name'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_usage_records_module', table_name='model_usage_records')
    op.drop_index('ix_usage_records_created_at', table_name='model_usage_records')
    op.drop_table('model_usage_records')
