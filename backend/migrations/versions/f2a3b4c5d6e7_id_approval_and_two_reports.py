"""Employee ID approval workflow and separate Noon/EOD daily reports.

Revision ID: f2a3b4c5d6e7
Revises: e8f9a0b1c2d3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- Employee ID approval ----------------
    op.add_column("employees", sa.Column("id_card_status", sa.String(20), nullable=True))
    op.add_column("employees", sa.Column("id_card_requested_at", sa.DateTime(), nullable=True))
    op.add_column("employees", sa.Column("id_card_approved_at", sa.DateTime(), nullable=True))
    op.add_column("employees", sa.Column("id_card_rejected_at", sa.DateTime(), nullable=True))
    op.add_column("employees", sa.Column("id_card_approval_remarks", sa.Text(), nullable=True))
    op.add_column("employees", sa.Column("id_card_approved_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_employees_id_card_approved_by",
        "employees",
        "users",
        ["id_card_approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_employees_id_card_status", "employees", ["id_card_status"], unique=False)

    # Existing issued IDs are already approved and must remain available.
    op.execute(
        "UPDATE employees SET id_card_status = 'Approved', "
        "id_card_approved_at = COALESCE(id_card_approved_at, id_card_issued_at) "
        "WHERE unique_employee_id IS NOT NULL"
    )
    op.execute("UPDATE employees SET id_card_status = 'Pending' WHERE id_card_status IS NULL")
    op.alter_column("employees", "id_card_status", nullable=False, server_default="Pending")

    # ---------------- Noon / EOD reports ----------------
    op.add_column(
        "daily_reports",
        sa.Column("report_type", sa.String(10), nullable=True, server_default="EOD"),
    )
    op.execute("UPDATE daily_reports SET report_type = 'EOD' WHERE report_type IS NULL")
    op.drop_constraint("uq_daily_report_employee_date", "daily_reports", type_="unique")
    op.create_unique_constraint(
        "uq_daily_report_employee_date_type",
        "daily_reports",
        ["employee_id", "report_date", "report_type"],
    )
    op.create_index("ix_daily_reports_report_type", "daily_reports", ["report_type"], unique=False)
    op.alter_column("daily_reports", "report_type", nullable=False, server_default="EOD")


def downgrade() -> None:
    op.drop_index("ix_daily_reports_report_type", table_name="daily_reports")
    op.drop_constraint("uq_daily_report_employee_date_type", "daily_reports", type_="unique")
    op.create_unique_constraint(
        "uq_daily_report_employee_date", "daily_reports", ["employee_id", "report_date"]
    )
    op.drop_column("daily_reports", "report_type")

    op.drop_index("ix_employees_id_card_status", table_name="employees")
    op.drop_constraint("fk_employees_id_card_approved_by", "employees", type_="foreignkey")
    for col in (
        "id_card_approved_by_id", "id_card_approval_remarks", "id_card_rejected_at",
        "id_card_approved_at", "id_card_requested_at", "id_card_status",
    ):
        op.drop_column("employees", col)
