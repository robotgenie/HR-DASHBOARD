"""Login, logout, password reset and session recording."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.utils.timeutil import utcnow
from app.core.config import settings
from app.core.constants import AuditAction, RoleName, SettingKey, WorkPeriod
from app.core.security import (
    create_access_token, generate_reset_token, hash_password, hash_token, verify_password,
)
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.models.work_session import WorkSession
from app.core.dependencies import ApiRuleError
from app.services import attendance_service, audit_service, email_service, settings_service, file_service

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="That email and password combination doesn't match.",
)

MIN_PASSWORD_LENGTH = 8


def validate_password_strength(password: str) -> None:
    value = password or ""
    if len(value) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Use at least {MIN_PASSWORD_LENGTH} characters.",
        )
    if value.isdigit() or value.isalpha():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mix letters and numbers so the password is harder to guess.",
        )


def authenticate(
    db: Session, email: str, password: str, ip: Optional[str] = None,
    user_agent: Optional[str] = None, selfie_data: Optional[str] = None,
    late_login_reason: Optional[str] = None, work_period: Optional[str] = None,
) -> dict:
    user = (
        db.query(User)
        .options(joinedload(User.role), joinedload(User.employee))
        .filter(func.lower(User.email) == (email or "").strip().lower())
        .first()
    )
    # Same error for unknown email and wrong password: no account enumeration.
    if user is None or not verify_password(password, user.hashed_password):
        raise INVALID_CREDENTIALS
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive. Contact HR.",
        )

    # Normal sign-in for every role. Attendance (late login, live selfie and
    # location) is recorded by Check-In on the dashboard, not at login.
    user.last_login_at = utcnow()
    db.flush()

    audit_service.record(
        db, AuditAction.LOGIN, user=user, entity_type="user", entity_id=user.id,
        ip_address=ip, user_agent=user_agent,
    )
    db.commit()

    token = create_access_token(subject=user.email, role=user.role_name, user_id=user.id)
    employee = user.employee
    onboarding_required = False
    onboarding_message = None
    if employee is not None:
        from app.services import document_service
        c = document_service.completion(db, employee)
        from app.services import bank_details_service
        docs_pending = c["missing"] > 0 or c["verified"] < c["total_required"]
        bank_pending = not bank_details_service.is_complete(employee)
        onboarding_required = docs_pending or bank_pending
        if docs_pending:
            onboarding_message = "Complete and get HR approval for all mandatory documents before continuing."
        elif bank_pending:
            onboarding_message = "Submit your bank details (Documents → Bank Details) for HR approval."
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "must_change_password": user.must_change_password,
        "user": user_summary(user),
        "onboarding_required": onboarding_required and user.role_name != RoleName.ADMIN,
        "onboarding_message": onboarding_message,
        "home": home_for(user),
    }


def portal_for(user: User) -> str:
    """Which dashboard an account lands on. One login, role-based routing."""
    role = user.role_name
    employee = user.employee
    if role == RoleName.ADMIN:
        return "admin"
    if role == RoleName.HR_ADMIN:
        return "hr"
    if role == RoleName.MANAGER:
        return "manager"
    if employee and employee.department and employee.department.name == "Internship":
        return "intern"
    return "employee"


def home_for(user: User) -> str:
    return f"/{portal_for(user)}/dashboard.html"


def user_summary(user: User) -> dict:
    from app.services import hierarchy_service
    employee = user.employee
    hr = hierarchy_service.get_reporting_hr(employee) if employee else None
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role_name,
        "role_label": (hierarchy_service.person_type(employee) if employee
                       else RoleName.LABELS.get(user.role_name, user.role_name)),
        "portal": portal_for(user),
        "has_employee_record": employee is not None,
        "employee_id": employee.id if employee else None,
        "employee_code": employee.employee_code if employee else None,
        "full_name": employee.full_name if employee else (user.full_name or user.email),
        "designation": employee.designation if employee else (user.title or "Administrator"),
        "department": employee.department.name if employee and employee.department else None,
        "department_id": employee.department_id if employee else None,
        "photo_path": employee.photo_path if employee else None,
        "reporting_manager": (employee.reporting_manager.full_name
                              if employee and employee.reporting_manager else None),
        "reporting_hr": hr.full_name if hr is not None and hr.id != (employee.id if employee else None) else None,
    }


def logout(
    db: Session, user: User, ip: Optional[str] = None,
    user_agent: Optional[str] = None, selfie_data: Optional[str] = None,
    logout_reason: Optional[str] = None
) -> dict:
    # Signing out only ends the portal session. Attendance is closed by
    # Check-Out (which enforces the report/leave rules), so logout is never
    # blocked and needs no selfie.
    now = utcnow()
    user.last_logout_at = now
    db.flush()

    audit_service.record(
        db, AuditAction.LOGOUT, user=user, entity_type="user", entity_id=user.id,
        ip_address=ip, user_agent=user_agent,
    )
    db.commit()
    return {"detail": "Signed out.", "logout_at": now}


def request_password_reset(db: Session, email: str) -> None:
    """Always succeeds from the caller's point of view; never reveals if an account exists."""
    user = (
        db.query(User)
        .options(joinedload(User.employee))
        .filter(func.lower(User.email) == (email or "").strip().lower())
        .first()
    )
    if user is None or not user.is_active:
        return

    raw, token_hash = generate_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=utcnow()
            + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )
    db.flush()

    audit_service.record(
        db, AuditAction.PASSWORD_RESET_REQUESTED, user=user, entity_type="user",
        entity_id=user.id,
    )
    if settings_service.get_bool(db, SettingKey.EMAIL_ENABLED, True):
        name = user.display_name
        email_service.send_password_reset_email(db, user.email, name, raw)
    db.commit()


def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    validate_password_strength(new_password)
    token_row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == hash_token(raw_token or ""))
        .first()
    )
    if (
        token_row is None
        or token_row.used_at is not None
        or token_row.expires_at < utcnow()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired or has already been used. Request a new one.",
        )

    user = token_row.user
    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    token_row.used_at = utcnow()

    # Any other outstanding links for this account stop working.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": utcnow()}, synchronize_session=False)
    db.flush()

    audit_service.record(
        db, AuditAction.PASSWORD_RESET_COMPLETED, user=user, entity_type="user",
        entity_id=user.id,
    )
    db.commit()


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Your current password is wrong."
        )
    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a password you haven't used here before.",
        )
    validate_password_strength(new_password)

    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    db.flush()
    audit_service.record(
        db, AuditAction.PASSWORD_CHANGED, user=user, entity_type="user", entity_id=user.id
    )
    db.commit()
