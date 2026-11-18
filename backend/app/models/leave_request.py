from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import TimestampMixin


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_employee_status", "employee_id", "status"),
        Index("ix_leave_requests_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Part of the office day the leave covers: Full Day, Morning Half
    # (10:00 AM-1:00 PM) or Afternoon Half (1:00 PM-6:00 PM). A half-day
    # period is only valid for a single-date request.
    leave_period: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Full Day", server_default="Full Day"
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending", index=True)
    hr_remarks: Mapped[Optional[str]] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Hierarchy approval flow. approval_stage says who acts next while the
    # request is Pending: Manager -> HR -> (Admin for HR's own leave).
    # The final decision stays in status / hr_remarks / reviewed_*.
    approval_stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default="HR", server_default="HR", index=True
    )
    manager_status: Mapped[Optional[str]] = mapped_column(String(20))
    manager_remarks: Mapped[Optional[str]] = mapped_column(Text)
    manager_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    manager_reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    employee: Mapped["Employee"] = relationship(back_populates="leave_requests")  # noqa: F821
    reviewed_by: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewed_by_id])  # noqa: F821
    manager_reviewed_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        foreign_keys=[manager_reviewed_by_id]
    )
