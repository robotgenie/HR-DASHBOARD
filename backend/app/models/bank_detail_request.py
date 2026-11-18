from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import TimestampMixin


class BankDetailRequest(Base, TimestampMixin):
    """One bank-details submission by an employee, waiting for HR/Admin review.

    The employee's approved details live on the employees table
    (bank_name, bank_account_no, ifsc_code, pan_number). A submission only
    replaces them when it is approved, so salary slips never use unapproved
    data. Every submission is kept as history.
    """

    __tablename__ = "bank_detail_requests"
    __table_args__ = (
        Index("ix_bank_detail_requests_employee_status", "employee_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bank_name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_number: Mapped[str] = mapped_column(String(34), nullable=False)
    ifsc_code: Mapped[str] = mapped_column(String(11), nullable=False)
    pan_number: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    submitted_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    review_remarks: Mapped[Optional[str]] = mapped_column(Text)

    employee: Mapped["Employee"] = relationship(back_populates="bank_detail_requests")  # noqa: F821
    reviewed_by: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewed_by_id])  # noqa: F821
