"""Single source of "now" for attendance, leave and report rules.

Every office-hour rule (late login, Noon/EOD windows, extra hours) is defined in
India Standard Time. Reading the clock through this module keeps those rules in
one time zone and lets the automated tests pin the time to a specific moment
(`set_fixed_now`) so scenarios such as "10:20 AM login" are reproducible.
"""
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_fixed_now: Optional[datetime] = None


def set_fixed_now(value: Optional[datetime]) -> None:
    """Pin the clock (tests only). Naive values are treated as IST wall time."""
    global _fixed_now
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    _fixed_now = value


def local_now() -> datetime:
    """Current time as an aware IST datetime."""
    if _fixed_now is not None:
        return _fixed_now.astimezone(IST)
    return datetime.now(timezone.utc).astimezone(IST)


def local_today() -> date:
    return local_now().date()


def utc_naive_now() -> datetime:
    """Current UTC time as a naive datetime (the storage convention of this schema)."""
    return local_now().astimezone(timezone.utc).replace(tzinfo=None)


def to_local(value: Optional[datetime]) -> Optional[datetime]:
    """Stored naive-UTC timestamp -> aware IST datetime."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(IST)


def local_combine(day: date, t) -> datetime:
    """IST wall-clock datetime for a date + time."""
    return datetime.combine(day, t).replace(tzinfo=IST)
