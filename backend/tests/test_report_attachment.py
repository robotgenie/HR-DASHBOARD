"""EOD reports: an attachment is mandatory, and logout depends on a valid report."""
from datetime import date

from app.core.constants import AuditAction, ReportStatus, SettingKey
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.daily_report import DailyReport
from app.services import report_service
from tests.conftest import MINIMAL_PNG

TODAY = date.today().isoformat()

REPORT_BODY = {
    "report_date": TODAY,
    "tasks_completed": "Closed the assigned tickets.",
    "tasks_in_progress": "Drafting the weekly summary.",
    "tasks_pending": "Waiting on design assets.",
    "work_summary": "Cleared the open queue and joined the stand-up.",
    "challenges": "None blocking.",
    "submit": True,
}


def _report_id(employee_id):
    db = SessionLocal()
    try:
        report = (
            db.query(DailyReport)
            .filter(
                DailyReport.employee_id == employee_id,
                DailyReport.report_date == date.today(),
            )
            .first()
        )
        return report.id if report else None
    finally:
        db.close()


def test_submit_without_attachment_is_refused_with_the_exact_message(
    client, emp_a_headers, employee_a
):
    response = client.post("/api/reports", json=REPORT_BODY, headers=emp_a_headers)
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Please upload at least one attachment before submitting your EOD report."
    )


def test_the_typed_report_is_kept_as_a_draft_when_blocked(client, employee_a):
    """Blocking the submission must not throw away what the employee wrote."""
    db = SessionLocal()
    try:
        report = (
            db.query(DailyReport)
            .filter(
                DailyReport.employee_id == employee_a["id"],
                DailyReport.report_date == date.today(),
            )
            .first()
        )
        assert report is not None
        assert report.status == ReportStatus.DRAFT
        assert report.tasks_completed == "Closed the assigned tickets."
        assert report.submitted_at is None
    finally:
        db.close()


def test_blocked_submission_is_audit_logged(client):
    db = SessionLocal()
    try:
        assert (
            db.query(AuditLog)
            .filter(AuditLog.action == AuditAction.REPORT_ATTACHMENT_MISSING)
            .count()
            >= 1
        )
    finally:
        db.close()


def test_logout_is_blocked_while_no_valid_report_exists(client, emp_a_headers):
    check = client.get("/api/reports/logout-check", headers=emp_a_headers).json()
    assert check["report_mandatory"] is True
    assert check["attachment_required"] is True
    assert check["attachment_count"] == 0
    assert check["report_submitted_today"] is False
    assert check["logout_blocked"] is True


def test_draft_can_be_saved_without_an_attachment(client, emp_a_headers):
    """Only submitting needs evidence; saving a draft mid-day does not."""
    body = dict(REPORT_BODY, submit=False)
    response = client.post("/api/reports", json=body, headers=emp_a_headers)
    assert response.status_code in (200, 201)
    assert response.json()["status"] == ReportStatus.DRAFT


def test_submit_succeeds_once_an_attachment_exists(client, emp_a_headers, employee_a):
    report_id = _report_id(employee_a["id"])
    assert report_id is not None

    upload = client.post(
        f"/api/reports/{report_id}/attachments",
        files={"file": ("screenshot.png", MINIMAL_PNG, "image/png")},
        headers=emp_a_headers,
    )
    assert upload.status_code in (200, 201)

    response = client.post("/api/reports", json=REPORT_BODY, headers=emp_a_headers)
    assert response.status_code in (200, 201)
    assert response.json()["status"] == ReportStatus.SUBMITTED
    assert response.json()["submitted_at"] is not None
    assert len(response.json()["attachments"]) == 1


def test_logout_is_allowed_after_a_valid_submission(client, emp_a_headers):
    # A normal working day needs both reports: the Noon Report is filed too.
    noon = dict(REPORT_BODY, report_type="Noon")
    assert client.post("/api/reports", json=noon, headers=emp_a_headers).status_code in (200, 201)
    check = client.get("/api/reports/logout-check", headers=emp_a_headers).json()
    assert check["report_submitted_today"] is True
    assert check["attachment_count"] == 1
    assert check["logout_blocked"] is False


def test_logging_out_never_submits_a_report(client, hr_headers, employee_b, emp_b_headers):
    """Logging out is not a submission channel: nothing is auto-filed."""
    before = client.get("/api/reports/logout-check", headers=emp_b_headers).json()
    assert before["report_submitted_today"] is False

    # Signing out is a plain logout; with reports pending, Check-Out (not
    # logout) is what the server refuses - and nothing is filed either way.
    from datetime import datetime, time as _t
    from app.utils import clock
    from tests.conftest import SUITE_NOW, selfie_data_url
    clock.set_fixed_now(datetime.combine(date.today(), _t(14, 0)))   # within working hours
    body = {"selfie_data": selfie_data_url(), "latitude": 28.63, "longitude": 77.27}
    client.post("/api/attendance/check-in", json=dict(body, late_login_reason="x", work_period="Second Half"),
                headers=emp_b_headers)
    refused = client.post("/api/attendance/check-out", json=body, headers=emp_b_headers)
    assert refused.status_code == 409
    assert refused.json()["code"] == "CHECKOUT_BLOCKED"
    clock.set_fixed_now(SUITE_NOW)

    db = SessionLocal()
    try:
        report = (
            db.query(DailyReport)
            .filter(
                DailyReport.employee_id == employee_b["id"],
                DailyReport.report_date == date.today(),
            )
            .first()
        )
        assert report is None or report.status != ReportStatus.SUBMITTED
    finally:
        db.close()


def test_logout_is_not_blocked_when_hr_makes_reports_optional(
    client, hr_headers, intern_ds_headers
):
    assert client.put(
        "/api/settings",
        json={"values": {SettingKey.DAILY_REPORT_MANDATORY: False}},
        headers=hr_headers,
    ).status_code == 200
    try:
        check = client.get("/api/reports/logout-check", headers=intern_ds_headers).json()
        assert check["report_mandatory"] is False
        assert check["logout_blocked"] is False
    finally:
        client.put(
            "/api/settings",
            json={"values": {SettingKey.DAILY_REPORT_MANDATORY: True}},
            headers=hr_headers,
        )


def test_attachment_count_helper_matches_the_stored_rows(client, employee_a):
    db = SessionLocal()
    try:
        report = (
            db.query(DailyReport)
            .filter(
                DailyReport.employee_id == employee_a["id"],
                DailyReport.report_date == date.today(),
            )
            .first()
        )
        assert report_service.attachment_count(report) == len(report.attachments)
        assert report_service.attachment_count(None) == 0
    finally:
        db.close()


def test_reviewed_report_cannot_be_resubmitted(client, hr_headers, emp_a_headers,
                                               employee_a):
    report_id = _report_id(employee_a["id"])
    assert client.post(
        f"/api/reports/{report_id}/review",
        json={"review_notes": "Looks good."}, headers=hr_headers,
    ).status_code == 200

    response = client.post("/api/reports", json=REPORT_BODY, headers=emp_a_headers)
    assert response.status_code == 409
