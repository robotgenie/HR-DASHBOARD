"""SQLAlchemy engine, session factory and declarative base.

PostgreSQL is the target database. The engine is built from DATABASE_URL, which
means the test suite can point at a throwaway database (PostgreSQL or SQLite)
without touching application code.
"""
from typing import Any, Dict, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

_url = settings.DATABASE_URL
_connect_args: Dict[str, Any] = {}
_engine_kwargs: Dict[str, Any] = {"pool_pre_ping": True}

if _url.startswith("sqlite"):
    # Only used by the portable test profile.
    _connect_args = {"check_same_thread": False}
    _engine_kwargs = {}

engine = create_engine(
    _url,
    echo=settings.SQL_ECHO,
    future=True,
    connect_args=_connect_args,
    **_engine_kwargs,
)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
