"""Admin and Manager roles, reporting hierarchy, hierarchical leave approval,
task division and Excel import batches.

Schema (additive - no column or row is dropped):
* roles: ADMIN and MANAGER rows; HR_ADMIN relabelled "HR"
* users.full_name / phone / title            (profile of the Admin, who has no employee record)
* employees.reporting_hr_id (+ index), employees.internship_details,
  index on employees.reporting_manager_id
* leave_requests.approval_stage / manager_status / manager_remarks /
  manager_reviewed_at / manager_reviewed_by_id
* work_tasks.parent_task_id                  (manager divides a task among the team)
* excel_import_batches                        (preview -> confirm; never the file itself)
* app_settings.hr_sees_unassigned            (default true)

Data (existing records preserved, only reporting lines are normalised):
1. A "reporting manager" that is an HR account (the original form only listed
   HR staff there) becomes the Reporting HR.
2. HR accounts report to the Admin only: their reporting lines are cleared.
3. An employee that other people report to is promoted to the MANAGER role
   (an intern referenced that way is not promoted; the reference is cleared).
4. A Manager reports to an HR, not to another manager: their own manager line
   is converted to that manager's HR.
5. If the organisation has exactly one active HR, every Manager/Employee
   without a Reporting HR is assigned to that HR.
6. Employees inherit their manager's Reporting HR.
7. Pending leave keeps HR as the deciding stage (current behaviour); pending
   leave of HR accounts moves to the Admin stage; decided leave is Closed.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _role_id(conn, name):
    return conn.execute(sa.text("SELECT id FROM roles WHERE name = :n"), {"n": name}).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # ---------------------------------------------------------------- schema
    op.add_column("users", sa.Column("full_name", sa.String(160), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("title", sa.String(120), nullable=True))

    op.add_column("employees", sa.Column("reporting_hr_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_employees_reporting_hr_id", "employees", "employees",
                          ["reporting_hr_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_employees_reporting_hr_id", "employees", ["reporting_hr_id"])
    op.create_index("ix_employees_reporting_manager_id", "employees", ["reporting_manager_id"])
    op.add_column("employees", sa.Column("internship_details", sa.Text(), nullable=True))

    op.add_column("leave_requests", sa.Column("approval_stage", sa.String(20), nullable=False, server_default="HR"))
    op.create_index("ix_leave_requests_approval_stage", "leave_requests", ["approval_stage"])
    op.add_column("leave_requests", sa.Column("manager_status", sa.String(20), nullable=True))
    op.add_column("leave_requests", sa.Column("manager_remarks", sa.Text(), nullable=True))
    op.add_column("leave_requests", sa.Column("manager_reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("leave_requests", sa.Column("manager_reviewed_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_leave_requests_manager_reviewed_by_id", "leave_requests", "users",
                          ["manager_reviewed_by_id"], ["id"], ondelete="SET NULL")

    op.add_column("work_tasks", sa.Column("parent_task_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_work_tasks_parent_task_id", "work_tasks", "work_tasks",
                          ["parent_task_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_work_tasks_parent_task_id", "work_tasks", ["parent_task_id"])

    json_type = sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")
    op.create_table(
        "excel_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("status", sa.String(20), nullable=False, server_default="Previewed"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_excel_import_batches_token", "excel_import_batches", ["token"], unique=True)
    op.create_index("ix_excel_import_batches_created_by_id", "excel_import_batches", ["created_by_id"])
    op.create_index("ix_excel_import_batches_status", "excel_import_batches", ["status"])

    # ----------------------------------------------------------------- roles
    for name, label, description in (
        ("ADMIN", "Admin", "Organisation administrator - monitors the whole organisation"),
        ("MANAGER", "Manager", "Supervises the employees and interns reporting to them"),
    ):
        if _role_id(conn, name) is None:
            conn.execute(
                sa.text("INSERT INTO roles (name, label, description, created_at, updated_at) "
                        "VALUES (:n, :l, :d, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                {"n": name, "l": label, "d": description},
            )
    conn.execute(sa.text("UPDATE roles SET label = 'HR', description = 'HR - manages the hierarchy assigned to them' "
                         "WHERE name = 'HR_ADMIN'"))
    hr_role = _role_id(conn, "HR_ADMIN")
    mgr_role = _role_id(conn, "MANAGER")
    emp_role = _role_id(conn, "EMPLOYEE")

    if conn.execute(sa.text("SELECT 1 FROM app_settings WHERE key = 'hr_sees_unassigned'")).first() is None:
        conn.execute(sa.text(
            "INSERT INTO app_settings (key, value, value_type, description, created_at, updated_at) VALUES "
            "('hr_sees_unassigned', 'true', 'bool', "
            "'Let every HR see employees/managers that have no reporting HR assigned yet', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))

    # ------------------------------------------------------- hierarchy data
    def rows(sql, **params):
        return conn.execute(sa.text(sql), params).fetchall()

    people = {r.id: r for r in rows(
        "SELECT e.id, e.reporting_manager_id, u.role_id, d.name AS dept "
        "FROM employees e JOIN users u ON u.id = e.user_id JOIN departments d ON d.id = e.department_id")}

    # 1. reporting manager that is an HR -> reporting HR
    for p in people.values():
        target = people.get(p.reporting_manager_id)
        if target is not None and target.role_id == hr_role:
            conn.execute(sa.text("UPDATE employees SET reporting_hr_id = :h, reporting_manager_id = NULL WHERE id = :i"),
                         {"h": target.id, "i": p.id})
    # 2. HR accounts report to the Admin only
    conn.execute(sa.text("UPDATE employees SET reporting_manager_id = NULL, reporting_hr_id = NULL "
                         "WHERE user_id IN (SELECT id FROM users WHERE role_id = :r)"), {"r": hr_role})

    # 3. employees with direct reports become managers
    referenced = {r.reporting_manager_id for r in rows(
        "SELECT DISTINCT reporting_manager_id FROM employees WHERE reporting_manager_id IS NOT NULL")}
    for mid in referenced:
        p = people.get(mid)
        if p is None or p.role_id != emp_role:
            continue
        if p.dept == "Internship":
            conn.execute(sa.text("UPDATE employees SET reporting_manager_id = NULL WHERE reporting_manager_id = :m"),
                         {"m": mid})
            continue
        conn.execute(sa.text("UPDATE users SET role_id = :r WHERE id = (SELECT user_id FROM employees WHERE id = :m)"),
                     {"r": mgr_role, "m": mid})

    # 4. managers do not report to managers: take that manager's HR instead
    for r in rows("SELECT e.id, m.reporting_hr_id AS hr FROM employees e JOIN users u ON u.id = e.user_id "
                  "JOIN employees m ON m.id = e.reporting_manager_id WHERE u.role_id = :r", r=mgr_role):
        conn.execute(sa.text("UPDATE employees SET reporting_manager_id = NULL, "
                             "reporting_hr_id = COALESCE(reporting_hr_id, :h) WHERE id = :i"), {"h": r.hr, "i": r.id})

    # 5. a single HR owns everyone not yet assigned
    hrs = rows("SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id "
               "WHERE u.role_id = :r AND u.is_active = :t", r=hr_role, t=True)
    if len(hrs) == 1:
        conn.execute(sa.text(
            "UPDATE employees SET reporting_hr_id = :h WHERE reporting_hr_id IS NULL AND user_id IN "
            "(SELECT id FROM users WHERE role_id IN (:m, :e))"), {"h": hrs[0].id, "m": mgr_role, "e": emp_role})

    # 6. employees inherit their manager's HR
    for r in rows("SELECT e.id, m.reporting_hr_id AS hr FROM employees e "
                  "JOIN employees m ON m.id = e.reporting_manager_id"):
        conn.execute(sa.text("UPDATE employees SET reporting_hr_id = :h WHERE id = :i"), {"h": r.hr, "i": r.id})

    # 7. leave stages
    conn.execute(sa.text("UPDATE leave_requests SET approval_stage = 'Closed' WHERE status <> 'Pending'"))
    conn.execute(sa.text(
        "UPDATE leave_requests SET approval_stage = 'Admin' WHERE status = 'Pending' AND employee_id IN "
        "(SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id WHERE u.role_id = :r)"), {"r": hr_role})


def downgrade() -> None:
    conn = op.get_bind()
    emp_role = _role_id(conn, "EMPLOYEE")
    # Managers fall back to employees; Admin accounts have no employee record and are removed.
    conn.execute(sa.text("UPDATE users SET role_id = :e WHERE role_id = (SELECT id FROM roles WHERE name = 'MANAGER')"),
                 {"e": emp_role})
    op.drop_index("ix_excel_import_batches_status", table_name="excel_import_batches")
    op.drop_index("ix_excel_import_batches_created_by_id", table_name="excel_import_batches")
    op.drop_index("ix_excel_import_batches_token", table_name="excel_import_batches")
    op.drop_table("excel_import_batches")
    op.drop_index("ix_work_tasks_parent_task_id", table_name="work_tasks")
    op.drop_constraint("fk_work_tasks_parent_task_id", "work_tasks", type_="foreignkey")
    op.drop_column("work_tasks", "parent_task_id")
    op.drop_constraint("fk_leave_requests_manager_reviewed_by_id", "leave_requests", type_="foreignkey")
    for col in ("manager_reviewed_by_id", "manager_reviewed_at", "manager_remarks", "manager_status"):
        op.drop_column("leave_requests", col)
    op.drop_index("ix_leave_requests_approval_stage", table_name="leave_requests")
    op.drop_column("leave_requests", "approval_stage")
    op.drop_column("employees", "internship_details")
    op.drop_index("ix_employees_reporting_manager_id", table_name="employees")
    op.drop_index("ix_employees_reporting_hr_id", table_name="employees")
    op.drop_constraint("fk_employees_reporting_hr_id", "employees", type_="foreignkey")
    op.drop_column("employees", "reporting_hr_id")
    op.drop_column("users", "title")
    op.drop_column("users", "phone")
    op.drop_column("users", "full_name")
    conn.execute(sa.text("DELETE FROM users WHERE role_id = (SELECT id FROM roles WHERE name = 'ADMIN')"))
    conn.execute(sa.text("DELETE FROM roles WHERE name IN ('ADMIN', 'MANAGER')"))
    conn.execute(sa.text("DELETE FROM app_settings WHERE key = 'hr_sees_unassigned'"))
