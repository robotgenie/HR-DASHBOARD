"""Organisational hierarchy and the single authorization engine.

    ADMIN                 organisation-wide (not an employee: no attendance)
      |
      HR                  the managers assigned to them + those managers' teams
      |
      MANAGER             the employees / interns reporting to them
      |
      EMPLOYEE / INTERN   their own records only

Every router asks this module who may see or act on what. Nothing here trusts
the frontend: the same functions back list filtering (``restrict``), single
record checks (``assert_*``) and the approval flows, so the rules cannot drift
apart between modules.

Access levels used across the API
---------------------------------
* view       - profile, attendance, reports, hourly updates, tasks, leave,
               monthly report, document *status*.          (self, manager, HR, admin)
* sensitive  - salary, payslips, UAN, document files.     (self, HR, admin; never a manager)
* supervise  - review reports, first-level leave approval, assign / divide tasks.
                                                            (manager -> team, HR -> scope, admin)
* manage     - HR-level changes to someone else's record: verify documents,
               salary, UAN, ID approval, final leave approval, edit profile.
                                                            (HR -> scope excluding self, admin)

A person never supervises or manages *themselves*: HR's own leave, documents
and salary are handled by the Admin, a Manager's own leave by their HR.

Unassigned people
-----------------
Employees/managers that have no reporting HR yet (legacy data, or created by
the Admin without a hierarchy) are visible to every HR while the
``hr_sees_unassigned`` setting is on (default), so the existing HR workflow
keeps working until the Admin assigns them. With the setting off, only the
Admin sees them. HR accounts are never part of that pool: one HR never sees
another HR.
"""
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from app.core.constants import (
    INTERNSHIP_DEPARTMENT_NAME, ApprovalStage, AuditAction, LeaveStatus, NotificationType,
    RoleName, SettingKey,
)
from app.models.employee import Employee
from app.models.role import Role
from app.models.user import User

FORBIDDEN = "You don't have access to this resource."

VIEW = "view"
SENSITIVE = "sensitive"
SUPERVISE = "supervise"
MANAGE = "manage"
LEVELS = (VIEW, SENSITIVE, SUPERVISE, MANAGE)

_UNSET = object()


# --------------------------------------------------------------------- roles
def role_of(user: Optional[User]) -> str:
    return user.role_name if user is not None else ""


def is_admin(user: Optional[User]) -> bool:
    return role_of(user) == RoleName.ADMIN


def is_hr(user: Optional[User]) -> bool:
    """The HR role itself (not Admin)."""
    return role_of(user) == RoleName.HR_ADMIN


def is_manager(user: Optional[User]) -> bool:
    return role_of(user) == RoleName.MANAGER


def has_hr_authority(user: Optional[User]) -> bool:
    """HR-level management rights (HR within their scope, Admin everywhere)."""
    return role_of(user) in (RoleName.ADMIN, RoleName.HR_ADMIN)


def is_supervisor(user: Optional[User]) -> bool:
    return role_of(user) in (RoleName.ADMIN, RoleName.HR_ADMIN, RoleName.MANAGER)


def employee_role(employee: Optional[Employee]) -> str:
    return employee.user.role_name if employee is not None and employee.user else ""


def role_label(role: str) -> str:
    return RoleName.LABELS.get(role, role or "")


def person_type(employee: Employee) -> str:
    """HR / Manager / Intern / Employee, as shown on screens and exports."""
    role = employee_role(employee)
    if role == RoleName.HR_ADMIN:
        return "HR"
    if role == RoleName.MANAGER:
        return "Manager"
    return "Intern" if employee.is_intern else "Employee"


def own_employee(user: Optional[User]) -> Optional[Employee]:
    return user.employee if user is not None else None


def _pool_enabled(db: Session) -> bool:
    from app.services import settings_service
    return settings_service.get_bool(db, SettingKey.HR_SEES_UNASSIGNED, True)


# -------------------------------------------------------------- relationships
def get_reporting_manager(employee: Optional[Employee]) -> Optional[Employee]:
    if employee is None:
        return None
    return employee.reporting_manager


def get_reporting_hr(employee: Optional[Employee]) -> Optional[Employee]:
    """The HR an employee ultimately reports to (directly or via the manager)."""
    if employee is None:
        return None
    if employee.reporting_hr is not None:
        return employee.reporting_hr
    manager = employee.reporting_manager
    return manager.reporting_hr if manager is not None else None


