"""Department meetings and Google Meet link validation."""
import re
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.employee import Employee
from app.models.meeting import Meeting

# Accepts meet.google.com/abc-defg-hij and Google Calendar/Hangouts style links.
MEET_PATTERNS = (
    re.compile(r"^https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}(\?.*)?$", re.I),
    re.compile(r"^https://meet\.google\.com/[A-Za-z0-9_-]{6,40}(\?.*)?$"),
)


def validate_meet_url(url: Optional[str]) -> Optional[str]:
    """Reject anything that isn't a real Google Meet URL. Links are never invented."""
    if url is None or not url.strip():
        return None
    value = url.strip()
    if not any(pattern.match(value) for pattern in MEET_PATTERNS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Enter a Google Meet link like https://meet.google.com/abc-defg-hij",
        )
    return value


def visible_to_employee(db: Session, employee: Employee, **filters) -> List[Meeting]:
    """An employee only ever sees meetings for their own department."""
    query = (
        db.query(Meeting)
        .options(joinedload(Meeting.department))
        .filter(Meeting.department_id == employee.department_id)
    )
    if filters.get("date_from"):
        query = query.filter(Meeting.meeting_date >= filters["date_from"])
    if filters.get("date_to"):
        query = query.filter(Meeting.meeting_date <= filters["date_to"])
    if filters.get("status"):
        query = query.filter(Meeting.status == filters["status"])
    return query.order_by(Meeting.meeting_date.desc(), Meeting.start_time).all()
