"""Timestamp helper.

`datetime.utcnow()` is deprecated from Python 3.12 onward, but every timestamp
column in this schema is `TIMESTAMP WITHOUT TIME ZONE`, so handing SQLAlchemy a
timezone-aware value would make stored and freshly-computed datetimes
incomparable. `utcnow()` therefore returns the current UTC time as a *naive*
datetime: the same value `datetime.utcnow()` produced, without the warning.
"""
from datetime import datetime, timezone

__all__ = ["utcnow"]


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (no tzinfo).

    Read through app.utils.clock so attendance timestamps and the office-hour
    rules always agree (and tests can pin the time).
    """
    from app.utils.clock import utc_naive_now
    return utc_naive_now()