def reporting_chain(employee: Employee) -> List[dict]:
    """Employee -> Manager -> HR -> Admin, for display."""
    chain = [{"level": person_type(employee), "employee_id": employee.id, "name": employee.full_name}]
    manager = get_reporting_manager(employee)
    if manager is not None:
        chain.append({"level": "Manager", "employee_id": manager.id, "name": manager.full_name})
    hr = get_reporting_hr(employee)
    if hr is not None and employee_role(employee) != RoleName.HR_ADMIN:
        chain.append({"level": "HR", "employee_id": hr.id, "name": hr.full_name})
    chain.append({"level": "Admin", "employee_id": None, "name": "Admin"})
    return chain


def get_direct_reports(db: Session, employee: Employee) -> List[Employee]:
    role = employee_role(employee)
    if role == RoleName.HR_ADMIN:
        return (
            db.query(Employee).join(User, Employee.user_id == User.id).join(Role, User.role_id == Role.id)
            .filter(Employee.reporting_hr_id == employee.id, Role.name == RoleName.MANAGER)
            .order_by(Employee.full_name).all()
        )
    if role == RoleName.MANAGER:
        return (
            db.query(Employee).filter(Employee.reporting_manager_id == employee.id)
            .order_by(Employee.full_name).all()
        )
    return []


def get_subordinates(db: Session, user: User, include_self: bool = False) -> List[Employee]:
    """Everyone below the user in the hierarchy (the Admin gets everyone)."""
    query = restrict(db.query(Employee), db, user, Employee.id, include_self=include_self)
    return query.order_by(Employee.full_name).all()


def get_team(db: Session, manager: Employee) -> List[Employee]:
    return (
        db.query(Employee).filter(Employee.reporting_manager_id == manager.id)
        .order_by(Employee.full_name).all()
    )


# --------------------------------------------------------------- list scoping
def visible_ids_select(db: Session, user: User, include_self: bool = True):
    """A SELECT of the employee ids the user may *view*, or None for everything."""
    if is_admin(user):
        return None
    me = own_employee(user)
    if me is None:
        return select(Employee.id).where(false())
    role = role_of(user)
    conditions = []
    if include_self:
        conditions.append(Employee.id == me.id)
    if role == RoleName.HR_ADMIN:
        conditions.append(and_(Employee.reporting_hr_id == me.id, Employee.id != me.id))
        mine_mgrs = select(Employee.id).where(Employee.reporting_hr_id == me.id)
        conditions.append(and_(Employee.reporting_hr_id.is_(None), Employee.reporting_manager_id.in_(mine_mgrs)))
        if _pool_enabled(db):
            owned_mgrs = select(Employee.id).where(Employee.reporting_hr_id.isnot(None))
            conditions.append(
                and_(
                    Employee.reporting_hr_id.is_(None),
                    Employee.id != me.id,
                    Role.name.in_((RoleName.MANAGER, RoleName.EMPLOYEE)),
                    or_(Employee.reporting_manager_id.is_(None),
                        Employee.reporting_manager_id.notin_(owned_mgrs)),
                )
            )
    elif role == RoleName.MANAGER:
        conditions.append(and_(Employee.reporting_manager_id == me.id, Employee.id != me.id))
    if not conditions:
        return select(Employee.id).where(false())
    return (
        select(Employee.id)
        .join(User, Employee.user_id == User.id)
        .join(Role, User.role_id == Role.id)
        .where(or_(*conditions))
    )


def restrict(query, db: Session, user: User, column, include_self: bool = True):
    """Filter any query to rows whose employee id (``column``) the user may view."""
    ids = visible_ids_select(db, user, include_self=include_self)
    if ids is None:
        return query
    return query.filter(column.in_(ids))


def restrict_sensitive(query, db: Session, user: User, column, include_self: bool = True):
    """Like restrict(), but a Manager only ever sees their own row (salary, UAN...)."""
    if is_manager(user):
        me = own_employee(user)
        if not include_self or me is None:
            return query.filter(false())
        return query.filter(column == me.id)
    return restrict(query, db, user, column, include_self=include_self)


def restrict_managed(query, db: Session, user: User, column):
    """Rows the user can act on with HR authority (never their own)."""
    if not has_hr_authority(user):
        return query.filter(false())
    return restrict(query, db, user, column, include_self=False)


