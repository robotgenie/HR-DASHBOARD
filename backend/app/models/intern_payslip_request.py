from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DownloadRequestStatus
from app.database.database import Base
from app.models.mixins import TimestampMixin


class InternPayslipDownloadRequest(Base, TimestampMixin):
    """An intern's request to download one specific payslip.

    Interns may always view a payslip. Downloading needs HR approval, and this
    is the record of the ask: the reason the intern gave, HR's decision, who
    made it and when.

    It does not replace `SalaryRecord.intern_download_allowed` -- that column is
    still the single source of truth for whether a download is permitted.
    Approving a request sets it; rejecting leaves it alone.
    """

    __tablename__ = "intern_payslip_download_requests"
    __table_args__ = (
        Index("ix_ipdr_employee_status", "employee_id", "status"),
        Index("ix_ipdr_salary_status", "salary_id", "status"),
        Index("ix_ipdr_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    salary_id: Mapped[int] = mapped_column(
        ForeignKey("salary_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=DownloadRequestStatus.PENDING, nullable=False, index=True
    )
    hr_remarks: Mapped[Optional[str]] = mapped_column(Text)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    hr_reviewer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    employee: Mapped["Employee"] = relationship(  # noqa: F821
        back_populates="payslip_download_requests"
    )
    salary: Mapped["SalaryRecord"] = relationship(  # noqa: F821
        back_populates="download_requests"
    )
    hr_reviewer: Mapped[Optional["User"]] = relationship(  # noqa: F821
        foreign_keys=[hr_reviewer_id]
    )
