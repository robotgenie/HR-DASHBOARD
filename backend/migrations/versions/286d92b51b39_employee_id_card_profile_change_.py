"""employee id card, profile change requests, intern payslip permission

Adds:
  * employees.unique_employee_id (RGEMP001...) plus issue/lock timestamps
  * profile_change_requests: HR-approved changes to locked identity fields
  * salary_records.intern_download_allowed: per-record intern download permission

Also backfills a unique employee id for every existing employee whose profile is
already complete, so upgrading an installation with live data does not leave
those employees without an id or an ID card.

Revision ID: 286d92b51b39
Revises: f5e3b245eda5
Create Date: 2026-09-17 10:44:51.800590
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "286d92b51b39"
down_revision: Union[str, None] = "f5e3b245eda5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every field that must be present before an id is issued (photo included).
COMPLETE_PROFILE_SQL = """
    full_name IS NOT NULL AND full_name <> ''
    AND phone IS NOT NULL AND phone <> ''
    AND date_of_birth IS NOT NULL
    AND gender IS NOT NULL AND gender <> ''
    AND address IS NOT NULL AND address <> ''
    AND emergency_contact_name IS NOT NULL AND emergency_contact_name <> ''
    AND emergency_contact_phone IS NOT NULL AND emergency_contact_phone <> ''
    AND emergency_contact_relation IS NOT NULL AND emergency_contact_relation <> ''
    AND designation IS NOT NULL AND designation <> ''
    AND photo_path IS NOT NULL AND photo_path <> ''
"""


def _backfill_employee_ids() -> None:
    """Assign RGEMP ids in joining order. Engine-agnostic, so no window functions."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"SELECT id FROM employees WHERE unique_employee_id IS NULL "
            f"AND {COMPLETE_PROFILE_SQL} ORDER BY id"
        )
    ).fetchall()

    start = bind.execute(
        sa.text("SELECT COUNT(*) FROM employees WHERE unique_employee_id IS NOT NULL")
    ).scalar() or 0

    for offset, row in enumerate(rows, start=start + 1):
        bind.execute(
            sa.text(
                "UPDATE employees SET unique_employee_id = :eid, "
                "employee_id_issued_at = CURRENT_TIMESTAMP, "
                "id_card_issued_at = CURRENT_TIMESTAMP, "
                "identity_locked_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"eid": f"RGEMP{offset:03d}", "id": row[0]},
        )


def upgrade() -> None:
    op.create_table(
        "profile_change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=60), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("hr_remarks", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"],
            name="fk_pcr_employee", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"],
            name="fk_pcr_reviewed_by", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pcr_employee_status", "profile_change_requests",
        ["employee_id", "status"], unique=False,
    )
    op.create_index(
        "ix_pcr_status_created", "profile_change_requests",
        ["status", "created_at"], unique=False,
    )
    op.create_index(
        op.f("ix_profile_change_requests_employee_id"), "profile_change_requests",
        ["employee_id"], unique=False,
    )
    op.create_index(
        op.f("ix_profile_change_requests_status"), "profile_change_requests",
        ["status"], unique=False,
    )

    op.add_column(
        "employees", sa.Column("unique_employee_id", sa.String(length=20), nullable=True)
    )
    op.add_column("employees", sa.Column("employee_id_issued_at", sa.DateTime(), nullable=True))
    op.add_column("employees", sa.Column("identity_locked_at", sa.DateTime(), nullable=True))
    op.add_column("employees", sa.Column("id_card_issued_at", sa.DateTime(), nullable=True))
    op.create_index(
        op.f("ix_employees_unique_employee_id"), "employees",
        ["unique_employee_id"], unique=True,
    )

    # server_default keeps the NOT NULL valid for rows that already exist
    op.add_column(
        "salary_records",
        sa.Column(
            "intern_download_allowed", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
    )
    op.add_column(
        "salary_records", sa.Column("download_permission_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "salary_records",
        sa.Column("download_permission_by_id", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("salary_records") as batch:
        batch.create_foreign_key(
            "fk_salary_download_permission_by", "users",
            ["download_permission_by_id"], ["id"], ondelete="SET NULL",
        )

    _backfill_employee_ids()


def downgrade() -> None:
    with op.batch_alter_table("salary_records") as batch:
        batch.drop_constraint("fk_salary_download_permission_by", type_="foreignkey")
    op.drop_column("salary_records", "download_permission_by_id")
    op.drop_column("salary_records", "download_permission_at")
    op.drop_column("salary_records", "intern_download_allowed")

    op.drop_index(op.f("ix_employees_unique_employee_id"), table_name="employees")
    op.drop_column("employees", "id_card_issued_at")
    op.drop_column("employees", "identity_locked_at")
    op.drop_column("employees", "employee_id_issued_at")
    op.drop_column("employees", "unique_employee_id")

    op.drop_index(
        op.f("ix_profile_change_requests_status"), table_name="profile_change_requests"
    )
    op.drop_index(
        op.f("ix_profile_change_requests_employee_id"), table_name="profile_change_requests"
    )
    op.drop_index("ix_pcr_status_created", table_name="profile_change_requests")
    op.drop_index("ix_pcr_employee_status", table_name="profile_change_requests")
    op.drop_table("profile_change_requests")