def visible_employee_ids(db: Session, user: User, include_self: bool = True) -> Optional[set]:
    ids = visible_ids_select(db, user, include_self=include_self)
    if ids is None:
        return None
    return {row[0] for row in db.execute(ids).all()}


def visible_user_ids_select(db: Session, user: User, include_self: bool = True):
    """Same scope expressed as user ids (attendance sessions, audit logs)."""
    ids = visible_ids_select(db, user, include_self=include_self)
    if ids is None:
        return None
    return select(Employee.user_id).where(Employee.id.in_(ids))


# ------------------------------------------------------------ single checks
def _in_hr_scope(db: Session, hr: Employee, employee: Employee) -> bool:
    if employee.id == hr.id:
        return False
    if employee.reporting_hr_id == hr.id:
        return True
    if employee.reporting_hr_id is None and employee_role(employee) in (RoleName.MANAGER, RoleName.EMPLOYEE):
        manager = employee.reporting_manager
        if manager is not None and manager.reporting_hr_id is not None:
            return manager.reporting_hr_id == hr.id
        return _pool_enabled(db)
    return False


def can_access_employee(db: Session, user: User, employee: Optional[Employee]) -> bool:
    """View level: profile, attendance, reports, tasks, leave, document status."""
    if employee is None or user is None:
        return False
    if is_admin(user):
        return True
    me = own_employee(user)
    if me is None:
        return False
    if employee.id == me.id:
        return True
    role = role_of(user)
    if role == RoleName.HR_ADMIN:
        return _in_hr_scope(db, me, employee)
    if role == RoleName.MANAGER:
        return employee.reporting_manager_id == me.id
    return False


def can_view_sensitive(db: Session, user: User, employee: Optional[Employee]) -> bool:
    """Salary, payslips, UAN and document files: never a Manager's team."""
    if employee is None or user is None:
        return False
    if is_admin(user):
        return True
    me = own_employee(user)
    if me is not None and employee.id == me.id:
        return True
    if is_hr(user) and me is not None:
        return _in_hr_scope(db, me, employee)
    return False


def can_supervise_employee(db: Session, user: User, employee: Optional[Employee]) -> bool:
    """Review reports, first-level leave decisions, assign tasks (never self)."""
    if employee is None or user is None:
        return False
    if is_admin(user):
        return True
    me = own_employee(user)
    if me is None or employee.id == me.id:
        return False
    if is_hr(user):
        return _in_hr_scope(db, me, employee)
    if is_manager(user):
        return employee.reporting_manager_id == me.id
    return False


def can_manage_employee(db: Session, user: User, employee: Optional[Employee]) -> bool:
    """HR-level changes to someone else's record (never self)."""
    if employee is None or user is None:
        return False
    if is_admin(user):
        return True
    me = own_employee(user)
    if not is_hr(user) or me is None or employee.id == me.id:
        return False
    return _in_hr_scope(db, me, employee)


_CHECKS = {
    VIEW: can_access_employee,
    SENSITIVE: can_view_sensitive,
    SUPERVISE: can_supervise_employee,
    MANAGE: can_manage_employee,
}


def check(db: Session, user: User, employee: Optional[Employee], level: str = VIEW) -> bool:
    return _CHECKS[level](db, user, employee)


def _deny(db: Session, user: User, employee_id, level: str, what: Optional[str]) -> None:
    """Record the refusal (best effort) and answer 403."""
    try:
        from app.services import audit_service
        audit_service.record(
            db, AuditAction.ACCESS_DENIED, user=user, entity_type=what or "employee",
            entity_id=employee_id, meta={"level": level}, commit=True,
        )
    except Exception:  # pragma: no cover - auditing must never mask the 403
        db.rollback()
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)


def assert_employee(db: Session, user: User, employee_id: int, level: str = VIEW,
                    what: Optional[str] = None) -> Employee:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")
    if not check(db, user, employee, level):
        _deny(db, user, employee_id, level, what)
    return employee


def assert_level(db: Session, user: User, employee: Employee, level: str, what: Optional[str] = None) -> Employee:
    if not check(db, user, employee, level):
        _deny(db, user, employee.id if employee else None, level, what)
    return employee


# Record-type helpers (each module calls the one for its record) ------------
def can_access_report(db: Session, user: User, report) -> bool:
    return can_access_employee(db, user, report.employee)


def can_review_report(db: Session, user: User, report) -> bool:
    return can_supervise_employee(db, user, report.employee)


