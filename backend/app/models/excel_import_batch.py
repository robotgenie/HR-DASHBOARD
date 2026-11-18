from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.models.mixins import JSONType, TimestampMixin


class ExcelImportBatch(Base, TimestampMixin):
    """One Excel employee import between "preview" and "confirm".

    The uploaded workbook itself is never stored. Only the validated, normalised
    rows needed to apply the import are kept, and they are cleared once the batch
    is confirmed or discarded. The audit log receives counts only.
    """

    __tablename__ = "excel_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")  # auto | create | update
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Previewed", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Normalised rows + per-row errors / diffs. Cleared after confirm.
    payload: Mapped[Optional[dict]] = mapped_column(JSONType)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_by: Mapped[Optional["User"]] = relationship()  # noqa: F821
