from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.timeutil import utcnow


class WorkSession(Base):
    """Login/logout times, recorded independently of daily-report submission."""

    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    login_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow, index=True
    )
    logout_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # login_at / logout_at are the Check-In / Check-Out times; the selfie paths
    # hold the live Check-In / Check-Out selfies (names kept for existing data).
    login_selfie_path: Mapped[Optional[str]] = mapped_column(String(255))
    logout_selfie_path: Mapped[Optional[str]] = mapped_column(String(255))
    check_in_latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    check_in_longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    check_in_accuracy_m: Mapped[Optional[float]] = mapped_column(Float)
    check_in_location: Mapped[Optional[str]] = mapped_column(String(255))
    check_out_latitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    check_out_longitude: Mapped[Optional[float]] = mapped_column(Numeric(9, 6))
    check_out_accuracy_m: Mapped[Optional[float]] = mapped_column(Float)
    check_out_location: Mapped[Optional[str]] = mapped_column(String(255))
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    work_period: Mapped[str] = mapped_column(String(20), default="Full Day", nullable=False)
    # Expected office window for this date (IST wall-clock), after applying any
    # approved leave: e.g. 1:00 PM login for an approved Morning Half leave.
    expected_login_time: Mapped[Optional[time]] = mapped_column(Time)
    expected_logout_time: Mapped[Optional[time]] = mapped_column(Time)
    # Approved leave period that applied when the session started (snapshot).
    leave_period: Mapped[Optional[str]] = mapped_column(String(20))
    late_login_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    late_login_reason: Mapped[Optional[str]] = mapped_column(String(500))
    early_logout_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    early_logout_reason: Mapped[Optional[str]] = mapped_column(String(500))
    extra_work_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    work_duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attendance_status: Mapped[str] = mapped_column(String(30), default="Present", nullable=False)
    logout_reason: Mapped[Optional[str]] = mapped_column(String(500))
    ip_address: Mapped[Optional[str]] = mapped_column(String(60))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="work_sessions")  # noqa: F821
