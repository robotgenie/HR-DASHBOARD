from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ProfileChangeStatus
from app.database.database import Base
from app.models.mixins import TimestampMixin


class ProfileChangeRequest(Base, TimestampMixin):
    """An employee's request to change a locked identity field.

    Locked fields (name, phone, email, date of birth, gender) can only be
    changed by HR approving one of these. The employee's own profile is never
    written directly: approval is what applies `new_value`.
    """

    __tablename__ = "profile_change_requests"
    __table_args__ = (
        Index("ix_pcr_employee_status", "employee_id", "status"),
        Index("ix_pcr_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(60), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=ProfileChangeStatus.PENDING, nullable=False, index=True
    )
    hr_remarks: Mapped[Optional[str]] = mapped_column(Text)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    employee: Mapped["Employee"] = relationship(  # noqa: F821
        back_populates="profile_change_requests"
    )
    reviewed_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        foreign_keys=[reviewed_by_id]
    )
