"""Half-day leave periods and the expected attendance window per session.

* leave_requests.leave_period  - Full Day / Morning Half / Afternoon Half
* work_sessions.expected_login_time / expected_logout_time / leave_period
* Re-asserts the mandatory document set: Photograph, Aadhaar, PAN, CV are
  required; Highest Qualification and Experience Letter stay optional.

Existing rows are preserved: old leave requests become "Full Day" (which is what
they always meant) and old sessions keep their stored minutes.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leave_requests",
        sa.Column("leave_period", sa.String(20), nullable=False, server_default="Full Day"),
    )
    op.add_column("work_sessions", sa.Column("expected_login_time", sa.Time(), nullable=True))
    op.add_column("work_sessions", sa.Column("expected_logout_time", sa.Time(), nullable=True))
    op.add_column("work_sessions", sa.Column("leave_period", sa.String(20), nullable=True))
    # Every session recorded before this release used the standard window.
    op.execute(
        "UPDATE work_sessions SET expected_login_time = '10:00:00', "
        "expected_logout_time = '18:00:00' WHERE expected_login_time IS NULL"
    )

    op.execute("UPDATE document_types SET is_required = TRUE WHERE code IN ('PHOTO','AADHAAR','PAN','CV')")
    op.execute("UPDATE document_types SET is_required = FALSE WHERE code IN ('QUALIFICATION','EXPERIENCE','OTHER')")


def downgrade() -> None:
    op.drop_column("work_sessions", "leave_period")
    op.drop_column("work_sessions", "expected_logout_time")
    op.drop_column("work_sessions", "expected_login_time")
    op.drop_column("leave_requests", "leave_period")
