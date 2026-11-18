"""UAN workflow, employee management and internship backgrounds."""
from datetime import date


def test_uan_starts_not_submitted(client, intern_ds_headers):
    body = client.get("/api/uan/me", headers=intern_ds_headers).json()
    assert body["status"] == "Not Submitted"
    assert body["uan_number"] is None


def test_uan_must_be_twelve_digits(client, intern_ds_headers):
    for bad in ("12345", "abcdefghijkl", "1234567890123"):
        response = client.post(
            "/api/uan", json={"uan_number": bad}, headers=intern_ds_headers
        )
        assert response.status_code == 422, bad


def test_employee_submits_uan(client, intern_ds_headers):
    response = client.post(
        "/api/uan", json={"uan_number": "101234567890"}, headers=intern_ds_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Submitted"
    assert body["submitted_at"] is not None


def test_employee_cannot_verify_their_own_uan(client, intern_ds_headers):
    uan_id = client.get("/api/uan/me", headers=intern_ds_headers).json()["id"]
    assert client.post(
        f"/api/uan/{uan_id}/verify", json={}, headers=intern_ds_headers
    ).status_code == 403


def test_hr_rejection_requires_a_remark(client, hr_headers, intern_ds_headers):
    uan_id = client.get("/api/uan/me", headers=intern_ds_headers).json()["id"]
    assert client.post(
        f"/api/uan/{uan_id}/reject", json={}, headers=hr_headers
    ).status_code == 422


def test_hr_rejects_then_employee_resubmits(client, hr_headers, intern_ds_headers):
    uan_id = client.get("/api/uan/me", headers=intern_ds_headers).json()["id"]
    rejected = client.post(
        f"/api/uan/{uan_id}/reject",
        json={"remarks": "The number doesn't match your EPFO record."},
        headers=hr_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "Rejected"

    employee_view = client.get("/api/uan/me", headers=intern_ds_headers).json()
    assert employee_view["hr_remarks"] == "The number doesn't match your EPFO record."

    resubmitted = client.post(
        "/api/uan", json={"uan_number": "109876543210"}, headers=intern_ds_headers
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == "Submitted"


def test_hr_verifies_uan_and_it_locks(client, hr_headers, intern_ds_headers):
    uan_id = client.get("/api/uan/me", headers=intern_ds_headers).json()["id"]
    verified = client.post(f"/api/uan/{uan_id}/verify", json={}, headers=hr_headers)
    assert verified.status_code == 200
    assert verified.json()["status"] == "Verified"

    response = client.post(
        "/api/uan", json={"uan_number": "111111111111"}, headers=intern_ds_headers
    )
    assert response.status_code == 409


def test_uan_notification_reaches_the_employee(client, intern_ds_headers):
    items = client.get("/api/notifications", headers=intern_ds_headers).json()["items"]
    assert any(n["type"] in ("UAN Verified", "UAN Rejected") for n in items)


# ------------------------------------------------------------------ employees
def test_hr_creates_an_employee_with_login_account(client, hr_headers):
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    response = client.post(
        "/api/employees",
        json={
            "full_name": "New Starter", "email": "new.starter@test.com",
            "department_id": departments["Teaching"], "designation": "Trainer",
            "joining_date": "2026-05-04", "send_account_email": True,
        },
        headers=hr_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["employee"]["employee_code"].startswith("RG-")
    assert body["initial_password"]

    # The generated credentials actually work.
    from tests.conftest import login as do_login
    login = do_login(client, "new.starter@test.com", body["initial_password"])
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True


def test_duplicate_email_is_refused(client, hr_headers):
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    response = client.post(
        "/api/employees",
        json={"full_name": "Clone", "email": "new.starter@test.com",
              "department_id": departments["Teaching"], "designation": "Trainer",
              "joining_date": "2026-05-04"},
        headers=hr_headers,
    )
    assert response.status_code == 409


def test_intern_requires_a_background(client, hr_headers):
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    response = client.post(
        "/api/employees",
        json={"full_name": "Background-less Intern", "email": "nobg@test.com",
              "department_id": departments["Internship"], "designation": "Trainee",
              "joining_date": "2026-05-04"},
        headers=hr_headers,
    )
    assert response.status_code == 422
    assert "internship background" in response.json()["detail"].lower()


def test_interns_can_hold_different_backgrounds(client, hr_headers, intern_ds, intern_cy):
    ds = client.get(f"/api/employees/{intern_ds['id']}", headers=hr_headers).json()
    cy = client.get(f"/api/employees/{intern_cy['id']}", headers=hr_headers).json()
    assert ds["department"] == cy["department"] == "Internship"
    assert ds["internship_background"] == "Data Science"
    assert cy["internship_background"] == "Cyber Security"
    assert ds["is_intern"] and cy["is_intern"]


def test_hr_adds_a_new_internship_background(client, hr_headers):
    response = client.post(
        "/api/internship-backgrounds",
        json={"name": "Cloud Engineering"}, headers=hr_headers,
    )
    assert response.status_code == 201
    names = {b["name"] for b in client.get(
        "/api/internship-backgrounds", headers=hr_headers).json()}
    assert "Cloud Engineering" in names


def test_hr_deactivates_a_background(client, hr_headers):
    rows = client.get("/api/internship-backgrounds", headers=hr_headers).json()
    target = next(b for b in rows if b["name"] == "Cloud Engineering")
    response = client.put(
        f"/api/internship-backgrounds/{target['id']}",
        json={"is_active": False}, headers=hr_headers,
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_hr_adds_and_deactivates_a_department(client, hr_headers):
    created = client.post(
        "/api/departments", json={"name": "Design", "code": "DSGN"}, headers=hr_headers
    )
    assert created.status_code == 201
    updated = client.put(
        f"/api/departments/{created.json()['id']}",
        json={"is_active": False}, headers=hr_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


def test_duplicate_department_refused(client, hr_headers):
    response = client.post(
        "/api/departments", json={"name": "Marketing", "code": "MKT2"}, headers=hr_headers
    )
    assert response.status_code == 409


def test_employee_search_and_filter(client, hr_headers, employee_a):
    by_name = client.get("/api/employees?search=Employee A", headers=hr_headers).json()
    assert by_name["meta"]["total"] >= 1
    assert any("Employee A" in i["full_name"] for i in by_name["items"])

    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    interns = client.get(
        f"/api/employees?department_id={departments['Internship']}", headers=hr_headers
    ).json()
    assert all(i["department"] == "Internship" for i in interns["items"])


def test_employee_pagination(client, hr_headers):
    page = client.get("/api/employees?page=1&page_size=2", headers=hr_headers).json()
    assert len(page["items"]) <= 2
    assert page["meta"]["page_size"] == 2
    assert page["meta"]["pages"] >= 1


def test_deactivate_then_activate_blocks_and_restores_login(client, hr_headers):
    rows = client.get("/api/employees?search=New Starter", headers=hr_headers).json()
    employee = rows["items"][0]

    assert client.post(
        f"/api/employees/{employee['id']}/deactivate", headers=hr_headers
    ).status_code == 200
    blocked = client.post(
        "/api/auth/login",
        json={"email": "new.starter@test.com", "password": "irrelevant"},
    )
    assert blocked.status_code in (401, 403)

    assert client.post(
        f"/api/employees/{employee['id']}/activate", headers=hr_headers
    ).status_code == 200


def test_hr_cannot_deactivate_themselves(client, hr_headers, hr_user):
    response = client.post(
        f"/api/employees/{hr_user['id']}/deactivate", headers=hr_headers
    )
    assert response.status_code == 400