def can_access_leave(db: Session, user: User, leave) -> bool:
    return can_access_employee(db, user, leave.employee)


def can_access_task(db: Session, user: User, task) -> bool:
    return task.assigned_by_id == user.id or can_access_employee(db, user, task.employee)


def can_edit_task(db: Session, user: User, task) -> bool:
    """The assigner, or anyone with supervise rights over the assignee."""
    if is_admin(user):
        return True
    return (task.assigned_by_id == user.id and is_supervisor(user)) or can_supervise_employee(db, user, task.employee)


def can_access_document(db: Session, user: User, document, files: bool = False) -> bool:
    if files:
        return can_view_sensitive(db, user, document.employee)
    return can_access_employee(db, user, document.employee)


def can_access_salary(db: Session, user: User, salary_record) -> bool:
    return can_view_sensitive(db, user, salary_record.employee)


# ----------------------------------------------------------- task assignment
def can_assign_task(db: Session, user: User, employee: Employee) -> bool:
    """ADMIN -> HR/Manager/Employee, HR -> Manager/Employee, Manager -> own team."""
    if employee is None or employee.user is None:
        return False
    if is_admin(user):
        return True
    target_level = RoleName.LEVEL.get(employee_role(employee), 0)
    my_level = RoleName.LEVEL.get(role_of(user), 0)
    if target_level >= my_level:
        return False
    return can_supervise_employee(db, user, employee)


# ------------------------------------------------------------- leave routing
def initial_leave_stage(employee: Employee) -> str:
    role = employee_role(employee)
    if role == RoleName.HR_ADMIN:
        return ApprovalStage.ADMIN
    if role == RoleName.MANAGER:
        return ApprovalStage.HR
    if employee.reporting_manager_id is not None:
        return ApprovalStage.MANAGER
    return ApprovalStage.HR


def can_act_on_leave(db: Session, user: User, leave) -> bool:
    if leave.status != LeaveStatus.PENDING:
        return False
    employee = leave.employee
    stage = leave.approval_stage or ApprovalStage.HR
    if is_admin(user):
        return True
    if is_hr(user):
        return stage in (ApprovalStage.MANAGER, ApprovalStage.HR) and can_manage_employee(db, user, employee)
    if is_manager(user):
        me = own_employee(user)
        return (
            stage == ApprovalStage.MANAGER and me is not None
            and employee.reporting_manager_id == me.id
        )
    return False


def leave_actionable_filter(db: Session, user: User):
    """SQL condition on LeaveRequest for "requests waiting on me"."""
    from app.models.leave_request import LeaveRequest
    pending = LeaveRequest.status == LeaveStatus.PENDING
    if is_admin(user):
        return pending
    me = own_employee(user)
    if me is None:
        return false()
    if is_hr(user):
        ids = visible_ids_select(db, user, include_self=False)
        return and_(
            pending,
            LeaveRequest.approval_stage.in_((ApprovalStage.MANAGER, ApprovalStage.HR)),
            LeaveRequest.employee_id.in_(ids),
        )
    if is_manager(user):
        team = select(Employee.id).where(Employee.reporting_manager_id == me.id)
        return and_(pending, LeaveRequest.approval_stage == ApprovalStage.MANAGER,
                    LeaveRequest.employee_id.in_(team))
    return false()


# -------------------------------------------------- who hears about requests
def active_users_with_role(db: Session, role: str) -> List[User]:
    return (
        db.query(User).join(Role, Role.id == User.role_id)
        .filter(Role.name == role, User.is_active.is_(True)).all()
    )


def hr_users_for(db: Session, employee: Employee) -> List[User]:
    """The HR responsible for an employee; the HR pool (or Admins) if none."""
    hr = get_reporting_hr(employee)
    if hr is not None and hr.user is not None and hr.user.is_active and hr.id != employee.id:
        return [hr.user]
    if employee_role(employee) == RoleName.HR_ADMIN:
        return active_users_with_role(db, RoleName.ADMIN)
    if _pool_enabled(db):
        users = [u for u in active_users_with_role(db, RoleName.HR_ADMIN) if u.id != employee.user_id]
        if users:
            return users
    return active_users_with_role(db, RoleName.ADMIN)


def stage_reviewers(db: Session, employee: Employee, stage: str) -> List[User]:
    if stage == ApprovalStage.MANAGER:
        manager = get_reporting_manager(employee)
        if manager is not None and manager.user is not None and manager.user.is_active:
            return [manager.user]
        return hr_users_for(db, employee)
    if stage == ApprovalStage.HR:
        return hr_users_for(db, employee)
    if stage == ApprovalStage.ADMIN:
        return active_users_with_role(db, RoleName.ADMIN)
    return []


