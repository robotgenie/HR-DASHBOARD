"""Reporting hierarchy: view the tree, see your own line and team, and (Admin /
HR) change who reports to whom. All rules live in hierarchy_service."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.serializers import employee_list_item, redact_for_viewer
from app.core.constants import RoleName
from app.core.dependencies import (
    assert_can_access_employee, get_current_employee, get_current_user, require_hr,
    require_supervisor,
)
from app.database.database import get_db
from app.models.employee import Employee
from app.models.user import User
from app.services import hierarchy_service as H

router = APIRouter(prefix="/hierarchy", tags=["Hierarchy"])


class AssignmentIn(BaseModel):
    """Only the fields that are present are changed (null clears a line)."""
    role: Optional[str] = None
    reporting_hr_id: Optional[int] = None
    reporting_manager_id: Optional[int] = None


def _person(db: Session, viewer: User, e: Employee) -> dict:
    return redact_for_viewer(db, viewer, e, employee_list_item(db, e, with_docs=False))


@router.get("/tree")
def hierarchy_tree(db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    """Admin: HR -> Managers -> Employees/Interns for the whole organisation.
    HR: their own branch. Manager: their own team."""
    return {"items": H.hierarchy_tree(db, current_user)}


@router.get("/me")
def my_line(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The signed-in person's reporting line and direct reports."""
    me = current_user.employee
    if me is None:
        return {"role": current_user.role_name, "chain": [{"level": "Admin", "name": current_user.display_name}],
                "reporting_manager": None, "reporting_hr": None, "direct_reports": []}
    hr = H.get_reporting_hr(me)
    return {
        "role": current_user.role_name,
        "type": H.person_type(me),
        "chain": H.reporting_chain(me),
        "reporting_manager": _person(db, current_user, me.reporting_manager) if me.reporting_manager else None,
        "reporting_hr": (
            {"id": hr.id, "full_name": hr.full_name, "designation": hr.designation}
            if hr is not None and hr.id != me.id else None
        ),
        "direct_reports": [_person(db, current_user, e) for e in H.get_direct_reports(db, me)],
    }


@router.get("/team")
def my_team(db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    """Everyone the signed-in supervisor may monitor (never themselves)."""
    people = H.get_subordinates(db, current_user, include_self=False)
    return {"items": [_person(db, current_user, e) for e in people]}


@router.get("/candidates")
def candidates(role: str = Query(..., description="HR_ADMIN or MANAGER"),
               db: Session = Depends(get_db), current_user: User = Depends(require_hr)):
    """People who can be picked as a Reporting HR / Reporting Manager."""
    if role not in (RoleName.HR_ADMIN, RoleName.MANAGER):
        raise HTTPException(status_code=422, detail="role must be HR_ADMIN or MANAGER.")
    return {"items": [
        {
            "id": e.id, "full_name": e.full_name, "designation": e.designation,
            "department": e.department.name if e.department else None,
            "department_id": e.department_id,
            "reporting_hr_id": e.reporting_hr_id,
            "reporting_hr": e.reporting_hr.full_name if e.reporting_hr else None,
            "employee_code": e.display_employee_id,
        }
        for e in H.candidates(db, current_user, role)
    ]}


@router.get("/employees/{employee_id}")
def employee_line(employee_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(require_supervisor)):
    employee = assert_can_access_employee(current_user, employee_id, db)
    return {
        "employee": _person(db, current_user, employee),
        "chain": H.reporting_chain(employee),
        "direct_reports": [_person(db, current_user, e) for e in H.get_direct_reports(db, employee)],
    }


@router.put("/employees/{employee_id}")
def update_line(employee_id: int, payload: AssignmentIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_hr)):
    """Change role and/or reporting line.

    Admin: anyone, any role (HR / Manager / Employee). HR: people in their own
    hierarchy, Manager / Employee roles only, placed under themselves.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    fields = payload.model_fields_set
    role = payload.role if "role" in fields and payload.role else None
    hr_id = payload.reporting_hr_id if "reporting_hr_id" in fields else H.UNSET
    mgr_id = payload.reporting_manager_id if "reporting_manager_id" in fields else H.UNSET
    H.authorize_assignment(db, current_user, employee, role=role,
                           reporting_hr_id=hr_id, reporting_manager_id=mgr_id)
    changes = H.apply_assignment(
        db, current_user, employee, role=role if role else H.UNSET,
        reporting_hr_id=hr_id, reporting_manager_id=mgr_id,
    )
    db.commit()
    db.refresh(employee)
    return {
        "changes": changes,
        "employee": _person(db, current_user, employee),
        "chain": H.reporting_chain(employee),
    }
