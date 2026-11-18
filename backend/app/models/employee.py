from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EmploymentStatus
from app.database.database import Base
from app.models.mixins import TimestampMixin


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (
        Index("ix_employees_dept_status", "department_id", "employment_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    employee_code: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )
    # Unique employee id (RGEMP001...). Issued once the profile is complete and
    # never reissued or edited afterwards.
    unique_employee_id: Mapped[Optional[str]] = mapped_column(
        String(20), unique=True, index=True
    )
    employee_id_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Set when the profile is completed: identity fields become HR-controlled
    # from this point on and the employee must raise a change request.
    identity_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    id_card_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    id_card_status: Mapped[str] = mapped_column(String(20), default="Pending", nullable=False, index=True)
    id_card_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    id_card_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    id_card_rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    id_card_approval_remarks: Mapped[Optional[str]] = mapped_column(Text)
    id_card_approved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    gender: Mapped[Optional[str]] = mapped_column(String(20))

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    internship_background_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("internship_backgrounds.id", ondelete="SET NULL"), index=True
    )
    designation: Mapped[str] = mapped_column(String(120), nullable=False)
    # Free-text internship information (college, programme, duration...).
    internship_details: Mapped[Optional[str]] = mapped_column(Text)
    joining_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Reporting hierarchy: ADMIN -> HR -> MANAGER -> EMPLOYEE / INTERN.
    # reporting_manager_id: the Manager an employee/intern reports to.
    # reporting_hr_id: the HR a Manager reports to. For employees/interns it is
    # kept equal to their manager's HR (or set directly when they report to an
    # HR without a manager), so "everyone under HR X" is one indexed lookup.
    # Both are maintained only through app.services.hierarchy_service.
    reporting_manager_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    reporting_hr_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    employment_status: Mapped[str] = mapped_column(
        String(20), default=EmploymentStatus.ACTIVE, nullable=False, index=True
    )

    address: Mapped[Optional[str]] = mapped_column(Text)
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(160))
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(20))
    emergency_contact_relation: Mapped[Optional[str]] = mapped_column(String(60))
    photo_path: Mapped[Optional[str]] = mapped_column(String(255))

    # Payroll details printed on the payslip. Kept on the employee record so the
    # payslip never hard-codes them.
    work_location: Mapped[Optional[str]] = mapped_column(String(120))
    bank_name: Mapped[Optional[str]] = mapped_column(String(120))
    bank_account_no: Mapped[Optional[str]] = mapped_column(String(34))
    pan_number: Mapped[Optional[str]] = mapped_column(String(10))
    # bank_name / bank_account_no / pan_number / ifsc_code hold the employee's
    # APPROVED bank details only. Employees submit changes as BankDetailRequest
    # rows; approval copies them here, so a pending change never replaces the
    # details salary slips are printed with.
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(11))
    bank_details_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # --- relationships ---
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="employee"
    )  # noqa: F821
    id_card_approved_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[id_card_approved_by_id], back_populates="approved_id_cards"
    )  # noqa: F821
    department: Mapped["Department"] = relationship(back_populates="employees")  # noqa: F821
    internship_background: Mapped[Optional["InternshipBackground"]] = relationship(  # noqa: F821
        back_populates="employees"
    )
    reporting_manager: Mapped[Optional["Employee"]] = relationship(
        remote_side=[id], foreign_keys=[reporting_manager_id], backref="direct_reports"
    )
    reporting_hr: Mapped[Optional["Employee"]] = relationship(
        remote_side=[id], foreign_keys=[reporting_hr_id], backref="hr_reports"
    )
    documents: Mapped[List["EmployeeDocument"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    uan: Mapped[Optional["UanDetail"]] = relationship(  # noqa: F821
        back_populates="employee", uselist=False, cascade="all, delete-orphan"
    )
    salary_records: Mapped[List["SalaryRecord"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    daily_reports: Mapped[List["DailyReport"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    payslip_download_requests: Mapped[List["InternPayslipDownloadRequest"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan",
        order_by="InternPayslipDownloadRequest.created_at.desc()",
    )
    profile_change_requests: Mapped[List["ProfileChangeRequest"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan",
        order_by="ProfileChangeRequest.created_at.desc()",
    )
    bank_detail_requests: Mapped[List["BankDetailRequest"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan",
        order_by="BankDetailRequest.created_at.desc()",
    )
    leave_requests: Mapped[List["LeaveRequest"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan",
        order_by="LeaveRequest.created_at.desc()",
    )

    @property
    def email(self) -> str:
        return self.user.email if self.user else ""

    @property
    def is_intern(self) -> bool:
        return bool(self.department and self.department.name == "Internship")

    @property
    def role_name(self) -> str:
        return self.user.role_name if self.user else ""

    @property
    def identity_locked(self) -> bool:
        return self.identity_locked_at is not None

    @property
    def display_employee_id(self) -> str:
        """The unique employee id once issued, else the internal joining code."""
        return self.unique_employee_id or self.employee_code
