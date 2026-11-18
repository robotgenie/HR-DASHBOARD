from datetime import date, time
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import MeetingStatus
from app.database.database import Base
from app.models.mixins import TimestampMixin


class Meeting(Base, TimestampMixin):
    """Meetings belong to exactly one department; visibility follows that link."""

    __tablename__ = "meetings"
    __table_args__ = (Index("ix_meetings_dept_date", "department_id", "meeting_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[Optional[time]] = mapped_column(Time)
    agenda: Mapped[Optional[str]] = mapped_column(Text)
    google_meet_url: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(20), default=MeetingStatus.SCHEDULED, nullable=False, index=True
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    department: Mapped["Department"] = relationship(back_populates="meetings")  # noqa: F821
