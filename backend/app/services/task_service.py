"""Tasks assigned down the hierarchy.

ADMIN -> HR / Manager / Employee / Intern, HR -> Manager / Employee / Intern
(their hierarchy), Manager -> their own team. A Manager can also divide a task
assigned to them into sub-tasks for team members (parent_task_id).
"""
from datetime import date
from typing import Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import AuditAction, NotificationType, TaskStatus
from app.models.employee import Employee
from app.models.user import User
from app.models.work_task import WorkTask
from app.services import audit_service, hierarchy_service, notification_service
from app.utils.clock import local_today
from app.utils.timeutil import utcnow


def query(db: Session):
    return db.query(WorkTask).options(
        joinedload(WorkTask.employee).joinedload(Employee.department),
        joinedload(WorkTask.assigned_by).joinedload(User.employee),
    )


def assigner_name(task: WorkTask) -> Optional[str]:
    user = task.assigned_by
    if user is None:
        return None
    return user.display_name


def remaining(task: WorkTask) -> Optional[int]:
    return max(0, task.target - task.completed) if task.target else None


def progress(task: WorkTask) -> int:
    if task.status == TaskStatus.COMPLETED:
        return 100
    if task.target:
        return min(100, round(task.completed * 100 / task.target))
    return task.progress_percent or 0


def output(task: WorkTask) -> dict:
    e = task.employee
    return {
        "id": task.id,
        "employee_id": task.employee_id,
        "employee_name": e.full_name if e else None,
        "employee_code": e.display_employee_id if e else None,
        "department": e.department.name if e and e.department else None,
        "is_intern": e.is_intern if e else False,
        "title": task.title,
        "description": task.description,
        "task_date": task.task_date,
        "due_date": task.due_date,
        "target": task.target,
        "unit": task.unit,
        "completed": task.completed,
        "remaining": remaining(task),
        "progress_percent": progress(task),
        "status": task.status,
        "assigned_by": assigner_name(task),
        "assigned_by_id": task.assigned_by_id,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updates_count": len(task.hourly_updates),
        "parent_task_id": task.parent_task_id,
        "parent_task_title": task.parent_task.title if task.parent_task else None,
        "subtasks_count": len(task.subtasks or []),
        "person_type": hierarchy_service.person_type(e) if e else None,
    }


def create(db: Session, actor: User, employee_ids: Iterable[int], title: str,
           description: Optional[str], task_date: Optional[date], due_date: Optional[date],
           target: Optional[int], unit: Optional[str],
           parent_task_id: Optional[int] = None) -> List[WorkTask]:
    title = (title or "").strip()
    if len(title) < 3:
        raise HTTPException(status_code=422, detail="Give the task a title (at least 3 characters).")
    ids = sorted(set(int(i) for i in employee_ids or []))
    if not ids:
        raise HTTPException(status_code=422, detail="Choose at least one employee or intern.")
    task_date = task_date or local_today()
    if due_date and due_date < task_date:
        raise HTTPException(status_code=422, detail="Due date can't be before the task date.")
    if target is not None and target < 1:
        raise HTTPException(status_code=422, detail="Target must be 1 or more (or leave it empty).")
    employees = db.query(Employee).filter(Employee.id.in_(ids)).all()
    if len(employees) != len(ids):
        raise HTTPException(status_code=404, detail="One of the selected employees was not found.")
    rows = []
    for employee in employees:
        if employee.user is None or not employee.user.is_active:
            raise HTTPException(status_code=409, detail=f"{employee.full_name}'s account is inactive.")
        if not hierarchy_service.can_assign_task(db, actor, employee):
            raise HTTPException(
                status_code=403,
                detail=f"You can't assign tasks to {employee.full_name}: they are outside your hierarchy.",
            )
        row = WorkTask(
            employee_id=employee.id, assigned_by_id=actor.id, title=title, parent_task_id=parent_task_id,
            description=(description or "").strip() or None, task_date=task_date,
            due_date=due_date, target=target, unit=(unit or "").strip() or None,
            status=TaskStatus.PENDING,
        )
        db.add(row)
        db.flush()
        rows.append(row)
        audit_service.record(
            db, AuditAction.TASK_ASSIGNED, user=actor, entity_type="work_task", entity_id=row.id,
            meta={"employee_id": employee.id, "title": title, "target": target},
        )
        notification_service.create(
            db, user_id=employee.user_id, title="New task assigned",
            message=f"{title}" + (f" - target {target}{' ' + unit if unit else ''}" if target else "")
            + f" (from {task_date.strftime('%d %b %Y')}).",
            type_=NotificationType.TASK_ASSIGNED, related_entity="work_task", related_id=row.id,
            dedupe_key=f"task:{row.id}:assigned", actor=actor,
        )
    return rows


