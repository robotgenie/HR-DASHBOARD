from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import TimestampMixin


class WorkTask(Base, TimestampMixin):
    """A task HR/Admin assigns to one employee or intern.

    Progress is either numeric (target / completed, e.g. "Hire 5 employees",
    2 done, 3 remaining) or a percentage when no numeric target is set. Hourly
    updates move the progress forward.
    """

    __tablename__ = "work_tasks"
    __table_args__ = (
        Index("ix_work_tasks_employee_status", "employee_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    task_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    target: Mapped[Optional[int]] = mapped_column(Integer)
    unit: Mapped[Optional[str]] = mapped_column(String(40))
    completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Pending", nullable=False, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Set when a Manager divides a task assigned to them among their team.
    parent_task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("work_tasks.id", ondelete="SET NULL"), index=True
    )

    employee: Mapped["Employee"] = relationship()  # noqa: F821
    parent_task: Mapped[Optional["WorkTask"]] = relationship(
        remote_side=[id], backref="subtasks"
    )
    assigned_by: Mapped[Optional["User"]] = relationship()  # noqa: F821
    hourly_updates: Mapped[List["HourlyUpdate"]] = relationship(  # noqa: F821
        back_populates="task", order_by="HourlyUpdate.update_date, HourlyUpdate.slot_index"
    )
