"""Department-scoped meeting visibility and Google Meet link validation."""
from datetime import date

import pytest

MEET_URL = {
    "Marketing": "https://meet.google.com/mkt-abcd-efg",
    "Digital Marketing": "https://meet.google.com/dmk-abcd-efg",
    "Teaching": "https://meet.google.com/tch-abcd-efg",
    "Internship": "https://meet.google.com/int-abcd-efg",
}


@pytest.fixture(scope="module", autouse=True)
def meetings(client, hr_headers):
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    today = date.today().isoformat()
    plan = [
        ("Marketing", "Daily Sales Day Plan", "10:15:00", "10:45:00"),
        ("Digital Marketing", "Daily Work Discussion", "10:30:00", "11:00:00"),
        ("Teaching", "Daily Team Meeting", "11:00:00", "11:30:00"),
        ("Internship", "Intern Daily Meeting", "11:30:00", "12:00:00"),
    ]
    created = {}
    for dept, title, start, end in plan:
        response = client.post(
            "/api/meetings",
            json={
                "title": title, "department_id": departments[dept], "meeting_date": today,
                "start_time": start, "end_time": end,
                "agenda": f"{dept} daily sync.", "google_meet_url": MEET_URL[dept],
            },
            headers=hr_headers,
        )
        assert response.status_code == 201, response.text
        created[dept] = response.json()
    return created


def test_hr_sees_every_department_meeting(client, hr_headers):
    titles = {m["title"] for m in client.get("/api/meetings/today", headers=hr_headers).json()}
    assert {"Daily Sales Day Plan", "Daily Work Discussion",
            "Daily Team Meeting", "Intern Daily Meeting"} <= titles


def test_marketing_employee_sees_only_marketing(client, emp_b_headers):
    rows = client.get("/api/meetings/today", headers=emp_b_headers).json()
    titles = {m["title"] for m in rows}
    assert "Daily Sales Day Plan" in titles
    assert "Daily Team Meeting" not in titles      # Teaching hidden
    assert "Intern Daily Meeting" not in titles    # Internship hidden
    assert all(m["department"] == "Marketing" for m in rows)


def test_intern_sees_only_the_internship_meeting(client, intern_ds_headers):
    rows = client.get("/api/meetings/today", headers=intern_ds_headers).json()
    titles = {m["title"] for m in rows}
    assert "Intern Daily Meeting" in titles
    assert "Daily Sales Day Plan" not in titles
    assert all(m["department"] == "Internship" for m in rows)


def test_department_filter_cannot_be_used_to_peek(client, emp_b_headers, hr_headers):
    """An employee passing another department_id still only gets their own."""
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    rows = client.get(
        f"/api/meetings?department_id={departments['Teaching']}", headers=emp_b_headers
    ).json()
    assert all(m["department"] == "Marketing" for m in rows)


def test_stored_meet_url_is_returned_unchanged(client, emp_b_headers):
    row = next(
        m for m in client.get("/api/meetings/today", headers=emp_b_headers).json()
        if m["title"] == "Daily Sales Day Plan"
    )
    assert row["google_meet_url"] == MEET_URL["Marketing"]


def test_invalid_meet_url_is_refused(client, hr_headers):
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    for bad in ("https://zoom.us/j/123456", "not-a-url", "http://meet.google.com/abc"):
        response = client.post(
            "/api/meetings",
            json={
                "title": "Bad link", "department_id": departments["Marketing"],
                "meeting_date": date.today().isoformat(), "start_time": "09:00:00",
                "google_meet_url": bad,
            },
            headers=hr_headers,
        )
        assert response.status_code == 422, bad


def test_employee_cannot_create_or_cancel_meetings(client, emp_b_headers, hr_headers, meetings):
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    assert client.post(
        "/api/meetings",
        json={"title": "Unauthorised", "department_id": departments["Marketing"],
              "meeting_date": date.today().isoformat(), "start_time": "09:00:00"},
        headers=emp_b_headers,
    ).status_code == 403
    assert client.post(
        f"/api/meetings/{meetings['Marketing']['id']}/cancel", headers=emp_b_headers
    ).status_code == 403


def test_hr_can_cancel_a_meeting(client, hr_headers, meetings):
    response = client.post(
        f"/api/meetings/{meetings['Teaching']['id']}/cancel", headers=hr_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Cancelled"


def test_end_time_must_follow_start_time(client, hr_headers):
    departments = {d["name"]: d["id"] for d in client.get(
        "/api/departments", headers=hr_headers).json()}
    response = client.post(
        "/api/meetings",
        json={"title": "Backwards", "department_id": departments["Marketing"],
              "meeting_date": date.today().isoformat(),
              "start_time": "11:00:00", "end_time": "10:00:00"},
        headers=hr_headers,
    )
    assert response.status_code == 422