def update(db: Session, task: WorkTask, actor: User, changes: dict) -> WorkTask:
    """HR edits a task (title, dates, target, status...)."""
    for field in ("title", "description", "task_date", "due_date", "target", "unit"):
        if field in changes:
            value = changes[field]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(task, field, value)
    if not task.title:
        raise HTTPException(status_code=422, detail="Task title can't be empty.")
    if task.target is not None and task.target < 1:
        raise HTTPException(status_code=422, detail="Target must be 1 or more.")
    if "status" in changes:
        if changes["status"] not in TaskStatus.ALL:
            raise HTTPException(status_code=422, detail="Unknown task status.")
        task.status = changes["status"]
        task.completed_at = utcnow() if task.status == TaskStatus.COMPLETED else None
    db.flush()
    audit_service.record(
        db, AuditAction.TASK_UPDATED, user=actor, entity_type="work_task", entity_id=task.id,
        meta={"fields": sorted(changes)},
    )
    return task


def active_for(db: Session, employee_id: int, day: date):
    """Tasks the employee works on today: open tasks already started (and not
    past their due date by more than today), plus ones completed today."""
    return (
        query(db)
        .filter(
            WorkTask.employee_id == employee_id,
            WorkTask.task_date <= day,
            or_(
                WorkTask.status.in_(TaskStatus.OPEN),
                WorkTask.task_date == day,
            ),
            WorkTask.status != TaskStatus.CANCELLED,
        )
        .order_by(WorkTask.status.desc(), WorkTask.task_date, WorkTask.id)
        .all()
    )


def apply_update(task: WorkTask, units: int, percent: Optional[int], status: str) -> None:
    """Move a task forward from an hourly update."""
    if task.target:
        task.completed = min(task.target, max(0, task.completed + max(0, units)))
        task.progress_percent = progress(task)
        if task.completed >= task.target:
            status = TaskStatus.COMPLETED
    elif percent is not None:
        task.progress_percent = max(task.progress_percent or 0, min(100, max(0, percent)))
    if status == TaskStatus.COMPLETED:
        task.status = TaskStatus.COMPLETED
        task.completed_at = task.completed_at or utcnow()
        task.progress_percent = 100
    elif task.status == TaskStatus.PENDING:
        task.status = TaskStatus.IN_PROGRESS


def divide(db: Session, actor: User, parent: WorkTask, parts: List[dict]) -> List[WorkTask]:
    """A Manager splits a task assigned to them among their team members.

    Each part becomes a normal task (same notifications, hourly updates and
    progress rules) linked to the parent with parent_task_id.
    """
    me = actor.employee
    if me is None or parent.employee_id != me.id:
        raise HTTPException(status_code=403, detail="You can only divide tasks assigned to you.")
    if parent.status == TaskStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="A cancelled task can't be divided.")
    if not parts:
        raise HTTPException(status_code=422, detail="Add at least one part.")
    created: List[WorkTask] = []
    for part in parts:
        created.extend(create(
            db, actor, [part["employee_id"]], part.get("title") or parent.title,
            part.get("description") or parent.description, part.get("task_date") or local_today(),
            part.get("due_date") or parent.due_date, part.get("target"), part.get("unit") or parent.unit,
            parent_task_id=parent.id,
        ))
    if parent.status == TaskStatus.PENDING:
        parent.status = TaskStatus.IN_PROGRESS
    db.flush()
    audit_service.record(
        db, AuditAction.TASK_DIVIDED, user=actor, entity_type="work_task", entity_id=parent.id,
        meta={"subtasks": [t.id for t in created], "employees": [t.employee_id for t in created]},
    )
    return created
