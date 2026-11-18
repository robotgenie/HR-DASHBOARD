"""Unique employee id generation and the electronic ID card."""
import re

from app.core.constants import AuditAction
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.employee import Employee
from tests.conftest import MINIMAL_PNG, hr_verify_photo, request_and_approve_id

COMPLETION_FIELDS = {
    "phone": "+91 9876500011",
    "address": "12 Laxmi Nagar, New Delhi - 110092",
    "emergency_contact_name": "Family Contact",
    "emergency_contact_phone": "+91 9876500012",
    "emergency_contact_relation": "Parent",
}


def _fill_profile(client, headers, employee_id, with_photo=True, hr_headers=None):
    """Complete a profile the way the UI does: self-service fields, then photo."""
    client.put("/api/employees/me", json=COMPLETION_FIELDS, headers=headers)
    # date_of_birth and gender are HR-owned on create, so HR sets them
    if hr_headers:
        client.put(
            f"/api/employees/{employee_id}",
            json={"date_of_birth": "1998-04-12", "gender": "Male"},
            headers=hr_headers,
        )
    if with_photo:
        client.post(
            "/api/employees/me/photo",
            files={"file": ("photo.png", MINIMAL_PNG, "image/png")},
            headers=headers,
        )
        if hr_headers:
            # The photo only counts once HR approves it; then the ID is requested
            # and approved (Profile complete -> Request ID -> HR approval).
            hr_verify_photo(client, hr_headers, employee_id)
            request_and_approve_id(client, headers, employee_id, hr_headers)


def test_no_employee_id_until_profile_is_complete(client, hr_headers, employee_b, emp_b_headers):
    """A fresh employee has no unique id, and the card explains what is missing."""
    detail = client.get("/api/employees/me", headers=emp_b_headers).json()
    assert detail["unique_employee_id"] is None
    assert detail["profile_complete"] is False
    assert detail["id_card_available"] is False
    assert detail["profile_missing_fields"]

    card = client.get("/api/employees/me/id-card", headers=emp_b_headers).json()
    assert card["available"] is False
    assert "Profile photograph" in card["missing_fields"]

    # ...and the PDF is refused rather than rendering a half-empty badge
    pdf = client.get("/api/employees/me/id-card/pdf", headers=emp_b_headers)
    assert pdf.status_code == 409
    assert "complete" in pdf.json()["detail"].lower()


def test_employee_id_issued_on_profile_completion(
    client, hr_headers, employee_b, emp_b_headers
):
    _fill_profile(client, emp_b_headers, employee_b["id"], hr_headers=hr_headers)

    detail = client.get("/api/employees/me", headers=emp_b_headers).json()
    assert detail["profile_complete"] is True
    assert detail["unique_employee_id"] is not None
    assert re.fullmatch(r"RGEMP\d{3,}", detail["unique_employee_id"])
    assert detail["id_card_available"] is True
    assert detail["employee_id_issued_at"] is not None


def test_employee_id_is_immutable_and_never_reissued(client, emp_b_headers, employee_b):
    first = client.get("/api/employees/me", headers=emp_b_headers).json()["unique_employee_id"]

    # repeated profile saves and an explicit issue call must not change it
    client.put("/api/employees/me", json={"address": "New address, New Delhi"},
               headers=emp_b_headers)
    again = client.post("/api/employees/me/request-id-approval", headers=emp_b_headers)
    assert again.status_code == 200
    assert again.json()["unique_employee_id"] == first

    later = client.get("/api/employees/me", headers=emp_b_headers).json()
    assert later["unique_employee_id"] == first


def test_employee_id_cannot_be_set_through_the_update_api(client, emp_b_headers, hr_headers,
                                                          employee_b):
    """The id is server-assigned: sending one is ignored, not honoured."""
    original = client.get("/api/employees/me", headers=emp_b_headers).json()["unique_employee_id"]
    client.put("/api/employees/me", json={"unique_employee_id": "RGEMP999"},
               headers=emp_b_headers)
    client.put(f"/api/employees/{employee_b['id']}", json={"unique_employee_id": "RGEMP999"},
               headers=hr_headers)
    after = client.get("/api/employees/me", headers=emp_b_headers).json()["unique_employee_id"]
    assert after == original != "RGEMP999"


def test_employee_ids_are_unique_across_employees(
    client, hr_headers, employee_a, emp_a_headers, intern_ds, intern_ds_headers
):
    _fill_profile(client, emp_a_headers, employee_a["id"], hr_headers=hr_headers)
    _fill_profile(client, intern_ds_headers, intern_ds["id"], hr_headers=hr_headers)

    db = SessionLocal()
    try:
        ids = [
            e.unique_employee_id
            for e in db.query(Employee).all()
            if e.unique_employee_id
        ]
    finally:
        db.close()
    assert len(ids) >= 3
    assert len(ids) == len(set(ids)), "unique employee ids must not repeat"


def test_id_card_pdf_is_generated_with_the_employee_details(client, emp_b_headers):
    response = client.get("/api/employees/me/id-card/pdf", headers=emp_b_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "ID-Card-RGEMP" in response.headers["content-disposition"]


def test_hr_can_view_any_employee_id_card(client, hr_headers, employee_b):
    card = client.get(f"/api/employees/{employee_b['id']}/id-card", headers=hr_headers)
    assert card.status_code == 200
    assert card.json()["available"] is True

    pdf = client.get(f"/api/employees/{employee_b['id']}/id-card/pdf", headers=hr_headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_employee_cannot_view_another_employees_id_card(client, emp_a_headers, employee_b):
    response = client.get(f"/api/employees/{employee_b['id']}/id-card", headers=emp_a_headers)
    assert response.status_code == 403

    pdf = client.get(f"/api/employees/{employee_b['id']}/id-card/pdf", headers=emp_a_headers)
    assert pdf.status_code == 403


def test_id_generation_and_card_are_audit_logged(client, employee_b):
    db = SessionLocal()
    try:
        actions = {
            row.action
            for row in db.query(AuditLog).filter(
                AuditLog.entity_type == "employee",
                AuditLog.entity_id == employee_b["id"],
            )
        }
    finally:
        db.close()
    assert AuditAction.EMPLOYEE_ID_GENERATED in actions
    assert AuditAction.ID_CARD_GENERATED in actions
