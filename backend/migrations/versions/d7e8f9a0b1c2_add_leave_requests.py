"""add leave request workflow

Revision ID: d7e8f9a0b1c2
Revises: 286d92b51b39
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c4f6a7b8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("leave_type", sa.String(length=40), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("hr_remarks", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_leave_requests_employee_status", "leave_requests",
        ["employee_id", "status"], unique=False,
    )
    op.create_index(
        "ix_leave_requests_status_created", "leave_requests",
        ["status", "created_at"], unique=False,
    )
    op.create_index(
        op.f("ix_leave_requests_employee_id"), "leave_requests", ["employee_id"], unique=False
    )
    op.create_index(
        op.f("ix_leave_requests_status"), "leave_requests", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_leave_requests_status"), table_name="leave_requests")
    op.drop_index(op.f("ix_leave_requests_employee_id"), table_name="leave_requests")
    op.drop_index("ix_leave_requests_status_created", table_name="leave_requests")
    op.drop_index("ix_leave_requests_employee_status", table_name="leave_requests")
    op.drop_table("leave_requests")
