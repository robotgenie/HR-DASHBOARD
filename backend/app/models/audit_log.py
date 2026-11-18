from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.timeutil import utcnow
from app.models.mixins import JSONType


class AuditLog(Base):
    """Append-only trail. No API exposes update or delete for this table."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_email: Mapped[Optional[str]] = mapped_column(String(255))
    role_name: Mapped[Optional[str]] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    meta: Mapped[Optional[dict]] = mapped_column(JSONType)
    ip_address: Mapped[Optional[str]] = mapped_column(String(60))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow, index=True
    )

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")  # noqa: F821
