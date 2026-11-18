from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import TimestampMixin


class SalaryComponent(Base, TimestampMixin):
    """Free-form earning/deduction lines. Nothing about pay structure is hard-coded."""

    __tablename__ = "salary_components"

    id: Mapped[int] = mapped_column(primary_key=True)
    salary_record_id: Mapped[int] = mapped_column(
        ForeignKey("salary_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_type: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    salary_record: Mapped["SalaryRecord"] = relationship(back_populates="components")  # noqa: F821
