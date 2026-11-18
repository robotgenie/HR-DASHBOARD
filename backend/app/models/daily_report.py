from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ReportStatus, ReportType
from app.database.database import Base
from app.models.mixins import TimestampMixin


class DailyReport(Base, TimestampMixin):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("employee_id", "report_date", "report_type", name="uq_daily_report_employee_date_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(10), default=ReportType.EOD, nullable=False, index=True)
    tasks_completed: Mapped[Optional[str]] = mapped_column(Text)
    tasks_in_progress: Mapped[Optional[str]] = mapped_column(Text)
    tasks_pending: Mapped[Optional[str]] = mapped_column(Text)
    work_summary: Mapped[Optional[str]] = mapped_column(Text)
    challenges: Mapped[Optional[str]] = mapped_column(Text)
    additional_comments: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=ReportStatus.DRAFT, nullable=False, index=True
    )
    # "Manual" (filed on the form) or "Hourly Updates" (Noon Report satisfied
    # automatically by an hourly update submitted after 1:00 PM).
    source: Mapped[str] = mapped_column(
        String(30), default="Manual", server_default="Manual", nullable=False
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    review_notes: Mapped[Optional[str]] = mapped_column(Text)

    employee: Mapped["Employee"] = relationship(back_populates="daily_reports")  # noqa: F821
    reviewed_by: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewed_by_id])  # noqa: F821
    attachments: Mapped[List["ReportAttachment"]] = relationship(  # noqa: F821
        back_populates="report", cascade="all, delete-orphan"
    )
