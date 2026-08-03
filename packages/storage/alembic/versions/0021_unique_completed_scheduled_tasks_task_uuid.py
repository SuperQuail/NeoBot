"""add unique constraint on completed_scheduled_tasks.task_uuid

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-03

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM completed_scheduled_tasks WHERE id NOT IN "
        "(SELECT MIN(id) FROM completed_scheduled_tasks GROUP BY task_uuid)"
    )
    op.create_index(
        "uq_completed_scheduled_tasks_task_uuid",
        "completed_scheduled_tasks",
        ["task_uuid"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_completed_scheduled_tasks_task_uuid",
        table_name="completed_scheduled_tasks",
    )
