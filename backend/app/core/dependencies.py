"""Authentication, role and ownership dependencies.

Every protected route composes these; nothing relies on the frontend hiding a button.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from app.core.constants import RoleName
from app.core.security import decode_access_token
from app.database.database import get_db
from app.models.employee import Employee
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sign in to continue.",
    headers={"WWW-Authenticate": "Bearer"},
)
FORBIDDEN_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You don't have access to this resource.",
)


class ApiRuleError(HTTPException):
    """An HTTPException that also carries a machine-readable code and context.

    The JSON body keeps the usual {"detail": "..."} shape (so every existing
    caller still shows a readable message) and adds "code" and "context" so the
    UI can react precisely, e.g. open the late-login reason dialog.
    """

    def __init__(self, status_code: int, detail: str, code: str, context: Optional[dict] = None):
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.context = context or {}


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_ERROR
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise CREDENTIALS_ERROR

    user_id = payload.get("uid")
    if user_id is None:
        raise CREDENTIALS_ERROR

    user = (
        db.query(User)
        .options(joinedload(User.role), joinedload(User.employee))
        .filter(User.id == user_id)
        .first()
    )
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


def require_hr(current_user: User = Depends(get_current_user)) -> User:
    """HR-level authority: HR (inside their hierarchy) or the Admin (everywhere).

    Passing this dependency is never enough on its own: every route then limits
    the data through app.services.hierarchy_service.
    """
    if current_user.role_name not in (RoleName.HR_ADMIN, RoleName.ADMIN):
        raise FORBIDDEN_ERROR
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role_name != RoleName.ADMIN:
        raise FORBIDDEN_ERROR
    return current_user


def require_supervisor(current_user: User = Depends(get_current_user)) -> User:
    """Admin, HR or Manager (team monitoring / review screens)."""
    if current_user.role_name not in (RoleName.ADMIN, RoleName.HR_ADMIN, RoleName.MANAGER):
        raise FORBIDDEN_ERROR
    return current_user


def require_employee(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role_name != RoleName.EMPLOYEE:
        raise FORBIDDEN_ERROR
    return current_user


def get_current_employee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Employee:
    """The employee profile of the signed-in user (HR and Managers also have one).

    The Admin is not an employee and has none, so employee-only features
    (check-in, hourly updates, own leave/reports) answer 404 for the Admin.
    """
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employee profile is linked to this account.",
        )
    return employee


def is_hr(user: User) -> bool:
    """True for accounts with HR-level authority (HR or Admin)."""
    return user.role_name in (RoleName.HR_ADMIN, RoleName.ADMIN)


def is_admin(user: User) -> bool:
    return user.role_name == RoleName.ADMIN


def assert_can_access_employee(user: User, employee_id: int, db: Session, level: str = "view") -> Employee:
    """Hierarchy check for one employee record (see hierarchy_service levels).

    Admin reaches everyone, HR their hierarchy, a Manager their team, everyone
    else only themselves. Refusals are 403 and audited.
    """
    from app.services import hierarchy_service
    return hierarchy_service.assert_employee(db, user, employee_id, level)


def client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> Optional[str]:
    return (request.headers.get("user-agent") or "")[:255] or None
