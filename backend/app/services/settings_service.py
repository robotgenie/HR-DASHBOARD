"""Typed access to the app_settings key/value store."""
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.constants import SettingKey
from app.models.app_setting import AppSetting

DEFAULTS: Dict[str, tuple] = {
    SettingKey.DAILY_REPORT_MANDATORY: ("true", "bool", "Block logout until the daily report is submitted"),
    SettingKey.COMPANY_NAME: ("Robot Genie", "string", "Name shown on payslips and emails"),
    SettingKey.COMPANY_ADDRESS: (
        "Hno. 35, Office no. 301, 3rd Floor, Metro Pillar no. 35, "
        "Near Sai Baba Mandir, Laxmi Nagar, New Delhi - 110092",
        "string", "Registered address shown on payslips",
    ),
    SettingKey.COMPANY_UDYAM: (
        "UDYAM-DL-02-0061089", "string", "Udyam registration number shown on payslips",
    ),
    SettingKey.DEFAULT_WORK_LOCATION: (
        "", "string",
        "Work location printed on salary slips for employees who have none of their own",
    ),
    SettingKey.NOTIFY_ON_SALARY_CREDIT: ("true", "bool", "Notify employees when salary is credited"),
    SettingKey.NOTIFY_ON_DOCUMENT_REVIEW: ("true", "bool", "Notify employees on document verification"),
    SettingKey.EMAIL_ENABLED: ("true", "bool", "Send transactional emails"),
    SettingKey.PAYSLIP_AUTO_GENERATE: ("true", "bool", "Generate a payslip PDF when salary is credited"),
    SettingKey.SALARY_AUTO_GENERATE: (
        "true", "bool",
        "Create each month's salary slip automatically from the employee's previous month",
    ),
    SettingKey.HR_SEES_UNASSIGNED: (
        "true", "bool",
        "Let every HR see employees/managers that have no reporting HR assigned yet",
    ),
}


def _cast(value: str, value_type: str) -> Any:
    if value_type == "bool":
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if value_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return value


def ensure_defaults(db: Session) -> None:
    existing = {s.key for s in db.query(AppSetting).all()}
    for key, (value, vtype, description) in DEFAULTS.items():
        if key not in existing:
            db.add(AppSetting(key=key, value=value, value_type=vtype, description=description))
    db.flush()


def get(db: Session, key: str, default: Any = None) -> Any:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        if key in DEFAULTS:
            value, vtype, _ = DEFAULTS[key]
            return _cast(value, vtype)
        return default
    return _cast(row.value, row.value_type)


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    value = get(db, key, default)
    return bool(value)


def set_value(db: Session, key: str, value: Any) -> AppSetting:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        vtype = DEFAULTS.get(key, ("", "string", ""))[1]
        row = AppSetting(key=key, value="", value_type=vtype)
        db.add(row)
    if isinstance(value, bool):
        row.value = "true" if value else "false"
        row.value_type = "bool"
    elif isinstance(value, int):
        row.value = str(value)
        row.value_type = "int"
    else:
        row.value = str(value)
    db.flush()
    return row


def all_settings(db: Session) -> Dict[str, Any]:
    ensure_defaults(db)
    return {s.key: _cast(s.value, s.value_type) for s in db.query(AppSetting).all()}


def get_optional(db: Session, key: str) -> Optional[AppSetting]:
    return db.query(AppSetting).filter(AppSetting.key == key).first()