def oversight_users(db: Session, employee: Employee) -> List[User]:
    """Who is told about an employee's HR requests (profile change, payslip...)."""
    return hr_users_for(db, employee)


# --------------------------------------------------- hierarchy validation
def validate_assignment(
    db: Session, role: str, reporting_hr_id: Optional[int], reporting_manager_id: Optional[int],
    employee: Optional[Employee] = None, department_name: Optional[str] = None,
) -> Tuple[List[Tuple[str, str]], Optional[Employee], Optional[Employee]]:
    """Check a role + reporting line. Returns (errors, hr, manager).

    errors is a list of (field, message); the import preview and the API both
    use this, so a reporting line valid in one is valid in the other.
    """
    errors: List[Tuple[str, str]] = []
    hr = manager = None
    self_id = employee.id if employee is not None else None
    dept = department_name or (employee.department.name if employee is not None and employee.department else None)

    if role not in RoleName.EMPLOYEE_SIDE:
        errors.append(("role", "Role must be HR, Manager or Employee."))
        return errors, None, None
    if role in (RoleName.HR_ADMIN, RoleName.MANAGER) and dept == INTERNSHIP_DEPARTMENT_NAME:
        errors.append(("role", "Interns cannot hold the HR or Manager role."))

    if reporting_manager_id is not None:
        if reporting_manager_id == self_id:
            errors.append(("reporting_manager", "A person cannot report to themselves."))
        manager = db.query(Employee).filter(Employee.id == reporting_manager_id).first()
        if manager is None:
            errors.append(("reporting_manager", "Reporting manager not found."))
        elif employee_role(manager) != RoleName.MANAGER:
            errors.append(("reporting_manager", f"{manager.full_name} does not have the Manager role."))
            manager = None
        elif manager.user is None or not manager.user.is_active:
            errors.append(("reporting_manager", f"{manager.full_name}'s account is inactive."))
    if reporting_hr_id is not None:
        if reporting_hr_id == self_id:
            errors.append(("reporting_hr", "A person cannot report to themselves."))
        hr = db.query(Employee).filter(Employee.id == reporting_hr_id).first()
        if hr is None:
            errors.append(("reporting_hr", "Reporting HR not found."))
        elif employee_role(hr) != RoleName.HR_ADMIN:
            errors.append(("reporting_hr", f"{hr.full_name} does not have the HR role."))
            hr = None
        elif hr.user is None or not hr.user.is_active:
            errors.append(("reporting_hr", f"{hr.full_name}'s account is inactive."))

    if role == RoleName.HR_ADMIN:
        if reporting_manager_id is not None or reporting_hr_id is not None:
            errors.append(("reporting_hr", "HR reports directly to the Admin; leave Reporting HR and Manager empty."))
    elif role == RoleName.MANAGER:
        if reporting_manager_id is not None:
            errors.append(("reporting_manager", "A Manager reports to an HR, not to another manager."))
    else:  # employee / intern
        if manager is not None and hr is not None and manager.reporting_hr_id != hr.id:
            current = manager.reporting_hr.full_name if manager.reporting_hr else "no HR"
            errors.append((
                "reporting_hr",
                f"Manager {manager.full_name} reports to {current}, not to {hr.full_name}.",
            ))
    return errors, hr, manager


def _raise_first(errors: List[Tuple[str, str]]) -> None:
    if errors:
        raise HTTPException(status_code=422, detail=errors[0][1])


def _set_role(db: Session, employee: Employee, role: str) -> None:
    role_row = db.query(Role).filter(Role.name == role).first()
    if role_row is None:
        raise HTTPException(status_code=422, detail="Unknown role.")
    employee.user.role_id = role_row.id
    employee.user.role = role_row


