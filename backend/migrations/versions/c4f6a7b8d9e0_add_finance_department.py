"""add Finance department

Adds Finance to installations created before Finance was included in the
default department catalogue. The insert is idempotent and does not modify
existing employees or department records.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4f6a7b8d9e0"
down_revision: Union[str, None] = "b7d31f04ae19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text("SELECT 1 FROM departments WHERE lower(name) = lower(:name) LIMIT 1"),
        {"name": "Finance"},
    ).first()
    if not exists:
        conn.execute(
            sa.text(
                "INSERT INTO departments (name, code, description, is_active) "
                "VALUES (:name, :code, :description, TRUE)"
            ),
            {
                "name": "Finance",
                "code": "FIN",
                "description": "Finance and payroll operations",
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM departments "
            "WHERE lower(name) = lower(:name) AND code = :code"
        ),
        {"name": "Finance", "code": "FIN"},
    )
