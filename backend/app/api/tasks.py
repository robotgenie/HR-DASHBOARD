"""Task assignment down the hierarchy (see task_service). Everyone sees their
own tasks; supervisors see the tasks of the people they supervise."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, is_hr, require_hr, require_supervisor
from app.database.database import get_db
from app.models.employee import Employee
from app.models.user import User
from app.models.work_task import WorkTask
from app.services import hierarchy_service, task_service
from app.utils.clock import local_today

router = APIRouter(prefix="/tasks", tags=["Tasks"])


class TaskCreate(BaseModel):
    employee_ids: List[int] = Field(..., min_length=1)
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    task_date: Optional[date] = None
    due_date: Optional[date] = None
    target: Optional[int] = Field(None, ge=1, le=100000)
    unit: Optional[str] = Field(None, max_length=40)


class TaskPart(BaseModel):
    employee_id: int
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    task_date: Optional[date] = None
    due_date: Optional[date] = None
    target: Optional[int] = Field(None, ge=1, le=100000)
    unit: Optional[str] = Field(None, max_length=40)


class TaskDivide(BaseModel):
    parts: List[TaskPart] = Field(..., min_length=1, max_length=50)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    task_date: Optional[date] = None
    due_date: Optional[date] = None
    target: Optional[int] = Field(None, ge=1, le=100000)
    unit: Optional[str] = Field(None, max_length=40)
    status: Optional[str] = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tasks(payload: TaskCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(require_supervisor)):
    rows = task_service.create(
        db, current_user, payload.employee_ids, payload.title, payload.description,
        payload.task_date, payload.due_date, payload.target, payload.unit,
    )
    db.commit()
    ids = [r.id for r in rows]
    return {"items": [task_service.output(t) for t in task_service.query(db).filter(WorkTask.id.in_(ids))]}


@router.get("")
def list_tasks(
    employee_id: Optional[int] = None, status_filter: Optional[str] = Query(None, alias="status"),
    day: Optional[date] = Query(None, alias="date"), active: bool = False,
    department_id: Optional[int] = None, reporting_hr_id: Optional[int] = None,
    reporting_manager_id: Optional[int] = None, assigned_by_me: bool = False,
    mine: bool = False, parent_task_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Hierarchy-scoped: Admin all, HR their hierarchy, Manager their team
    (+ own), employees/interns only their own tasks."""
    me = current_user.employee
    if mine or not hierarchy_service.is_supervisor(current_user):
        if me is None:
            raise HTTPException(status_code=404, detail="No employee profile on this account.")
        employee_id = me.id
    elif employee_id:
        hierarchy_service.assert_employee(db, current_user, employee_id, hierarchy_service.VIEW, "work_task")
    if active and employee_id:
        rows = task_service.active_for(db, employee_id, day or local_today())
        return {"items": [task_service.output(t) for t in rows]}
    query = task_service.query(db).join(Employee, WorkTask.employee_id == Employee.id)
    if assigned_by_me:
        query = query.filter(WorkTask.assigned_by_id == current_user.id)
    else:
        query = hierarchy_service.restrict(query, db, current_user, WorkTask.employee_id)
    if employee_id:
        query = query.filter(WorkTask.employee_id == employee_id)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if reporting_hr_id:
        query = query.filter(Employee.reporting_hr_id == reporting_hr_id)
    if reporting_manager_id:
        query = query.filter(Employee.reporting_manager_id == reporting_manager_id)
    if parent_task_id:
        query = query.filter(WorkTask.parent_task_id == parent_task_id)
    if status_filter and status_filter.lower() != "all":
        query = query.filter(WorkTask.status == status_filter)
    if day:
        query = query.filter(WorkTask.task_date <= day)
    rows = query.order_by(WorkTask.task_date.desc(), WorkTask.id.desc()).limit(limit).all()
    return {"items": [task_service.output(t) for t in rows]}


def _load(db: Session, task_id: int, user: User) -> WorkTask:
    task = task_service.query(db).filter(WorkTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if not hierarchy_service.can_access_task(db, user, task):
        raise HTTPException(status_code=403, detail="You don't have access to this resource.")
    return task


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.services import hourly_service
    task = _load(db, task_id, current_user)
    return {**task_service.output(task),
            "hourly_updates": [hourly_service.output(u) for u in task.hourly_updates]}


@router.post("/{task_id}/divide", status_code=status.HTTP_201_CREATED)
def divide_task(task_id: int, payload: TaskDivide, db: Session = Depends(get_db),
                current_user: User = Depends(require_supervisor)):
    """Manager (or HR) splits a task assigned to them among their own team."""
    parent = _load(db, task_id, current_user)
    rows = task_service.divide(db, current_user, parent, [p.model_dump() for p in payload.parts])
    db.commit()
    ids = [r.id for r in rows]
    return {"parent": task_service.output(_load(db, task_id, current_user)),
            "items": [task_service.output(t) for t in task_service.query(db).filter(WorkTask.id.in_(ids))]}


@router.patch("/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(require_supervisor)):
    task = _load(db, task_id, current_user)
    if not hierarchy_service.can_edit_task(db, current_user, task):
        raise HTTPException(status_code=403, detail="Only the assigner or a supervisor can edit this task.")
    task_service.update(db, task, current_user, payload.model_dump(exclude_unset=True))
    db.commit()
    return task_service.output(_load(db, task_id, current_user))
