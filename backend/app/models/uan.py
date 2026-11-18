from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import UanStatus
from app.database.database import Base
from app.models.mixins import TimestampMixin


class UanDetail(Base, TimestampMixin):
    __tablename__ = "uan_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    uan_number: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(
        String(30), default=UanStatus.NOT_SUBMITTED, nullable=False, index=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    hr_remarks: Mapped[Optional[str]] = mapped_column(Text)
    verified_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    employee: Mapped["Employee"] = relationship(back_populates="uan")  # noqa: F821
