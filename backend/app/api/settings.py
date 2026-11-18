from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.core.constants import AuditAction, SettingKey
from app.core.dependencies import get_current_user, require_hr
from app.database.database import get_db
from app.models.user import User
from app.schemas.notification import SettingsUpdate
from app.services import audit_service, email_service, settings_service

router = APIRouter(prefix="/settings", tags=["Settings"])

# Keys an employee is allowed to read. SMTP values are never in this set.
PUBLIC_KEYS = {SettingKey.DAILY_REPORT_MANDATORY, SettingKey.COMPANY_NAME}
# Organisation-wide access rules only the Admin may change.
ADMIN_ONLY_KEYS = {SettingKey.HR_SEES_UNASSIGNED}


@router.get("/public")
def public_settings(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Safe subset for the employee UI. No SMTP credentials are ever exposed."""
    values = settings_service.all_settings(db)
    return {k: v for k, v in values.items() if k in PUBLIC_KEYS}


@router.get("")
def hr_settings(db: Session = Depends(get_db), current_user: User = Depends(require_hr)):
    """HR view. SMTP is reported as configured/not configured, never the credentials."""
    return {
        "values": settings_service.all_settings(db),
        "email": {
            "smtp_configured": email_service.smtp_configured(),
            "smtp_host": app_config.SMTP_HOST or None,
            "from_email": app_config.SMTP_FROM_EMAIL,
            "from_name": app_config.SMTP_FROM_NAME,
        },
        "uploads": {
            "max_file_size_mb": app_config.MAX_FILE_SIZE // (1024 * 1024),
            "allowed_extensions": sorted(app_config.allowed_extension_set),
        },
        "company": {
            "name": app_config.COMPANY_NAME,
            "address": app_config.COMPANY_ADDRESS,
        },
    }


@router.put("")
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr),
):
    from fastapi import HTTPException
    from app.core.constants import RoleName
    updated: Dict[str, Any] = {}
    changed_location = False
    for key, value in payload.values.items():
        if key not in settings_service.DEFAULTS:
            continue  # unknown keys are ignored rather than silently stored
        if key in ADMIN_ONLY_KEYS and current_user.role_name != RoleName.ADMIN:
            if str(value).lower() == str(settings_service.get(db, key)).lower():
                continue  # the HR form re-sends every value; unchanged is fine
            raise HTTPException(status_code=403, detail="Only the Admin can change this setting.")
        if key == SettingKey.DEFAULT_WORK_LOCATION:
            value = str(value or "").strip()[:120]
            changed_location = str(settings_service.get(db, key) or "") != value
        settings_service.set_value(db, key, value)
        updated[key] = value

    if changed_location:
        # Re-render not-yet-credited generated payslips that print the default.
        from app.models.employee import Employee
        from app.services import bank_details_service
        for employee in db.query(Employee).filter(
            (Employee.work_location.is_(None)) | (Employee.work_location == "")
        ).all():
            bank_details_service.refresh_payslips(db, employee, current_user, include_credited=False)

    audit_service.record(
        db, AuditAction.SETTING_UPDATED, user=current_user, entity_type="app_setting",
        entity_id=None, meta={"keys": list(updated)},
    )
    db.commit()
    return {"values": settings_service.all_settings(db), "updated": list(updated)}
