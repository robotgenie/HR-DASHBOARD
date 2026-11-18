"""Hourly work updates (10-11 ... 5-6), linked to assigned tasks.

Additional to the Noon and EOD reports. Eligibility comes from the same
approved-leave logic as the daily reports (attendance_service), plus the
employee's check-in/check-out times.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.constants import (
    HOURLY_SLOTS, AuditAction, NotificationType, RoleName, TaskStatus,
)
from app.core.dependencies import ApiRuleError
from app.models.employee import Employee
from app.models.hourly_update import HourlyUpdate
from app.models.notification import Notification
from app.models.user import User
from app.models.work_task import WorkTask
from app.services import (
    attendance_service, audit_service, notification_service, report_service, task_service,
)
from app.utils.clock import local_now, to_local
from app.utils.timeutil import utcnow

TASK_STATUSES = (TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED)


def query(db: Session):
    return db.query(HourlyUpdate).options(
        joinedload(HourlyUpdate.attachments),
        joinedload(HourlyUpdate.task).joinedload(WorkTask.assigned_by).joinedload(User.employee),
        joinedload(HourlyUpdate.employee).joinedload(Employee.department),
    )


def output(u: HourlyUpdate) -> dict:
    task = u.task
    e = u.employee
    submitted = to_local(u.submitted_at)
    return {
        "id": u.id,
        "employee_id": u.employee_id,
        "employee_name": e.full_name if e else None,
        "employee_code": e.display_employee_id if e else None,
        "department": e.department.name if e and e.department else None,
        "task_id": u.task_id,
        "task_title": task.title if task else None,
        "task_target": task.target if task else None,
        "task_unit": task.unit if task else None,
        "task_completed": task.completed if task else None,
        "task_remaining": task_service.remaining(task) if task else None,
        "task_progress": task_service.progress(task) if task else None,
        "assigned_by": task_service.assigner_name(task) if task else None,
        "update_date": u.update_date,
        "slot_index": u.slot_index,
        "slot_label": attendance_service.slot_label(u.slot_start.hour, u.slot_end.hour),
        "work_completed": u.work_completed,
        "description": u.description,
        "units_completed": u.units_completed,
        "progress_percent": u.progress_percent,
        "task_status": u.task_status,
        "remaining_work": u.remaining_work,
        "notes": u.notes,
        "submitted_at": submitted.isoformat() if submitted else None,
        "attachments": [
            {"id": a.id, "original_filename": a.original_filename, "mime_type": a.mime_type,
             "file_size": a.file_size}
            for a in u.attachments
        ],
    }


def _notify_due(db: Session, employee: Employee, day, slots) -> None:
    """One in-app notification per due period (dedupe key), never repeated."""
    for s in slots:
        if s["status"] != "Due":
            continue
        notification_service.create(
            db, user_id=employee.user_id,
            title=f"Hourly update due: {s['label']}",
            message=f"Please submit your work update for {s['label']}.",
            type_=NotificationType.HOURLY_UPDATE_DUE, related_entity="hourly_slot",
            related_id=s["slot_index"],
            dedupe_key=f"hourly:{employee.id}:{day.isoformat()}:{s['slot_index']}",
        )


def today_state(db: Session, employee: Employee, notify: bool = True) -> dict:
    now = local_now()
    today = now.date()
    session = attendance_service.today_session(db, employee.user_id, today)
    slots = attendance_service.hourly_slots(db, employee, session, today, now)
    if notify and session is not None and session.logout_at is None:
        _notify_due(db, employee, today, slots)
    tasks = task_service.active_for(db, employee.id, today)
    updates = (
        query(db).filter(HourlyUpdate.employee_id == employee.id, HourlyUpdate.update_date == today)
        .order_by(HourlyUpdate.slot_index).all()
    )
    current = next((s for s in slots if s["status"] == "Open"), None)
    applicable = [s for s in slots if s["status"] != "Not Applicable"]
    return {
        "date": today,
        "now": now.strftime("%H:%M"),
        "checked_in": session is not None,
        "checked_out": bool(session is not None and session.logout_at is not None),
        "working_hours": "10:00 - 18:00",
        "hourly_active": session is not None and session.logout_at is None and now.time() < attendance_service.OFFICE_END,
        "current_slot": current,
        "due_slots": [s for s in slots if s["status"] == "Due"],
        "submitted_count": sum(1 for s in slots if s["status"] == "Submitted"),
        "applicable_count": len(applicable),
        "slots": slots,
        "tasks": [task_service.output(t) for t in tasks],
        "updates": [output(u) for u in updates],
    }


def submit(db: Session, user: User, employee: Employee, data: dict) -> HourlyUpdate:
    if user.role_name == RoleName.ADMIN:
        raise ApiRuleError(403, "The Admin does not submit hourly updates.", "NOT_ALLOWED")
    now = local_now()
    today = now.date()
    session = attendance_service.today_session(db, user.id, today)
    if session is None:
        raise ApiRuleError(409, "Check in first - hourly updates start after Check-In.", "NOT_CHECKED_IN")
    if session.logout_at is not None:
        raise ApiRuleError(409, "You have checked out for today, so hourly updates are closed.", "CHECKED_OUT")

    try:
        index = int(data.get("slot_index"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Choose the hour this update is for.")
    if not 0 <= index < len(HOURLY_SLOTS):
        raise HTTPException(status_code=422, detail="Choose a valid hour between 10:00 AM and 6:00 PM.")
    slots = attendance_service.hourly_slots(db, employee, session, today, now)
    slot = slots[index]
    if slot["status"] == "Submitted":
        raise ApiRuleError(409, f"The {slot['label']} update is already submitted.", "ALREADY_SUBMITTED")
    if not slot["can_submit"]:
        why = slot["reason"] or {
            "Upcoming": "This hour hasn't started yet.",
            "Missed": "This hour can no longer be updated.",
            "Not Checked In": "Check in first.",
        }.get(slot["status"], "This hour is not open for updates.")
        raise ApiRuleError(409, f"Hourly update for {slot['label']} is not applicable: {why}.".replace("..", "."),
                           "SLOT_NOT_APPLICABLE", {"slot": slot})

    work = (data.get("work_completed") or "").strip()
    if len(work) < 3:
        raise HTTPException(status_code=422, detail="Describe the work completed during this hour.")
    task_status = data.get("task_status") or TaskStatus.IN_PROGRESS
    if task_status not in TASK_STATUSES:
        raise HTTPException(status_code=422, detail="Task status must be In Progress or Completed.")
    units = int(data.get("units_completed") or 0)
    percent = data.get("progress_percent")
    percent = None if percent in (None, "") else int(percent)
    if units < 0 or (percent is not None and not 0 <= percent <= 100):
        raise HTTPException(status_code=422, detail="Progress values must be positive (percent 0-100).")

    active = task_service.active_for(db, employee.id, today)
    open_ids = {t.id for t in active if t.status in TaskStatus.OPEN}
    task = None
    task_id = data.get("task_id")
    if task_id:
        task = db.query(WorkTask).filter(WorkTask.id == int(task_id)).first()
        if task is None or task.employee_id != employee.id:
            raise HTTPException(status_code=404, detail="Task not found.")
        if task.id not in open_ids:
            raise HTTPException(status_code=409, detail="That task is not open for updates.")
    elif open_ids:
        raise HTTPException(status_code=422, detail="Choose the assigned task this update belongs to.")

    start, end = HOURLY_SLOTS[index]
    from datetime import time
    row = HourlyUpdate(
        employee_id=employee.id, task_id=task.id if task else None, work_session_id=session.id,
        update_date=today, slot_index=index, slot_start=time(start), slot_end=time(end),
        work_completed=work, description=(data.get("description") or "").strip() or None,
        units_completed=units if task and task.target else 0,
        progress_percent=percent if percent is not None else 0,
        task_status=task_status, remaining_work=(data.get("remaining_work") or "").strip() or None,
        notes=(data.get("notes") or "").strip() or None, submitted_at=utcnow(),
    )
    db.add(row)
    db.flush()
    if task is not None:
        task_service.apply_update(task, units, percent, task_status)
        row.progress_percent = task_service.progress(task)
    # The due-hour notification is done with once the update is in.
    db.query(Notification).filter(
        Notification.dedupe_key == f"hourly:{employee.id}:{today.isoformat()}:{index}",
        Notification.is_read.is_(False),
    ).update({"is_read": True, "read_at": utcnow()}, synchronize_session=False)
    audit_service.record(
        db, AuditAction.HOURLY_UPDATE_SUBMITTED, user=user, entity_type="hourly_update",
        entity_id=row.id, meta={"slot": slot["label"], "task_id": row.task_id},
    )
    report_service.satisfy_noon_from_hourly(db, employee, user, now)
    return row
