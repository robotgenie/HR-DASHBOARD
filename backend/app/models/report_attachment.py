from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.timeutil import utcnow


class ReportAttachment(Base):
    __tablename__ = "report_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    daily_report_id: Mapped[int] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow
    )

    report: Mapped["DailyReport"] = relationship(back_populates="attachments")  # noqa: F821
