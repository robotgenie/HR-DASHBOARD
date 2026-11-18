from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.timeutil import utcnow
from app.models.mixins import TimestampMixin


class HourlyUpdate(Base, TimestampMixin):
    """One hourly work update (10-11, 11-12 ... 5-6) linked to an assigned task.

    Additional to the Noon / EOD daily reports, never a replacement for them.
    """

    __tablename__ = "hourly_updates"
    __table_args__ = (
        UniqueConstraint("employee_id", "update_date", "slot_index", name="uq_hourly_update_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("work_tasks.id", ondelete="SET NULL"), index=True
    )
    work_session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("work_sessions.id", ondelete="SET NULL")
    )
    update_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_start: Mapped[time] = mapped_column(Time, nullable=False)
    slot_end: Mapped[time] = mapped_column(Time, nullable=False)
    work_completed: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    units_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_status: Mapped[str] = mapped_column(String(20), nullable=False, default="In Progress")
    remaining_work: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    employee: Mapped["Employee"] = relationship()  # noqa: F821
    task: Mapped[Optional["WorkTask"]] = relationship(back_populates="hourly_updates")  # noqa: F821
    attachments: Mapped[List["HourlyUpdateAttachment"]] = relationship(
        back_populates="update", cascade="all, delete-orphan"
    )


class HourlyUpdateAttachment(Base):
    __tablename__ = "hourly_update_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    hourly_update_id: Mapped[int] = mapped_column(
        ForeignKey("hourly_updates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), default=utcnow)

    update: Mapped["HourlyUpdate"] = relationship(back_populates="attachments")
