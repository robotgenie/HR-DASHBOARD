from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.common import ORMModel


class NotificationOut(ORMModel):
    id: int
    title: str
    message: str
    type: str
    related_entity: Optional[str] = None
    related_id: Optional[int] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationList(BaseModel):
    items: List[NotificationOut]
    unread_count: int
    total: int


class AuditLogOut(ORMModel):
    id: int
    actor_email: Optional[str] = None
    role_name: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    meta: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime


class EmailLogOut(ORMModel):
    id: int
    to_email: str
    subject: str
    template: str
    status: str
    error: Optional[str] = None
    attachment_name: Optional[str] = None
    related_entity: Optional[str] = None
    related_id: Optional[int] = None
    created_at: datetime


class SettingsUpdate(BaseModel):
    values: dict