def apply_assignment(
    db: Session, actor: Optional[User], employee: Employee, *, role=_UNSET,
    reporting_hr_id=_UNSET, reporting_manager_id=_UNSET, notify: bool = True,
) -> Dict[str, dict]:
    """Change role and/or reporting line, keeping the whole tree consistent.

    Returns {field: {"old": .., "new": ..}} for what changed. Authorization of
    the actor is checked by ``authorize_assignment`` before calling this.
    """
    old_role = employee_role(employee)
    new_role = old_role if role is _UNSET else role
    old_hr = employee.reporting_hr_id
    old_mgr = employee.reporting_manager_id
    new_mgr = old_mgr if reporting_manager_id is _UNSET else reporting_manager_id
    new_hr = old_hr if reporting_hr_id is _UNSET else reporting_hr_id

    if new_role == RoleName.HR_ADMIN:
        # HR reports to the Admin only. Explicit values still go through
        # validation below so a wrong request is rejected, not silently fixed.
        new_mgr = None if reporting_manager_id is _UNSET else reporting_manager_id
        new_hr = None if reporting_hr_id is _UNSET else reporting_hr_id
    if new_role == RoleName.MANAGER and reporting_manager_id is _UNSET:
        new_mgr = None

    # Choosing a new manager without naming an HR: the HR follows the manager.
    if (new_role == RoleName.EMPLOYEE and reporting_hr_id is _UNSET
            and reporting_manager_id is not _UNSET and new_mgr is not None):
        target = db.query(Employee).filter(Employee.id == new_mgr).first()
        if target is not None:
            new_hr = target.reporting_hr_id

    errors, hr, manager = validate_assignment(db, new_role, new_hr, new_mgr, employee=employee)
    _raise_first(errors)

    # Employees inherit the HR of their manager.
    if new_role == RoleName.EMPLOYEE and manager is not None:
        new_hr = manager.reporting_hr_id

    if old_role != new_role:
        if old_role == RoleName.MANAGER and new_role != RoleName.MANAGER:
            if db.query(Employee.id).filter(Employee.reporting_manager_id == employee.id).first():
                raise HTTPException(
                    status_code=409,
                    detail=f"{employee.full_name} still has team members. Reassign them before changing the role.",
                )
        if old_role == RoleName.HR_ADMIN and new_role != RoleName.HR_ADMIN:
            if db.query(Employee.id).filter(Employee.reporting_hr_id == employee.id).first():
                raise HTTPException(
                    status_code=409,
                    detail=f"{employee.full_name} still has managers/employees assigned. Reassign them first.",
                )
        _set_role(db, employee, new_role)

    employee.reporting_manager_id = new_mgr
    employee.reporting_hr_id = new_hr
    db.flush()

    # A manager moving to another HR takes the team along.
    if new_role == RoleName.MANAGER and new_hr != old_hr:
        for member in db.query(Employee).filter(Employee.reporting_manager_id == employee.id).all():
            member.reporting_hr_id = new_hr
        db.flush()

    changes = {}
    if old_role != new_role:
        changes["role"] = {"old": old_role, "new": new_role}
    if old_hr != new_hr:
        changes["reporting_hr_id"] = {"old": old_hr, "new": new_hr}
    if old_mgr != new_mgr:
        changes["reporting_manager_id"] = {"old": old_mgr, "new": new_mgr}

    if changes:
        from app.services import audit_service, notification_service
        audit_service.record(
            db, AuditAction.ROLE_CHANGED if "role" in changes else AuditAction.HIERARCHY_UPDATED,
            user=actor, entity_type="employee", entity_id=employee.id, meta={"changes": changes},
        )
        if notify and employee.user is not None:
            notification_service.create(
                db, user_id=employee.user_id, title="Your reporting line was updated",
                message=describe_line(employee),
                type_=NotificationType.HIERARCHY_CHANGED, related_entity="employee",
                related_id=employee.id, actor=actor,
            )
    return changes


def describe_line(employee: Employee) -> str:
    db_mgr = employee.reporting_manager
    db_hr = get_reporting_hr(employee)
    parts = [f"Role: {role_label(employee_role(employee))}"]
    if db_mgr is not None:
        parts.append(f"Reporting manager: {db_mgr.full_name}")
    if db_hr is not None and employee_role(employee) != RoleName.HR_ADMIN:
        parts.append(f"Reporting HR: {db_hr.full_name}")
    return ". ".join(parts) + "."


