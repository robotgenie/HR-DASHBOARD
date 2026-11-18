from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.timeutil import utcnow


class DocumentVersion(Base):
    """Immutable upload history. Old versions are never overwritten or removed."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("employee_document_id", "version_no", name="uq_document_version_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_document_id: Mapped[int] = mapped_column(
        ForeignKey("employee_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    hr_remarks: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow
    )

    document: Mapped["EmployeeDocument"] = relationship(back_populates="versions")  # noqa: F821
