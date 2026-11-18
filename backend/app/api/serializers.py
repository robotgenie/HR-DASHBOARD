"""Model -> response-shape helpers shared by the routers."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.constants import (
    LOCKED_FIELD_LABELS, LOCKED_IDENTITY_FIELDS, ProfileChangeStatus, SalaryStatus,
)
from app.models.profile_change_request import ProfileChangeRequest
from app.models.employee import Employee
from app.models.meeting import Meeting
from app.models.salary import SalaryRecord
from app.services import document_service, employee_service
from app.utils.amount_words import amount_to_words, format_inr

PROFILE_FIELDS = (
    "full_name", "phone", "date_of_birth", "gender", "address",
    "emergency_contact_name", "emergency_contact_phone",
    "emergency_contact_relation", "designation", "photo_path",
)


def profile_completion(employee: Employee) -> float:
    filled = sum(1 for f in PROFILE_FIELDS if getattr(employee, f, None))
    return round(filled / len(PROFILE_FIELDS) * 100, 1)


def latest_salary(employee: Employee) -> Optional[SalaryRecord]:
    if not employee.salary_records:
        return None
    return sorted(
        employee.salary_records, key=lambda s: (s.period_year, s.period_month)
    )[-1]


def employee_list_item(db: Session, employee: Employee, with_docs: bool = True) -> dict:
    completion = document_service.completion(db, employee) if with_docs else None
    salary = latest_salary(employee)
    return {
        "id": employee.id,
        "employee_code": employee.employee_code,
        "unique_employee_id": employee.unique_employee_id,
        "display_employee_id": employee.display_employee_id,
        "full_name": employee.full_name,
        "email": employee.user.email if employee.user else "",
        "department": employee.department.name if employee.department else None,
        "department_id": employee.department_id,
        "internship_background": (
            employee.internship_background.name if employee.internship_background else None
        ),
        "designation": employee.designation,
        "joining_date": employee.joining_date,
        "employment_status": employee.employment_status,
        "is_active": employee.user.is_active if employee.user else False,
        "role": employee.user.role_name if employee.user else None,
        "role_label": _hierarchy().person_type(employee),
        "reporting_manager_id": employee.reporting_manager_id,
        "reporting_manager": (
            employee.reporting_manager.full_name if employee.reporting_manager else None
        ),
        "reporting_hr_id": _reporting_hr_id(employee),
        "reporting_hr": _reporting_hr_name(employee),
        "photo_path": employee.photo_path,
        "document_completion": completion["percent"] if completion else None,
        "document_label": completion["label"] if completion else None,
        "salary_status": salary.status if salary else SalaryStatus.PENDING,
    }


def _hierarchy():
    from app.services import hierarchy_service
    return hierarchy_service


def _reporting_hr_id(employee: Employee):
    hr = _hierarchy().get_reporting_hr(employee)
    return hr.id if hr is not None else None


def _reporting_hr_name(employee: Employee):
    hr = _hierarchy().get_reporting_hr(employee)
    return hr.full_name if hr is not None else None


def redact_for_viewer(db: Session, viewer, employee: Employee, data: dict) -> dict:
    """Remove salary/UAN fields when the viewer may see the profile but not
    the sensitive records (a Manager looking at a team member)."""
    if viewer is None or _hierarchy().can_view_sensitive(db, viewer, employee):
        return data
    for key in ("uan_number", "uan_remarks", "uan_submitted_at"):
        if key in data:
            data[key] = None
    if "uan_status" in data:
        data["uan_status"] = None
    if "salary_status" in data:
        data["salary_status"] = None
    return data


def employee_detail(db: Session, employee: Employee) -> dict:
    data = employee_list_item(db, employee)
    uan = employee.uan
    data.update(
        {
            "phone": employee.phone,
            "date_of_birth": employee.date_of_birth,
            "gender": employee.gender,
            "address": employee.address,
            "work_location": employee.work_location,
            "emergency_contact_name": employee.emergency_contact_name,
            "emergency_contact_phone": employee.emergency_contact_phone,
            "emergency_contact_relation": employee.emergency_contact_relation,
            "reporting_chain": _hierarchy().reporting_chain(employee),
            "internship_details": employee.internship_details,
            "is_intern": employee.is_intern,
            "uan_number": uan.uan_number if uan else None,
            "uan_status": uan.status if uan else "Not Submitted",
            "uan_submitted_at": uan.submitted_at if uan else None,
            "uan_remarks": uan.hr_remarks if uan else None,
            "profile_completion": profile_completion(employee),
            "profile_complete": employee_service.profile_is_complete(employee),
            "profile_missing_fields": employee_service.missing_profile_fields(employee),
            "identity_locked": employee.identity_locked,
            "identity_locked_at": employee.identity_locked_at,
            "locked_fields": list(LOCKED_IDENTITY_FIELDS),
            "employee_id_issued_at": employee.employee_id_issued_at,
            "id_card_status": getattr(employee, "id_card_status", "Approved" if employee.unique_employee_id else "Pending"),
            "id_card_requested_at": getattr(employee, "id_card_requested_at", None),
            "id_card_approved_at": getattr(employee, "id_card_approved_at", None),
            "id_card_rejected_at": getattr(employee, "id_card_rejected_at", None),
            "id_card_approval_remarks": getattr(employee, "id_card_approval_remarks", None),
            "id_card_available": bool(
                employee.unique_employee_id
                and employee_service.profile_is_complete(employee)
                and getattr(employee, "id_card_status", "Approved") == "Approved"
            ),
            "pending_change_requests": (
                db.query(ProfileChangeRequest)
                .filter(
                    ProfileChangeRequest.employee_id == employee.id,
                    ProfileChangeRequest.status == ProfileChangeStatus.PENDING,
                )
                .count()
            ),
            "photo_status": _photo_status(employee),
            "created_at": employee.created_at,
        }
    )
    return data


def _photo_status(employee: Employee) -> str:
    """Status of the latest photograph submission (Pending until HR approves)."""
    for record in employee.documents:
        if record.document_type and record.document_type.code == "PHOTO":
            return record.status
    return "Missing"


def profile_change_out(request: ProfileChangeRequest) -> dict:
    employee = request.employee
    return {
        "id": request.id,
        "employee_id": request.employee_id,
        "employee_name": employee.full_name if employee else None,
        "employee_display_id": employee.display_employee_id if employee else None,
        "department": (
            employee.department.name if employee and employee.department else None
        ),
        "field_name": request.field_name,
        "field_label": LOCKED_FIELD_LABELS.get(request.field_name, request.field_name),
        "old_value": request.old_value,
        "new_value": request.new_value,
        "reason": request.reason,
        "status": request.status,
        "hr_remarks": request.hr_remarks,
        "requested_at": request.requested_at,
        "reviewed_at": request.reviewed_at,
        "reviewed_by": (
            request.reviewed_by.email
            if getattr(request, "reviewed_by", None) is not None
            else None
        ),
        "created_at": request.created_at,
    }


def salary_out(record: SalaryRecord, db=None) -> dict:
    employee = record.employee
    is_intern = bool(employee and employee.is_intern)
    # Latest download request for this exact salary record, if any.
    latest = None
    if is_intern and record.download_requests:
        latest = record.download_requests[0]
    credited = record.status == SalaryStatus.CREDITED
    return {
        "id": record.id,
        "employee_id": record.employee_id,
        "is_intern": is_intern,
        "intern_download_allowed": bool(record.intern_download_allowed),
        # What the employee side of the UI should allow. HR is never limited.
        "employee_can_view_payslip": credited,
        "employee_can_download_payslip": credited and (
            record.intern_download_allowed if is_intern else True
        ),
        "download_block_reason": (
            "Download permission has not been granted by HR."
            if credited and is_intern and not record.intern_download_allowed
            else None
        ),
        "download_request_status": latest.status if latest else None,
        "download_request_id": latest.id if latest else None,
        "download_request_remarks": latest.hr_remarks if latest else None,
        # A rejected request may be raised again; a pending one may not.
        "can_request_download": bool(
            credited and is_intern and not record.intern_download_allowed
            and (latest is None or latest.status == "Rejected")
        ),
        "employee_name": employee.full_name,
        "employee_code": employee.employee_code,
        "department": employee.department.name if employee.department else None,
        "designation": employee.designation,
        "joining_date": employee.joining_date,
        "period_year": record.period_year,
        "period_month": record.period_month,
        "period_label": record.period_label,
        "working_days": record.working_days,
        "status": record.status,
        "total_earnings": record.total_earnings,
        "total_deductions": record.total_deductions,
        "net_pay": record.net_pay,
        "net_pay_display": format_inr(record.net_pay),
        "amount_in_words": amount_to_words(record.net_pay),
        "credit_date": record.credit_date,
        "credited_at": record.credited_at,
        "remarks": record.remarks,
        "has_payslip": record.slip is not None,
        "auto_generated": bool(record.auto_generated),
        "earnings": [
            {
                "id": c.id, "component_type": c.component_type, "name": c.name,
                "amount": c.amount, "sort_order": c.sort_order,
            }
            for c in record.earnings
        ],
        "deductions": [
            {
                "id": c.id, "component_type": c.component_type, "name": c.name,
                "amount": c.amount, "sort_order": c.sort_order,
            }
            for c in record.deductions
        ],
    }


def meeting_out(meeting: Meeting) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "department_id": meeting.department_id,
        "department": meeting.department.name if meeting.department else "",
        "meeting_date": meeting.meeting_date,
        "start_time": meeting.start_time,
        "end_time": meeting.end_time,
        "agenda": meeting.agenda,
        "google_meet_url": meeting.google_meet_url,
        "status": meeting.status,
        "is_today": meeting.meeting_date == date.today(),
    }


def report_out(report, include_employee: bool = True) -> dict:
    employee = report.employee
    return {
        "id": report.id,
        "employee_id": report.employee_id,
        "employee_name": employee.full_name if include_employee and employee else None,
        "employee_code": employee.employee_code if include_employee and employee else None,
        "department": (
            employee.department.name if include_employee and employee and employee.department
            else None
        ),
        "person_type": (_hierarchy().person_type(employee)
                        if include_employee and employee else None),
        "report_date": report.report_date,
        "report_type": getattr(report, "report_type", "EOD"),
        "tasks_completed": report.tasks_completed,
        "tasks_in_progress": report.tasks_in_progress,
        "tasks_pending": report.tasks_pending,
        "work_summary": report.work_summary,
        "challenges": report.challenges,
        "additional_comments": report.additional_comments,
        "status": report.status,
        "source": getattr(report, "source", None) or "Manual",
        "submitted_at": report.submitted_at,
        "reviewed_at": report.reviewed_at,
        "review_notes": report.review_notes,
        "reviewed_by_name": report.reviewed_by.display_name if getattr(report, "reviewed_by", None) else None,
        "attachments": report.attachments,
    }
