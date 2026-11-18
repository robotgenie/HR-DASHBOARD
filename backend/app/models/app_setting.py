from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base
from app.models.mixins import TimestampMixin


class AppSetting(Base, TimestampMixin):
    """Key/value store behind the HR Settings page (e.g. daily_report_mandatory)."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    value_type: Mapped[str] = mapped_column(String(20), default="string", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
