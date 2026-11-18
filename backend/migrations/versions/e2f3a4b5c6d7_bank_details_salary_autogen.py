"""Bank details approval workflow and automatic monthly salary slips.

Schema (additive - no column or row is dropped):
* employees.ifsc_code, employees.bank_details_approved_at
  (bank_name / bank_account_no / pan_number already exist and keep holding the
  APPROVED details that salary slips print)
* bank_detail_requests                    (employee submission -> HR/Admin review)
* salary_records.auto_generated, salary_records.generated_from_id
* app_settings.salary_auto_generate      (default true)

Existing data is untouched: approved bank values already stored on employees
stay as they are, existing salary records are marked auto_generated = false.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("ifsc_code", sa.String(length=11), nullable=True))
        batch.add_column(sa.Column("bank_details_approved_at", sa.DateTime(), nullable=True))

    op.create_table(
        "bank_detail_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bank_name", sa.String(length=120), nullable=False),
        sa.Column("account_number", sa.String(length=34), nullable=False),
        sa.Column("ifsc_code", sa.String(length=11), nullable=False),
        sa.Column("pan_number", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bank_detail_requests_employee_id", "bank_detail_requests", ["employee_id"])
    op.create_index("ix_bank_detail_requests_status", "bank_detail_requests", ["status"])
    op.create_index("ix_bank_detail_requests_employee_status", "bank_detail_requests", ["employee_id", "status"])

    with op.batch_alter_table("salary_records") as batch:
        batch.add_column(sa.Column("auto_generated", sa.Boolean(), server_default=sa.text("false"), nullable=False))
        batch.add_column(sa.Column("generated_from_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_salary_records_generated_from_id", "salary_records",
            ["generated_from_id"], ["id"], ondelete="SET NULL",
        )

    conn = op.get_bind()
    if conn.execute(sa.text("SELECT 1 FROM app_settings WHERE key = 'salary_auto_generate'")).first() is None:
        conn.execute(sa.text(
            "INSERT INTO app_settings (key, value, value_type, description, created_at, updated_at) VALUES "
            "('salary_auto_generate', 'true', 'bool', "
            "'Create each month''s salary slip automatically from the employee''s previous month', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM app_settings WHERE key = 'salary_auto_generate'"))
    with op.batch_alter_table("salary_records") as batch:
        batch.drop_constraint("fk_salary_records_generated_from_id", type_="foreignkey")
        batch.drop_column("generated_from_id")
        batch.drop_column("auto_generated")
    op.drop_index("ix_bank_detail_requests_employee_status", table_name="bank_detail_requests")
    op.drop_index("ix_bank_detail_requests_status", table_name="bank_detail_requests")
    op.drop_index("ix_bank_detail_requests_employee_id", table_name="bank_detail_requests")
    op.drop_table("bank_detail_requests")
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("bank_details_approved_at")
        batch.drop_column("ifsc_code")
