"""add scheduled task tables"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_uuid", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("recurrence", sa.String(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bindings_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("completed_window_keys_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_uuid"),
    )
    op.create_index(
        "ix_scheduled_tasks_state_start_at",
        "scheduled_tasks",
        ["state", "start_at"],
    )
    op.create_index(
        "ix_scheduled_tasks_recurrence_state",
        "scheduled_tasks",
        ["recurrence", "state"],
    )

    op.create_table(
        "completed_scheduled_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_uuid", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("recurrence", sa.String(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bindings_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completion_reason", sa.Text(), nullable=False),
        sa.Column("archived_payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_completed_scheduled_tasks_completed_at",
        "completed_scheduled_tasks",
        ["completed_at"],
    )
    op.create_index(
        "ix_completed_scheduled_tasks_task_uuid",
        "completed_scheduled_tasks",
        ["task_uuid"],
    )


def downgrade() -> None:
    op.drop_index("ix_completed_scheduled_tasks_task_uuid", table_name="completed_scheduled_tasks")
    op.drop_index("ix_completed_scheduled_tasks_completed_at", table_name="completed_scheduled_tasks")
    op.drop_table("completed_scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_recurrence_state", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_state_start_at", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
