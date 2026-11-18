from datetime import date, time
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import MeetingStatus


class MeetingBase(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    department_id: int
    meeting_date: date
    start_time: time
    end_time: Optional[time] = None
    agenda: Optional[str] = None
    google_meet_url: Optional[str] = None
    status: str = MeetingStatus.SCHEDULED

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in MeetingStatus.ALL:
            raise ValueError(f"status must be one of {', '.join(MeetingStatus.ALL)}")
        return v


class MeetingCreate(MeetingBase):
    """A scheduled meeting must carry the real Google Meet link HR will use.

    It stays optional on MeetingBase so existing rows and updates are unaffected.
    """
    google_meet_url: str = Field(min_length=10, max_length=255)


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    department_id: Optional[int] = None
    meeting_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    agenda: Optional[str] = None
    google_meet_url: Optional[str] = None
    status: Optional[str] = None


class MeetingOut(BaseModel):
    id: int
    title: str
    department_id: int
    department: str
    meeting_date: date
    start_time: time
    end_time: Optional[time] = None
    agenda: Optional[str] = None
    google_meet_url: Optional[str] = None
    status: str
    is_today: bool = False
