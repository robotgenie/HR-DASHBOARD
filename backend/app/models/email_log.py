from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.utils.timeutil import utcnow


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    body_preview: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text)
    attachment_name: Mapped[Optional[str]] = mapped_column(String(255))
    related_entity: Mapped[Optional[str]] = mapped_column(String(60))
    related_id: Mapped[Optional[int]] = mapped_column(Integer)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(180), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow, index=True
    )
