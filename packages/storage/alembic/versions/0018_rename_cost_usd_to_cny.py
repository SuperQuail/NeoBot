"""rename_cost_usd_to_cny

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-05

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'model_usage_records',
        'cost_usd',
        new_column_name='cost_cny',
    )


def downgrade() -> None:
    op.alter_column(
        'model_usage_records',
        'cost_cny',
        new_column_name='cost_usd',
    )
