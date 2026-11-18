"""Default work location for salary slips.

Adds the setting ``default_work_location``: the Location printed on a salary
slip for an employee who has no work location of their own. Its initial value
is taken from the data already in the database (the work location most
employees have), so nothing is hard-coded; it is empty when no employee has one.

No table or column changes: ``employees.work_location`` already exists.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT 1 FROM app_settings WHERE key = 'default_work_location'")).first() is not None:
        return
    row = conn.execute(sa.text(
        "SELECT TRIM(work_location) AS loc, COUNT(*) AS n FROM employees "
        "WHERE work_location IS NOT NULL AND TRIM(work_location) <> '' "
        "GROUP BY TRIM(work_location) ORDER BY n DESC, loc LIMIT 1"
    )).first()
    conn.execute(
        sa.text(
            "INSERT INTO app_settings (key, value, value_type, description, created_at, updated_at) VALUES "
            "('default_work_location', :value, 'string', "
            "'Work location printed on salary slips for employees who have none of their own', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"value": row[0] if row else ""},
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM app_settings WHERE key = 'default_work_location'"))
