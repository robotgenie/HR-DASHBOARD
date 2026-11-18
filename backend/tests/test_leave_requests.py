from datetime import date, timedelta


def test_employee_can_request_leave_and_see_pending(client, emp_a_headers):
    start = date.today() + timedelta(days=10)
    end = start + timedelta(days=1)
    response = client.post(
        "/api/leave-requests",
        headers=emp_a_headers,
        json={
            "leave_type": "Casual Leave",
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "reason": "Personal work.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "Pending"
    assert body["leave_type"] == "Casual Leave"

    mine = client.get("/api/leave-requests/me", headers=emp_a_headers)
    assert mine.status_code == 200
    assert any(item["id"] == body["id"] for item in mine.json()["items"])


def test_hr_can_approve_leave_and_employee_sees_approved(client, emp_b_headers, hr_headers):
    start = date.today() + timedelta(days=20)
    response = client.post(
        "/api/leave-requests",
        headers=emp_b_headers,
        json={
            "leave_type": "Sick Leave",
            "from_date": start.isoformat(),
            "to_date": start.isoformat(),
            "reason": "Medical appointment.",
        },
    )
    assert response.status_code == 201, response.text
    leave_id = response.json()["id"]

    approved = client.patch(
        f"/api/leave-requests/{leave_id}",
        headers=hr_headers,
        json={"status": "Approved", "hr_remarks": "Approved by HR."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Approved"

    mine = client.get("/api/leave-requests/me", headers=emp_b_headers)
    assert mine.status_code == 200
    row = next(item for item in mine.json()["items"] if item["id"] == leave_id)
    assert row["status"] == "Approved"


def test_hr_rejection_requires_reason(client, intern_ds_headers, hr_headers):
    start = date.today() + timedelta(days=30)
    response = client.post(
        "/api/leave-requests",
        headers=intern_ds_headers,
        json={
            "leave_type": "Other",
            "from_date": start.isoformat(),
            "to_date": start.isoformat(),
            "reason": "Personal commitment.",
        },
    )
    assert response.status_code == 201, response.text
    leave_id = response.json()["id"]

    rejected = client.patch(
        f"/api/leave-requests/{leave_id}",
        headers=hr_headers,
        json={"status": "Rejected", "hr_remarks": ""},
    )
    assert rejected.status_code == 422

    rejected = client.patch(
        f"/api/leave-requests/{leave_id}",
        headers=hr_headers,
        json={"status": "Rejected", "hr_remarks": "Please discuss the dates with HR."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "Rejected"


def test_employee_cannot_review_leave(client, emp_a_headers, emp_b_headers):
    start = date.today() + timedelta(days=40)
    response = client.post(
        "/api/leave-requests",
        headers=emp_a_headers,
        json={
            "leave_type": "Earned Leave",
            "from_date": start.isoformat(),
            "to_date": start.isoformat(),
            "reason": "Family function.",
        },
    )
    assert response.status_code == 201
    leave_id = response.json()["id"]

    forbidden = client.patch(
        f"/api/leave-requests/{leave_id}",
        headers=emp_b_headers,
        json={"status": "Approved", "hr_remarks": "Not HR."},
    )
    assert forbidden.status_code == 403
