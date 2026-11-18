"""intern payslip download requests

Adds the request record behind the intern download workflow: the reason the
intern gave, HR's decision, the reviewer and the timestamps.

This does NOT introduce a second permission system. Whether a download is
allowed is still `salary_records.intern_download_allowed`; approving a request
sets that flag on that one salary record.

Revision ID: b7d31f04ae19
Revises: 9c41ab7de552
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d31f04ae19"
down_revision: Union[str, None] = "9c41ab7de552"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intern_payslip_download_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("salary_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("hr_remarks", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("hr_reviewer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"],
                                name="fk_ipdr_employee", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["salary_id"], ["salary_records.id"],
                                name="fk_ipdr_salary", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hr_reviewer_id"], ["users.id"],
                                name="fk_ipdr_reviewer", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ipdr_employee_status", "intern_payslip_download_requests",
                    ["employee_id", "status"], unique=False)
    op.create_index("ix_ipdr_salary_status", "intern_payslip_download_requests",
                    ["salary_id", "status"], unique=False)
    op.create_index("ix_ipdr_status_created", "intern_payslip_download_requests",
                    ["status", "created_at"], unique=False)
    op.create_index(op.f("ix_intern_payslip_download_requests_employee_id"),
                    "intern_payslip_download_requests", ["employee_id"], unique=False)
    op.create_index(op.f("ix_intern_payslip_download_requests_salary_id"),
                    "intern_payslip_download_requests", ["salary_id"], unique=False)
    op.create_index(op.f("ix_intern_payslip_download_requests_status"),
                    "intern_payslip_download_requests", ["status"], unique=False)


def downgrade() -> None:
    for name in (
        op.f("ix_intern_payslip_download_requests_status"),
        op.f("ix_intern_payslip_download_requests_salary_id"),
        op.f("ix_intern_payslip_download_requests_employee_id"),
        "ix_ipdr_status_created", "ix_ipdr_salary_status", "ix_ipdr_employee_status",
    ):
        op.drop_index(name, table_name="intern_payslip_download_requests")
    op.drop_table("intern_payslip_download_requests")
