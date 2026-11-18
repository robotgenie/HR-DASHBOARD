from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import AuditAction
from app.core.dependencies import get_current_user, require_hr
from app.database.database import get_db
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.schemas.employee import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services import audit_service

router = APIRouter(prefix="/departments", tags=["Departments"])


def _with_counts(db: Session, departments: List[Department]) -> List[dict]:
    counts = dict(
        db.query(Employee.department_id, func.count(Employee.id))
        .group_by(Employee.department_id)
        .all()
    )
    return [
        {
            "id": d.id, "name": d.name, "code": d.code, "description": d.description,
            "is_active": d.is_active, "employee_count": counts.get(d.id, 0),
        }
        for d in departments
    ]


@router.get("", response_model=List[DepartmentOut])
def list_departments(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Readable by any signed-in user; the employee form needs the list."""
    query = db.query(Department)
    if active_only:
        query = query.filter(Department.is_active.is_(True))
    return _with_counts(db, query.order_by(Department.name).all())


@router.post("", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    exists = (
        db.query(Department)
        .filter(
            (func.lower(Department.name) == payload.name.lower())
            | (func.lower(Department.code) == payload.code.lower())
        )
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with that name or code already exists.",
        )

    department = Department(**payload.model_dump())
    db.add(department)
    db.flush()
    audit_service.record(
        db, AuditAction.DEPARTMENT_CREATED, user=current_user, entity_type="department",
        entity_id=department.id, meta={"name": department.name},
    )
    db.commit()
    return _with_counts(db, [department])[0]


@router.put("/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    department = db.query(Department).filter(Department.id == department_id).first()
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found.")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(department, field, value)
    db.flush()

    audit_service.record(
        db, AuditAction.DEPARTMENT_UPDATED, user=current_user, entity_type="department",
        entity_id=department.id, meta={"changes": {k: str(v) for k, v in changes.items()}},
    )
    db.commit()
    return _with_counts(db, [department])[0]
