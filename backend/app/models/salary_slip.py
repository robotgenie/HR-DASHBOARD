from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.timeutil import utcnow


class SalarySlip(Base):
    __tablename__ = "salary_slips"

    id: Mapped[int] = mapped_column(primary_key=True)
    salary_record_id: Mapped[int] = mapped_column(
        ForeignKey("salary_records.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="application/pdf", nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow
    )

    salary_record: Mapped["SalaryRecord"] = relationship(back_populates="slip")  # noqa: F821
