"""Attendance timing and document requirement updates."""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("work_sessions", sa.Column("work_date", sa.Date(), nullable=True))
    op.add_column("work_sessions", sa.Column("work_period", sa.String(20), nullable=True, server_default="Full Day"))
    op.add_column("work_sessions", sa.Column("late_login_minutes", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("work_sessions", sa.Column("late_login_reason", sa.String(500), nullable=True))
    op.add_column("work_sessions", sa.Column("early_logout_minutes", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("work_sessions", sa.Column("early_logout_reason", sa.String(500), nullable=True))
    op.add_column("work_sessions", sa.Column("extra_work_minutes", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("work_sessions", sa.Column("work_duration_minutes", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("work_sessions", sa.Column("attendance_status", sa.String(30), nullable=True, server_default="Present"))
    op.add_column("work_sessions", sa.Column("logout_reason", sa.String(500), nullable=True))
    op.create_index("ix_work_sessions_work_date", "work_sessions", ["work_date"], unique=False)
    op.execute("UPDATE work_sessions SET work_date=(login_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date WHERE work_date IS NULL")
    for col in ["work_date","work_period","late_login_minutes","early_logout_minutes","extra_work_minutes","work_duration_minutes","attendance_status"]:
        op.alter_column("work_sessions", col, nullable=False)
    op.execute("UPDATE document_types SET name='Aadhaar Card', code='AADHAAR', is_required=TRUE WHERE code='AADHAAR_FRONT'")
    op.execute("UPDATE document_types SET is_required=FALSE, name='Aadhaar Card - Back (Legacy)' WHERE code='AADHAAR_BACK'")
    op.execute("UPDATE document_types SET is_required=FALSE WHERE code IN ('QUALIFICATION','EXPERIENCE')")
    op.execute("UPDATE document_types SET is_required=TRUE WHERE code IN ('PHOTO','PAN','CV')")

def downgrade():
    op.drop_index("ix_work_sessions_work_date", table_name="work_sessions")
    for col in ["logout_reason","attendance_status","work_duration_minutes","extra_work_minutes","early_logout_reason","early_logout_minutes","late_login_reason","late_login_minutes","work_period","work_date"]:
        op.drop_column("work_sessions", col)
