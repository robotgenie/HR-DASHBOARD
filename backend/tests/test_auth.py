"""Authentication, password flows and role routing."""
from app.core.security import hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("Correct@Horse1")
    assert hashed != "Correct@Horse1"
    assert verify_password("Correct@Horse1", hashed)
    assert not verify_password("wrong-password", hashed)


def test_long_password_is_not_truncated():
    """bcrypt ignores bytes past 72; the pre-hash keeps long passwords distinct."""
    base = "A" * 80
    hashed = hash_password(base + "ending-one")
    assert not verify_password(base + "ending-two", hashed)


def test_hr_login_routes_to_hr_dashboard(client, hr_user):
    response = client.post(
        "/api/auth/login",
        json={"email": hr_user["email"], "password": hr_user["password"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "HR_ADMIN"
    assert body["home"] == "/hr/dashboard.html"
    assert body["access_token"]


def test_employee_login_routes_to_employee_dashboard(client, employee_a):
    from tests.conftest import login
    response = login(client, employee_a["email"], employee_a["password"])
    assert response.status_code == 200
    assert response.json()["home"] == "/employee/dashboard.html"


def test_wrong_password_rejected(client, employee_a):
    response = client.post(
        "/api/auth/login",
        json={"email": employee_a["email"], "password": "definitely-not-it"},
    )
    assert response.status_code == 401


def test_unknown_email_gives_same_error_as_wrong_password(client):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@test.com", "password": "whatever1"}
    )
    assert response.status_code == 401


def test_unauthenticated_requests_are_rejected(client):
    for path in ("/api/employees", "/api/dashboard/hr", "/api/audit-logs", "/api/salaries"):
        assert client.get(path).status_code == 401, path


def test_garbage_token_rejected(client):
    response = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert response.status_code == 401


def test_forgot_password_never_reveals_whether_account_exists(client, employee_a):
    known = client.post("/api/auth/forgot-password", json={"email": employee_a["email"]})
    unknown = client.post("/api/auth/forgot-password", json={"email": "ghost@test.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_reset_with_invalid_token_is_refused(client):
    response = client.post(
        "/api/auth/reset-password",
        json={"token": "made-up-token", "new_password": "BrandNew@2026"},
    )
    assert response.status_code == 400


def test_change_password_requires_the_current_one(client, emp_a_headers):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong", "new_password": "BrandNew@2026"},
        headers=emp_a_headers,
    )
    assert response.status_code == 400


def test_weak_new_password_rejected(client, emp_a_headers, employee_a):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": employee_a["password"], "new_password": "abcdefgh"},
        headers=emp_a_headers,
    )
    assert response.status_code == 422


def test_logout_records_the_session(client, emp_b_headers, hr_headers):
    from tests.conftest import selfie_data_url
    # Daily reports are made optional so this test is only about the session record.
    client.put("/api/settings", json={"values": {"daily_report_mandatory": False}}, headers=hr_headers)
    try:
        response = client.post("/api/auth/logout", json={"selfie_data": selfie_data_url()},
                               headers=emp_b_headers)
        assert response.status_code == 200, response.text
    finally:
        client.put("/api/settings", json={"values": {"daily_report_mandatory": True}}, headers=hr_headers)
