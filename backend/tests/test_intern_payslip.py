"""Intern payslip permissions: viewing is always allowed, downloading is granted."""
from app.core.constants import AuditAction, NotificationType
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.notification import Notification

INTERN_COMPONENTS = [
    {"name": "Basic Salary", "component_type": "earning", "amount": 5565},
    {"name": "House Rent Allowance", "component_type": "earning", "amount": 2782},
    {"name": "Travelling Allowance", "component_type": "earning", "amount": 2225},
    {"name": "Special Allowance", "component_type": "earning", "amount": 557},
]

EMPLOYEE_COMPONENTS = [
    {"name": "Basic Salary", "component_type": "earning", "amount": 18000},
    {"name": "House Rent Allowance", "component_type": "earning", "amount": 9000},
]


def _create_and_credit(client, hr_headers, employee_id, month, components):
    created = client.post(
        "/api/salaries",
        json={
            "employee_id": employee_id, "period_year": 2026, "period_month": month,
            "working_days": 26, "components": components,
        },
        headers=hr_headers,
    )
    assert created.status_code in (200, 201), created.text
    salary_id = created.json()["id"]
    assert client.post(
        f"/api/salaries/{salary_id}/payslip/generate", headers=hr_headers
    ).status_code == 200
    credited = client.post(
        f"/api/salaries/{salary_id}/credit",
        json={"credit_date": f"2026-{month:02d}-28"}, headers=hr_headers,
    )
    assert credited.status_code == 200
    return salary_id


def test_regular_employee_can_download_once_credited(
    client, hr_headers, employee_b, emp_b_headers
):
    """No extra permission applies to non-interns."""
    salary_id = _create_and_credit(client, hr_headers, employee_b["id"], 5,
                                   EMPLOYEE_COMPONENTS)
    detail = client.get(f"/api/salaries/{salary_id}", headers=emp_b_headers).json()
    assert detail["is_intern"] is False
    assert detail["employee_can_view_payslip"] is True
    assert detail["employee_can_download_payslip"] is True
    assert detail["download_block_reason"] is None

    assert client.get(f"/api/salaries/{salary_id}/payslip",
                      headers=emp_b_headers).status_code == 200
    download = client.get(f"/api/salaries/{salary_id}/payslip/download",
                          headers=emp_b_headers)
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")


def test_intern_can_view_but_not_download_without_permission(
    client, hr_headers, intern_ds, intern_ds_headers
):
    salary_id = _create_and_credit(client, hr_headers, intern_ds["id"], 5,
                                   INTERN_COMPONENTS)

    detail = client.get(f"/api/salaries/{salary_id}", headers=intern_ds_headers).json()
    assert detail["is_intern"] is True
    assert detail["intern_download_allowed"] is False
    assert detail["employee_can_view_payslip"] is True
    assert detail["employee_can_download_payslip"] is False
    assert detail["download_block_reason"] == (
        "Download permission has not been granted by HR."
    )

    # viewing stays open
    view = client.get(f"/api/salaries/{salary_id}/payslip", headers=intern_ds_headers)
    assert view.status_code == 200
    assert view.content.startswith(b"%PDF")

    # downloading is refused by the API, not just by a disabled button
    download = client.get(
        f"/api/salaries/{salary_id}/payslip/download", headers=intern_ds_headers
    )
    assert download.status_code == 403
    assert download.json()["detail"] == (
        "Download permission has not been granted by HR."
    )

    db = SessionLocal()
    try:
        assert (
            db.query(AuditLog)
            .filter(AuditLog.action == AuditAction.INTERN_PAYSLIP_DOWNLOAD_DENIED)
            .count()
            >= 1
        )
    finally:
        db.close()


def test_intern_cannot_grant_their_own_permission(client, intern_ds_headers, intern_ds):
    salaries = client.get("/api/salaries", headers=intern_ds_headers).json()
    salary_id = salaries["items"][0]["id"]
    response = client.post(
        f"/api/salaries/{salary_id}/payslip-permission",
        json={"allowed": True}, headers=intern_ds_headers,
    )
    assert response.status_code == 403


