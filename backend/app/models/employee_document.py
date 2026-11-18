from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DocumentStatus
from app.database.database import Base
from app.models.mixins import TimestampMixin


class EmployeeDocument(Base, TimestampMixin):
    """One row per (employee, document type). The file itself lives in versions."""

    __tablename__ = "employee_documents"
    __table_args__ = (
        UniqueConstraint("employee_id", "document_type_id", name="uq_employee_document_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type_id: Mapped[int] = mapped_column(
        ForeignKey("document_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), default=DocumentStatus.PENDING, nullable=False, index=True
    )
    hr_remarks: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    employee: Mapped["Employee"] = relationship(back_populates="documents")  # noqa: F821
    document_type: Mapped["DocumentType"] = relationship(back_populates="documents")  # noqa: F821
    versions: Mapped[List["DocumentVersion"]] = relationship(  # noqa: F821
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_no",
    )
    reviewed_by: Mapped[Optional["User"]] = relationship()  # noqa: F821

    @property
    def current_version(self) -> Optional["DocumentVersion"]:  # noqa: F821
        return self.versions[-1] if self.versions else None

    @property
    def version_count(self) -> int:
        return len(self.versions)
