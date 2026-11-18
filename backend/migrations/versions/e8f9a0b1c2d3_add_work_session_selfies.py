"""add login and logout selfie paths to work sessions

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("work_sessions", sa.Column("login_selfie_path", sa.String(length=255), nullable=True))
    op.add_column("work_sessions", sa.Column("logout_selfie_path", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("work_sessions", "logout_selfie_path")
    op.drop_column("work_sessions", "login_selfie_path")
