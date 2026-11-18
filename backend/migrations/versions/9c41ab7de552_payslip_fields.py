"""payroll fields for the payslip: location, bank, PAN and LOP

Adds the employee payroll identity fields the payslip prints (Location, Bank
Name, Bank Account No., PAN No.) and the per-period loss-of-pay day count.
All are nullable / default 0, so existing rows are untouched.

Revision ID: 9c41ab7de552
Revises: 286d92b51b39
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9c41ab7de552"
down_revision: Union[str, None] = "286d92b51b39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("work_location", sa.String(length=120), nullable=True))
    op.add_column("employees", sa.Column("bank_name", sa.String(length=120), nullable=True))
    op.add_column("employees", sa.Column("bank_account_no", sa.String(length=34), nullable=True))
    op.add_column("employees", sa.Column("pan_number", sa.String(length=10), nullable=True))
    op.add_column(
        "salary_records",
        sa.Column("lop_days", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("salary_records", "lop_days")
    op.drop_column("employees", "pan_number")
    op.drop_column("employees", "bank_account_no")
    op.drop_column("employees", "bank_name")
    op.drop_column("employees", "work_location")