def authorize_assignment(
    db: Session, actor: User, employee: Optional[Employee], *, role: Optional[str],
    reporting_hr_id, reporting_manager_id,
) -> None:
    """Who may put whom where.

    Admin: anything. HR: only people in their own scope, only the Manager /
    Employee roles, only under themselves (Reporting HR = self) and only to
    managers they own. Managers and employees: nothing.
    """
    if is_admin(actor):
        return
    if not is_hr(actor):
        raise HTTPException(status_code=403, detail=FORBIDDEN)
    me = own_employee(actor)
    if employee is not None and not can_manage_employee(db, actor, employee):
        raise HTTPException(status_code=403, detail=FORBIDDEN)
    if role is not None and role not in (RoleName.MANAGER, RoleName.EMPLOYEE):
        raise HTTPException(status_code=403, detail="Only the Admin can assign the HR or Admin role.")
    if reporting_hr_id not in (_UNSET, None) and reporting_hr_id != me.id:
        raise HTTPException(status_code=403, detail="You can only place people under yourself.")
    if reporting_manager_id not in (_UNSET, None):
        manager = db.query(Employee).filter(Employee.id == reporting_manager_id).first()
        if manager is None or not can_manage_employee(db, actor, manager):
            raise HTTPException(status_code=403, detail="That manager is outside your hierarchy.")


UNSET = _UNSET


# ------------------------------------------------------------- summaries
def hierarchy_tree(db: Session, user: User) -> List[dict]:
    """HR -> Managers -> team, limited to what the user may view."""
    visible = visible_employee_ids(db, user)

    def ok(e: Employee) -> bool:
        return visible is None or e.id in visible

    def node(e: Employee) -> dict:
        return {
            "id": e.id, "full_name": e.full_name, "type": person_type(e),
            "role": employee_role(e), "designation": e.designation,
            "department": e.department.name if e.department else None,
            "department_id": e.department_id,
            "employee_code": e.display_employee_id,
            "is_active": bool(e.user and e.user.is_active),
            "photo_path": e.photo_path,
        }

    everyone = db.query(Employee).all()
    by_role: Dict[str, List[Employee]] = {}
    for e in everyone:
        by_role.setdefault(employee_role(e), []).append(e)
    hrs = sorted(by_role.get(RoleName.HR_ADMIN, []), key=lambda e: e.full_name)
    managers = by_role.get(RoleName.MANAGER, [])
    staff = by_role.get(RoleName.EMPLOYEE, [])

    def team_of(mgr: Employee) -> List[dict]:
        return [node(e) for e in sorted(staff, key=lambda e: e.full_name)
                if e.reporting_manager_id == mgr.id and ok(e)]

    tree = []
    for hr in hrs:
        if not ok(hr) and not any(ok(m) for m in managers if m.reporting_hr_id == hr.id):
            continue
        hr_node = node(hr)
        hr_node["managers"] = []
        for mgr in sorted(managers, key=lambda e: e.full_name):
            if mgr.reporting_hr_id == hr.id and ok(mgr):
                m = node(mgr)
                m["team"] = team_of(mgr)
                hr_node["managers"].append(m)
        hr_node["direct"] = [
            node(e) for e in sorted(staff, key=lambda e: e.full_name)
            if e.reporting_hr_id == hr.id and e.reporting_manager_id is None and ok(e)
        ]
        tree.append(hr_node)

    unassigned_mgrs = [m for m in managers if m.reporting_hr_id is None and ok(m)]
    unassigned_staff = [
        e for e in staff
        if e.reporting_hr_id is None and (e.reporting_manager is None or e.reporting_manager.reporting_hr_id is None)
        and e.reporting_manager_id is None and ok(e)
    ]
    if unassigned_mgrs or unassigned_staff:
        tree.append({
            "id": None, "full_name": "Not assigned to an HR", "type": "Unassigned",
            "managers": [dict(node(m), team=team_of(m)) for m in sorted(unassigned_mgrs, key=lambda e: e.full_name)],
            "direct": [node(e) for e in sorted(unassigned_staff, key=lambda e: e.full_name)],
        })
    return tree


def candidates(db: Session, user: User, role: str) -> List[Employee]:
    """Active people of a role the user could pick as a reporting line."""
    query = (
        db.query(Employee).join(User, Employee.user_id == User.id).join(Role, User.role_id == Role.id)
        .filter(Role.name == role, User.is_active.is_(True))
    )
    if is_hr(user):
        me = own_employee(user)
        if role == RoleName.HR_ADMIN:
            query = query.filter(Employee.id == me.id)
        else:
            query = restrict(query, db, user, Employee.id, include_self=False)
    elif not is_admin(user):
        query = query.filter(false())
    return query.order_by(Employee.full_name).all()


def ids_in(values: Iterable) -> Sequence[int]:
    return sorted({int(v) for v in values if v is not None})
