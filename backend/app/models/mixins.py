"""Shared column mixins and cross-dialect type helpers."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# JSONB on PostgreSQL (the deployment target), plain JSON on SQLite (test runs).
JSONType = JSONB().with_variant(JSON(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
    )
