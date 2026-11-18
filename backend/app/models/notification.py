from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.timeutil import utcnow


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    related_entity: Mapped[Optional[str]] = mapped_column(String(60))
    related_id: Mapped[Optional[int]] = mapped_column(Integer)
    # Prevents the same event producing duplicate notifications (e.g. re-saving a credit).
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(180), unique=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow, index=True
    )

    user: Mapped["User"] = relationship(back_populates="notifications")  # noqa: F821
