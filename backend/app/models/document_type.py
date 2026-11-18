from typing import List

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import TimestampMixin


class DocumentType(Base, TimestampMixin):
    """Configurable checklist of documents an employee must provide."""

    __tablename__ = "document_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allowed_extensions: Mapped[str] = mapped_column(
        String(160), default="pdf,png,jpg,jpeg", nullable=False
    )
    max_size_mb: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    documents: Mapped[List["EmployeeDocument"]] = relationship(  # noqa: F821
        back_populates="document_type"
    )

    @property
    def extension_set(self) -> set:
        return {e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()}
