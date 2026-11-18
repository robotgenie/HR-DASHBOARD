from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_logout_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Profile of accounts that have no employee record (the Admin). Employee-
    # side accounts keep their profile on the employees table as before.
    full_name: Mapped[Optional[str]] = mapped_column(String(160))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    title: Mapped[Optional[str]] = mapped_column(String(120))

    role: Mapped["Role"] = relationship(back_populates="users")  # noqa: F821
    employee: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys="Employee.user_id", back_populates="user", uselist=False
    )  # noqa: F821
    approved_id_cards: Mapped[List["Employee"]] = relationship(
        "Employee", foreign_keys="Employee.id_card_approved_by_id", back_populates="id_card_approved_by"
    )  # noqa: F821
    notifications: Mapped[List["Notification"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="user")  # noqa: F821
    reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    work_sessions: Mapped[List["WorkSession"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def role_name(self) -> str:
        return self.role.name if self.role else ""

    @property
    def display_name(self) -> str:
        if self.employee is not None:
            return self.employee.full_name
        return self.full_name or self.email
