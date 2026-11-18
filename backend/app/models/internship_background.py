from typing import List

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import TimestampMixin


class InternshipBackground(Base, TimestampMixin):
    """Interns come from many fields, so backgrounds are data, not a fixed list."""

    __tablename__ = "internship_backgrounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    employees: Mapped[List["Employee"]] = relationship(  # noqa: F821
        back_populates="internship_background"
    )
