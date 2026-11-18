"""Identity field locking and the HR-approved profile change workflow."""
from app.core.constants import AuditAction, NotificationType
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from app.models.notification import Notification
from tests.conftest import MINIMAL_PNG, hr_verify_photo, login, request_and_approve_id

FILL = {
    "phone": "+91 9876511111",
    "address": "9 Laxmi Nagar, New Delhi - 110092",
    "emergency_contact_name": "Family Contact",
    "emergency_contact_phone": "+91 9876511112",
    "emergency_contact_relation": "Sibling",
}


def _complete(client, headers, employee_id, hr_headers):
    client.put("/api/employees/me", json=FILL, headers=headers)
    client.put(
        f"/api/employees/{employee_id}",
        json={"date_of_birth": "1997-07-07", "gender": "Female"},
        headers=hr_headers,
    )
    client.post(
        "/api/employees/me/photo",
        files={"file": ("photo.png", MINIMAL_PNG, "image/png")},
        headers=headers,
    )
    hr_verify_photo(client, hr_headers, employee_id)
    request_and_approve_id(client, headers, employee_id, hr_headers)


def _notifications(user_id, type_):
    db = SessionLocal()
    try:
        return (
            db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.type == type_)
            .count()
        )
    finally:
        db.close()


def test_identity_fields_are_editable_before_the_profile_is_complete(
    client, hr_headers, intern_cy
):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    before = client.get("/api/employees/me", headers=headers).json()
    assert before["identity_locked"] is False

    response = client.put("/api/employees/me", json={"phone": "+91 9000000001"},
                          headers=headers)
    assert response.status_code == 200
    assert response.json()["phone"] == "+91 9000000001"


def test_completing_the_profile_locks_the_identity_fields(client, hr_headers, intern_cy):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    _complete(client, headers, intern_cy["id"], hr_headers)

    detail = client.get("/api/employees/me", headers=headers).json()
    assert detail["identity_locked"] is True
    assert detail["identity_locked_at"] is not None
    assert "phone" in detail["locked_fields"]
    assert "full_name" in detail["locked_fields"]

    lock = client.get("/api/employees/me/profile-lock", headers=headers).json()
    assert lock["identity_locked"] is True
    assert {f["field_name"] for f in lock["fields"]} >= {"full_name", "phone", "email"}


def test_locked_field_write_is_rejected_by_the_backend(client, intern_cy):
    """The API refuses the write even though the UI also disables the control."""
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    response = client.put("/api/employees/me", json={"phone": "+91 9123456789"},
                          headers=headers)
    assert response.status_code == 403
    assert "HR approval" in response.json()["detail"]

    # the stored value is untouched
    assert client.get("/api/employees/me", headers=headers).json()["phone"] != "+91 9123456789"

    db = SessionLocal()
    try:
        denied = (
            db.query(AuditLog)
            .filter(AuditLog.action == AuditAction.PROFILE_LOCKED_EDIT_DENIED)
            .count()
        )
    finally:
        db.close()
    assert denied >= 1