def test_hr_grants_permission_and_the_intern_is_notified(
    client, hr_headers, intern_ds, intern_ds_headers
):
    salaries = client.get("/api/salaries", headers=intern_ds_headers).json()
    salary_id = salaries["items"][0]["id"]

    response = client.post(
        f"/api/salaries/{salary_id}/payslip-permission",
        json={"allowed": True}, headers=hr_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intern_download_allowed"] is True
    assert body["notification_created"] is True

    db = SessionLocal()
    try:
        notification = (
            db.query(Notification)
            .filter(
                Notification.user_id == intern_ds["user_id"],
                Notification.type == NotificationType.PAYSLIP_DOWNLOAD_GRANTED,
            )
            .first()
        )
        assert notification is not None
        assert "permission to download" in notification.message
    finally:
        db.close()

    detail = client.get(f"/api/salaries/{salary_id}", headers=intern_ds_headers).json()
    assert detail["employee_can_download_payslip"] is True
    assert detail["download_block_reason"] is None


def test_intern_download_succeeds_after_permission(client, intern_ds_headers):
    salaries = client.get("/api/salaries", headers=intern_ds_headers).json()
    salary_id = salaries["items"][0]["id"]
    download = client.get(
        f"/api/salaries/{salary_id}/payslip/download", headers=intern_ds_headers
    )
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")

    db = SessionLocal()
    try:
        assert (
            db.query(AuditLog)
            .filter(AuditLog.action == AuditAction.INTERN_PAYSLIP_DOWNLOADED)
            .count()
            >= 1
        )
    finally:
        db.close()


def test_permission_is_per_salary_record(client, hr_headers, intern_ds, intern_ds_headers):
    """Granting one month must not unlock another."""
    second = _create_and_credit(client, hr_headers, intern_ds["id"], 6, INTERN_COMPONENTS)
    detail = client.get(f"/api/salaries/{second}", headers=intern_ds_headers).json()
    assert detail["intern_download_allowed"] is False
    assert client.get(
        f"/api/salaries/{second}/payslip/download", headers=intern_ds_headers
    ).status_code == 403


def test_permission_can_be_withdrawn(client, hr_headers, intern_ds_headers):
    salaries = client.get("/api/salaries", headers=intern_ds_headers).json()
    granted = next(s for s in salaries["items"] if s["intern_download_allowed"])

    response = client.post(
        f"/api/salaries/{granted['id']}/payslip-permission",
        json={"allowed": False}, headers=hr_headers,
    )
    assert response.status_code == 200
    assert response.json()["intern_download_allowed"] is False

    assert client.get(
        f"/api/salaries/{granted['id']}/payslip/download", headers=intern_ds_headers
    ).status_code == 403

    db = SessionLocal()
    try:
        assert (
            db.query(AuditLog)
            .filter(AuditLog.action == AuditAction.INTERN_PAYSLIP_PERMISSION_REVOKED)
            .count()
            >= 1
        )
    finally:
        db.close()


def test_permission_endpoint_rejects_non_interns(client, hr_headers, employee_b):
    salaries = client.get(
        f"/api/salaries?employee_id={employee_b['id']}", headers=hr_headers
    ).json()
    salary_id = salaries["items"][0]["id"]
    response = client.post(
        f"/api/salaries/{salary_id}/payslip-permission",
        json={"allowed": True}, headers=hr_headers,
    )
    assert response.status_code == 422
    assert "interns only" in response.json()["detail"]


def test_hr_download_is_never_blocked(client, hr_headers, intern_ds_headers):
    salaries = client.get("/api/salaries", headers=intern_ds_headers).json()
    blocked = next(s for s in salaries["items"] if not s["intern_download_allowed"])
    response = client.get(
        f"/api/salaries/{blocked['id']}/payslip/download", headers=hr_headers
    )
    assert response.status_code == 200


def test_intern_cannot_download_another_interns_payslip(
    client, hr_headers, intern_cy, intern_ds_headers
):
    other = _create_and_credit(client, hr_headers, intern_cy["id"], 5, INTERN_COMPONENTS)
    client.post(f"/api/salaries/{other}/payslip-permission",
                json={"allowed": True}, headers=hr_headers)
    # permission belongs to that intern, not to whoever asks
    assert client.get(
        f"/api/salaries/{other}/payslip/download", headers=intern_ds_headers
    ).status_code == 403
