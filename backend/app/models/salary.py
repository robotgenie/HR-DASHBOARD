from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import SalaryStatus
from app.database.database import Base
from app.models.mixins import TimestampMixin

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


class SalaryRecord(Base, TimestampMixin):
    __tablename__ = "salary_records"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "period_year", "period_month", name="uq_salary_employee_period"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    working_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Loss of pay days for the period, shown as "LOP" on the payslip.
    lop_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=SalaryStatus.PENDING, nullable=False, index=True
    )
    total_earnings: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    net_pay: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    credit_date: Mapped[Optional[date]] = mapped_column(Date)
    remarks: Mapped[Optional[str]] = mapped_column(Text)

    # Idempotency guards for the salary-credited side effects
    credited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    credited_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    credit_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    credit_email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Interns may always view their payslip but can only download it once HR
    # grants permission on this specific salary record.
    intern_download_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    download_permission_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Set when the record was created by the monthly auto-generation from the
    # employee's previous month (generated_from_id) instead of by hand.
    auto_generated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    generated_from_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("salary_records.id", ondelete="SET NULL")
    )
    download_permission_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    employee: Mapped["Employee"] = relationship(back_populates="salary_records")  # noqa: F821
    components: Mapped[List["SalaryComponent"]] = relationship(  # noqa: F821
        back_populates="salary_record",
        cascade="all, delete-orphan",
        order_by="SalaryComponent.sort_order",
    )
    download_requests: Mapped[List["InternPayslipDownloadRequest"]] = relationship(  # noqa: F821
        back_populates="salary", cascade="all, delete-orphan",
        order_by="InternPayslipDownloadRequest.created_at.desc()",
    )
    slip: Mapped[Optional["SalarySlip"]] = relationship(  # noqa: F821
        back_populates="salary_record", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def period_label(self) -> str:
        return f"{MONTH_NAMES[self.period_month - 1]} {self.period_year}"

    @property
    def earnings(self) -> List["SalaryComponent"]:  # noqa: F821
        return [c for c in self.components if c.component_type == "earning"]

    @property
    def deductions(self) -> List["SalaryComponent"]:  # noqa: F821
        return [c for c in self.components if c.component_type == "deduction"]
