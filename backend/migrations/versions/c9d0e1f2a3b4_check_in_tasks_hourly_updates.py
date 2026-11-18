"""Check-In/Check-Out location, work tasks, hourly updates, Noon report source.

* work_sessions: check-in / check-out latitude, longitude, accuracy, location
  (the selfie paths and login_at/logout_at columns are reused as Check-In /
  Check-Out selfies and times, so existing rows stay valid)
* daily_reports.source: Manual | Hourly Updates
* new tables: work_tasks, hourly_updates, hourly_update_attachments

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for prefix in ("check_in", "check_out"):
        op.add_column("work_sessions", sa.Column(f"{prefix}_latitude", sa.Numeric(9, 6), nullable=True))
        op.add_column("work_sessions", sa.Column(f"{prefix}_longitude", sa.Numeric(9, 6), nullable=True))
        op.add_column("work_sessions", sa.Column(f"{prefix}_accuracy_m", sa.Float(), nullable=True))
        op.add_column("work_sessions", sa.Column(f"{prefix}_location", sa.String(255), nullable=True))

    op.add_column("daily_reports", sa.Column("source", sa.String(30), nullable=False, server_default="Manual"))

    op.create_table(
        "work_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("target", sa.Integer(), nullable=True),
        sa.Column("unit", sa.String(40), nullable=True),
        sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="Pending"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_work_tasks_employee_id", "work_tasks", ["employee_id"])
    op.create_index("ix_work_tasks_task_date", "work_tasks", ["task_date"])
    op.create_index("ix_work_tasks_status", "work_tasks", ["status"])
    op.create_index("ix_work_tasks_employee_status", "work_tasks", ["employee_id", "status"])

    op.create_table(
        "hourly_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("work_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("work_session_id", sa.Integer(), sa.ForeignKey("work_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("update_date", sa.Date(), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("slot_start", sa.Time(), nullable=False),
        sa.Column("slot_end", sa.Time(), nullable=False),
        sa.Column("work_completed", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("units_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("task_status", sa.String(20), nullable=False, server_default="In Progress"),
        sa.Column("remaining_work", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("employee_id", "update_date", "slot_index", name="uq_hourly_update_slot"),
    )
    op.create_index("ix_hourly_updates_employee_id", "hourly_updates", ["employee_id"])
    op.create_index("ix_hourly_updates_task_id", "hourly_updates", ["task_id"])
    op.create_index("ix_hourly_updates_update_date", "hourly_updates", ["update_date"])

    op.create_table(
        "hourly_update_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hourly_update_id", sa.Integer(), sa.ForeignKey("hourly_updates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hourly_update_attachments_hourly_update_id", "hourly_update_attachments", ["hourly_update_id"])


def downgrade() -> None:
    op.drop_table("hourly_update_attachments")
    op.drop_table("hourly_updates")
    op.drop_table("work_tasks")
    op.drop_column("daily_reports", "source")
    for prefix in ("check_in", "check_out"):
        for col in ("location", "accuracy_m", "longitude", "latitude"):
            op.drop_column("work_sessions", f"{prefix}_{col}")