def test_unlocked_contact_fields_still_save(client, intern_cy):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    response = client.put(
        "/api/employees/me",
        json={"address": "77 New Street, New Delhi - 110092"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["address"] == "77 New Street, New Delhi - 110092"


def test_employee_raises_a_change_request(client, intern_cy):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    response = client.post(
        "/api/profile-change-requests",
        json={"field_name": "phone", "new_value": "+91 9555000111",
              "reason": "Changed my mobile number."},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "Pending"
    assert body["field_label"] == "Phone Number"
    assert body["new_value"] == "+91 9555000111"
    assert body["old_value"] is not None

    assert _notifications(intern_cy["user_id"], NotificationType.PROFILE_CHANGE_REQUESTED) >= 1


def test_duplicate_pending_request_is_refused(client, intern_cy):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    response = client.post(
        "/api/profile-change-requests",
        json={"field_name": "phone", "new_value": "+91 9555000222"},
        headers=headers,
    )
    assert response.status_code == 409
    assert "pending" in response.json()["detail"].lower()


def test_request_for_an_unmanaged_field_is_refused(client, intern_cy):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    response = client.post(
        "/api/profile-change-requests",
        json={"field_name": "designation", "new_value": "Chief Executive"},
        headers=headers,
    )
    assert response.status_code == 422


def test_employee_cannot_approve_their_own_request(client, intern_cy):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    mine = client.get("/api/profile-change-requests", headers=headers).json()
    request_id = mine["items"][0]["id"]

    assert client.post(f"/api/profile-change-requests/{request_id}/approve",
                       json={}, headers=headers).status_code == 403
    assert client.post(f"/api/profile-change-requests/{request_id}/reject",
                       json={"remarks": "no"}, headers=headers).status_code == 403


def test_employee_sees_only_their_own_requests(client, emp_a_headers, intern_cy):
    listing = client.get("/api/profile-change-requests", headers=emp_a_headers).json()
    assert all(item["employee_id"] != intern_cy["id"] for item in listing["items"])


def test_hr_approval_applies_the_change_and_notifies(client, hr_headers, intern_cy):
    pending = client.get(
        "/api/profile-change-requests?status=Pending", headers=hr_headers
    ).json()
    request = next(r for r in pending["items"] if r["employee_id"] == intern_cy["id"])

    response = client.post(
        f"/api/profile-change-requests/{request['id']}/approve",
        json={"remarks": "Verified against the ID proof."},
        headers=hr_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Approved"
    assert response.json()["hr_remarks"] == "Verified against the ID proof."

    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(Employee.id == intern_cy["id"]).first()
        assert employee.phone == "+91 9555000111"
    finally:
        db.close()

    assert _notifications(intern_cy["user_id"], NotificationType.PROFILE_CHANGE_APPROVED) >= 1

    db = SessionLocal()
    try:
        assert (
            db.query(AuditLog)
            .filter(AuditLog.action == AuditAction.PROFILE_CHANGE_APPROVED)
            .count()
            >= 1
        )
    finally:
        db.close()


def test_approving_twice_is_refused(client, hr_headers, intern_cy):
    approved = client.get(
        "/api/profile-change-requests?status=Approved", headers=hr_headers
    ).json()
    request_id = approved["items"][0]["id"]
    response = client.post(
        f"/api/profile-change-requests/{request_id}/approve", json={}, headers=hr_headers
    )
    assert response.status_code == 409


def test_rejection_keeps_the_old_value_and_needs_a_reason(client, hr_headers, intern_cy):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    created = client.post(
        "/api/profile-change-requests",
        json={"field_name": "full_name", "new_value": "Someone Else Entirely"},
        headers=headers,
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    # a rejection without a reason is refused: the employee needs to know why
    assert client.post(f"/api/profile-change-requests/{request_id}/reject",
                       json={}, headers=hr_headers).status_code == 422

    response = client.post(
        f"/api/profile-change-requests/{request_id}/reject",
        json={"remarks": "Name must match the Aadhaar record."},
        headers=hr_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Rejected"

    db = SessionLocal()
    try:
        employee = db.query(Employee).filter(Employee.id == intern_cy["id"]).first()
        assert employee.full_name != "Someone Else Entirely"
    finally:
        db.close()

    assert _notifications(intern_cy["user_id"], NotificationType.PROFILE_CHANGE_REJECTED) >= 1


def test_email_change_request_rejects_a_duplicate_address(client, hr_headers,
                                                          intern_cy, employee_a):
    headers = {
        "Authorization": "Bearer "
        + login(client, intern_cy["email"], intern_cy["password"]).json()["access_token"]
    }
    response = client.post(
        "/api/profile-change-requests",
        json={"field_name": "email", "new_value": employee_a["email"]},
        headers=headers,
    )
    assert response.status_code == 409
    assert "already uses" in response.json()["detail"]


def test_hr_can_filter_and_search_requests(client, hr_headers, intern_cy):
    approved = client.get(
        "/api/profile-change-requests?status=Approved", headers=hr_headers
    ).json()
    assert approved["items"]
    assert all(i["status"] == "Approved" for i in approved["items"])

    by_field = client.get(
        "/api/profile-change-requests?field_name=full_name", headers=hr_headers
    ).json()
    assert all(i["field_name"] == "full_name" for i in by_field["items"])

    searched = client.get(
        "/api/profile-change-requests?search=Intern Cyber", headers=hr_headers
    ).json()
    assert all(i["employee_id"] == intern_cy["id"] for i in searched["items"])

    bad = client.get("/api/profile-change-requests?status=Nonsense", headers=hr_headers)
    assert bad.status_code == 422
