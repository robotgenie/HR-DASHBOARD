"""Role-based access control and resource ownership."""
HR_ONLY_GET = [
    "/api/dashboard/hr",
    "/api/employees",
    "/api/audit-logs",
    "/api/audit-logs/emails",
    "/api/settings",
    "/api/documents",
    "/api/uan",
]


def test_employee_cannot_reach_hr_endpoints(client, emp_a_headers):
    for path in HR_ONLY_GET:
        response = client.get(path, headers=emp_a_headers)
        assert response.status_code == 403, f"{path} returned {response.status_code}"


def test_employee_cannot_create_employees(client, emp_a_headers):
    response = client.post(
        "/api/employees",
        json={
            "full_name": "Sneaky Hire", "email": "sneaky@test.com", "department_id": 1,
            "designation": "Trainee", "joining_date": "2026-01-01",
        },
        headers=emp_a_headers,
    )
    assert response.status_code == 403


def test_employee_cannot_create_departments_or_backgrounds(client, emp_a_headers):
    assert client.post(
        "/api/departments", json={"name": "Fake", "code": "FAKE"}, headers=emp_a_headers
    ).status_code == 403
    assert client.post(
        "/api/internship-backgrounds", json={"name": "Fake"}, headers=emp_a_headers
    ).status_code == 403


def test_employee_cannot_view_another_employee(client, emp_a_headers, employee_b):
    response = client.get(f"/api/employees/{employee_b['id']}", headers=emp_a_headers)
    assert response.status_code == 403


def test_employee_can_view_their_own_record(client, emp_a_headers, employee_a):
    response = client.get(f"/api/employees/{employee_a['id']}", headers=emp_a_headers)
    assert response.status_code == 200
    assert response.json()["id"] == employee_a["id"]


def test_hr_can_view_any_employee(client, hr_headers, employee_a):
    response = client.get(f"/api/employees/{employee_a['id']}", headers=hr_headers)
    assert response.status_code == 200


def test_employee_cannot_read_another_employees_documents(client, emp_a_headers, employee_b):
    response = client.get(f"/api/documents/employee/{employee_b['id']}", headers=emp_a_headers)
    assert response.status_code == 403


def test_employee_cannot_read_another_employees_uan(client, emp_a_headers, employee_b):
    response = client.get(f"/api/uan/employee/{employee_b['id']}", headers=emp_a_headers)
    assert response.status_code == 403


def test_employee_self_update_cannot_change_hr_controlled_fields(
    client, emp_a_headers, employee_a
):
    """Extra keys are dropped by the schema, so designation stays HR-controlled."""
    before = client.get("/api/employees/me", headers=emp_a_headers).json()
    response = client.put(
        "/api/employees/me",
        json={
            "phone": "+91 9000000001",
            "designation": "Chief Executive Officer",
            "employment_status": "Terminated",
            "department_id": 99,
        },
        headers=emp_a_headers,
    )
    assert response.status_code == 200
    after = response.json()
    assert after["phone"] == "+91 9000000001"
    assert after["designation"] == before["designation"]
    assert after["employment_status"] == before["employment_status"]
    assert after["department_id"] == before["department_id"]


def test_employee_cannot_update_another_employee_via_hr_route(
    client, emp_a_headers, employee_b
):
    response = client.put(
        f"/api/employees/{employee_b['id']}",
        json={"designation": "Intern"},
        headers=emp_a_headers,
    )
    assert response.status_code == 403


def test_employee_cannot_deactivate_anyone(client, emp_a_headers, employee_b):
    assert client.post(
        f"/api/employees/{employee_b['id']}/deactivate", headers=emp_a_headers
    ).status_code == 403


def test_audit_logs_are_read_only_and_hr_only(client, emp_a_headers, hr_headers):
    assert client.get("/api/audit-logs", headers=emp_a_headers).status_code == 403
    assert client.get("/api/audit-logs", headers=hr_headers).status_code == 200
    # No write routes exist at all.
    for method in ("post", "put", "delete"):
        response = getattr(client, method)("/api/audit-logs", headers=hr_headers)
        assert response.status_code == 405


def test_employee_cannot_read_smtp_settings(client, emp_a_headers):
    assert client.get("/api/settings", headers=emp_a_headers).status_code == 403
    public = client.get("/api/settings/public", headers=emp_a_headers)
    assert public.status_code == 200
    body = " ".join(public.json().keys()).lower()
    assert "smtp" not in body and "password" not in body
