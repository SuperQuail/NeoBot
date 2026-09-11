"""新增沙箱维护运行记录表

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-10

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('maintenance_runs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('trigger', sa.String(), nullable=False),
    sa.Column('tool_calls', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('skipped_reason', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_maintenance_runs_started_at', 'maintenance_runs', ['started_at'], unique=False)
    op.create_index('ix_maintenance_runs_status', 'maintenance_runs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_maintenance_runs_status', table_name='maintenance_runs')
    op.drop_index('ix_maintenance_runs_started_at', table_name='maintenance_runs')
    op.drop_table('maintenance_runs')
