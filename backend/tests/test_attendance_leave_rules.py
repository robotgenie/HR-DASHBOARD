"""Attendance (Check-In / Check-Out), leave-driven report rules, tasks, hourly
updates, monthly report, photo approval, HR ID auto-approval, notifications.

Login is a normal sign-in; attendance - late-login reason, live selfie and
location - is recorded by Check-In / Check-Out. Every test uses its own fresh
employee and pins the clock to exact IST times.
"""
import io
import uuid
from datetime import date, datetime, time

import pytest

from app.core.constants import RoleName
from app.database.database import SessionLocal
from app.models.daily_report import DailyReport
from app.models.work_session import WorkSession
from app.utils import clock
from tests.conftest import (
    EMP_PASSWORD, MINIMAL_PDF, MINIMAL_PNG, SUITE_NOW, _make_user, selfie_data_url,
)

DAY = date(2026, 9, 15)          # a Tuesday
NEXT = date(2026, 9, 16)
LOC = {"latitude": 28.6304, "longitude": 77.2773, "accuracy": 18}


def at(hh, mm=0, day=DAY):
    clock.set_fixed_now(datetime.combine(day, time(hh, mm)))


@pytest.fixture(autouse=True)
def _restore_clock():
    yield
    clock.set_fixed_now(SUITE_NOW)


def new_person(intern=False, hr=False):
    tag = uuid.uuid4().hex[:6]
    if hr:
        return _make_user("HR", "HR Executive", f"hr.{tag}@test.com", f"HR {tag}",
                          RoleName.HR_ADMIN, EMP_PASSWORD)
    if intern:
        return _make_user("Internship", "Trainee", f"in.{tag}@test.com", f"Intern {tag}",
                          RoleName.EMPLOYEE, EMP_PASSWORD, background="Data Science")
    return _make_user("Marketing", "Associate", f"em.{tag}@test.com", f"Emp {tag}",
                      RoleName.EMPLOYEE, EMP_PASSWORD)


def sign_in(client, person):
    r = client.post("/api/auth/login", json={"email": person["email"], "password": EMP_PASSWORD})
    assert r.status_code == 200, r.text                       # normal login, no selfie
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def check_in(client, h, reason="Metro delay", work_period=None, loc=LOC, selfie=True):
    body = dict(loc or {}, late_login_reason=reason)
    if selfie:
        body["selfie_data"] = selfie_data_url()
    if work_period:
        body["work_period"] = work_period
    return client.post("/api/attendance/check-in", json=body, headers=h)


def check_out(client, h, loc=LOC, selfie=True):
    body = dict(loc or {})
    if selfie:
        body["selfie_data"] = selfie_data_url()
    return client.post("/api/attendance/check-out", json=body, headers=h)


def in_ok(client, h, **kw):
    r = check_in(client, h, **kw)
    assert r.status_code == 200, r.text
    return r.json()["session"]


def leave(client, h, hr_headers, period, leave_type="Casual Leave", day=DAY, to=None, approve=True):
    body = {"leave_type": leave_type, "from_date": day.isoformat(), "to_date": (to or day).isoformat(),
            "leave_period": period, "reason": "Personal work at home"}
    r = client.post("/api/leave-requests", json=body, headers=h)
    assert r.status_code == 201, r.text
    if approve:
        a = client.patch(f"/api/leave-requests/{r.json()['id']}", json={"status": "Approved"},
                         headers=hr_headers)
        assert a.status_code == 200, a.text
    return r.json()


def report(client, h, rtype, day=DAY, submit=True):
    body = {"report_type": rtype, "report_date": day.isoformat() if day else None,
            "work_summary": f"{rtype} work", "tasks_completed": "Tasks done", "submit": submit}
    return client.post("/api/reports", json=body, headers=h)


def with_attachment(client, h, rtype, day=DAY):
    draft = report(client, h, rtype, day, submit=False)
    assert draft.status_code in (200, 201), draft.text
    up = client.post(f"/api/reports/{draft.json()['id']}/attachments",
                     files={"file": ("proof.png", MINIMAL_PNG, "image/png")}, headers=h)
    assert up.status_code == 200, up.text
    return report(client, h, rtype, day)


def last_session(user_id):
    db = SessionLocal()
    try:
        return db.query(WorkSession).filter(WorkSession.user_id == user_id).order_by(WorkSession.id.desc()).first()
    finally:
        db.close()


def assign(client, hr_headers, person, title="Hire 5 Employees", target=5, day=DAY):
    r = client.post("/api/tasks", json={"employee_ids": [person["id"]], "title": title,
                                        "target": target, "unit": "hires", "task_date": day.isoformat()},
                    headers=hr_headers)
    assert r.status_code == 201, r.text
    return r.json()["items"][0]


def hourly(client, h, slot, task_id=None, units=0, status="In Progress", text="Screened candidates"):
    return client.post("/api/hourly-updates", json={
        "slot_index": slot, "task_id": task_id, "work_completed": text, "units_completed": units,
        "task_status": status, "remaining_work": "More interviews", "description": "Details"}, headers=h)


# ------------------------------------------------------------------ login
def test_login_is_normal_and_records_no_attendance(client):
    p = new_person()
    at(10, 40)                                   # late, but login itself never asks
    h = sign_in(client, p)
    assert last_session(p["user_id"]) is None
    status = client.get("/api/attendance/status", headers=h).json()
    assert status["state"] == "not_checked_in" and status["can_check_in"] is True
    assert status["check_in_context"]["late_by_period"]["Full Day"] == 40
    # logout is a plain sign-out: no selfie, no report gate
    assert client.post("/api/auth/logout", headers=h).status_code == 200


# ------------------------------------------------------------------ Test 1 / 7
def test_normal_day_check_in_reports_check_out_extra_hours(client):
    p = new_person()
    at(9, 58)
    h = sign_in(client, p)
    s = in_ok(client, h)
    assert s["late_minutes"] == 0 and s["check_in_location"]["latitude"] == 28.6304
    assert s["check_in_selfie"] is True
    at(13, 5)
    noon = report(client, h, "Noon", day=None).json()
    assert noon["status"] == "Submitted" and noon["report_date"] == DAY.isoformat()
    blocked = check_out(client, h)
    assert blocked.status_code == 409 and blocked.json()["code"] == "CHECKOUT_BLOCKED"
    assert "EOD Report" in blocked.json()["detail"]
    at(18, 2)
    assert with_attachment(client, h, "EOD").json()["status"] == "Submitted"
    at(19, 30)
    out = check_out(client, h)
    assert out.status_code == 200, out.text
    row = last_session(p["user_id"])
    assert row.extra_work_minutes == 90 and row.check_out_latitude is not None
    assert row.logout_selfie_path and row.login_selfie_path
    again = check_in(client, h)
    assert again.status_code == 409 and again.json()["code"] == "ALREADY_CHECKED_OUT"


def test_check_in_requires_location_and_selfie(client):
    p = new_person()
    at(9, 50)
    h = sign_in(client, p)
    no_loc = check_in(client, h, loc=None)
    assert no_loc.status_code == 422 and no_loc.json()["code"] == "LOCATION_REQUIRED"
    no_selfie = check_in(client, h, selfie=False)
    assert no_selfie.status_code == 428 and no_selfie.json()["code"] == "SELFIE_REQUIRED"
    assert last_session(p["user_id"]) is None                 # nothing half-recorded
    in_ok(client, h)
    twice = check_in(client, h)
    assert twice.status_code == 409 and twice.json()["code"] == "ALREADY_CHECKED_IN"


# ------------------------------------------------------------------ Test 5 / 6
def test_late_check_in_needs_reason_stored_and_visible_to_hr(client, hr_headers):
    p = new_person()
    at(10, 20)
    h = sign_in(client, p)
    first = check_in(client, h, reason=None)
    assert first.status_code == 428 and first.json()["code"] == "LATE_LOGIN_REASON_REQUIRED"
    ctx = first.json()["context"]
    assert ctx["late_minutes"] == 20 and ctx["expected_login"] == "10:00" and ctx["actual_login"] == "10:20"
    in_ok(client, h, reason="Bus breakdown near Laxmi Nagar")
    s = last_session(p["user_id"])
    assert s.late_login_minutes == 20 and s.late_login_reason == "Bus breakdown near Laxmi Nagar"
    assert s.expected_login_time == time(10, 0) and s.work_date == DAY
    rows = client.get("/api/attendance/hr/late-logins", params={
        "date_from": DAY.isoformat(), "date_to": DAY.isoformat(), "employee_id": p["id"]},
        headers=hr_headers).json()["items"]
    assert rows[0]["late_minutes"] == 20 and rows[0]["late_reason"] == "Bus breakdown near Laxmi Nagar"
    assert client.get("/api/attendance/hr/late-logins", headers=h).status_code == 403


def test_intern_late_check_in_also_needs_reason(client):
    p = new_person(intern=True)
    at(10, 45)
    h = sign_in(client, p)
    r = check_in(client, h, reason=None)
    assert r.status_code == 428 and r.json()["code"] == "LATE_LOGIN_REASON_REQUIRED"


def test_hr_checks_in_without_late_login_rule(client):
    """Hierarchy update: HR is an employee and checks in/out with the existing
    selfie flow. The existing HR exception is kept: no late-login reason/penalty."""
    hr = new_person(hr=True)
    at(11, 40)
    r = client.post("/api/auth/login", json={"email": hr["email"], "password": EMP_PASSWORD})
    assert r.status_code == 200 and r.json()["home"] == "/hr/dashboard.html"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/attendance/status", headers=h).json()["applicable"] is True
    assert check_in(client, h, reason=None).status_code == 200
    s = last_session(hr["user_id"])
    assert s.late_login_minutes == 0 and s.login_selfie_path
    assert client.post("/api/auth/logout", json={}, headers=h).status_code == 200


def test_afternoon_check_in_without_leave_is_second_half(client):
    p = new_person()
    at(14, 10)
    h = sign_in(client, p)
    r = check_in(client, h, reason=None)
    assert r.status_code == 428 and r.json()["code"] == "WORK_PERIOD_REQUIRED"
    assert r.json()["context"]["late_by_period"]["Second Half"] == 70
    in_ok(client, h, work_period="Second Half")
    s = last_session(p["user_id"])
    assert s.work_period == "Second Half" and s.late_login_minutes == 70


def test_check_in_closed_after_working_hours(client):
    p = new_person()
    at(18, 30)
    h = sign_in(client, p)
    r = check_in(client, h)
    assert r.status_code == 409 and r.json()["code"] == "DAY_OVER"


# ------------------------------------------------------------------ tasks + hourly updates
def test_tasks_and_hourly_updates_with_attachment_and_progress(client, hr_headers):
    p = new_person()
    at(9, 55)
    h = sign_in(client, p)
    task = assign(client, hr_headers, p)
    assert task["target"] == 5 and task["remaining"] == 5 and task["assigned_by"]
    # hourly updates need a check-in
    at(11, 5)
    assert hourly(client, h, 0, task["id"]).json()["code"] == "NOT_CHECKED_IN"
    at(9, 58)
    in_ok(client, h)
    at(11, 5)
    state = client.get("/api/hourly-updates/today", headers=h).json()
    assert [s["status"] for s in state["slots"][:3]] == ["Due", "Open", "Upcoming"]
    assert state["tasks"][0]["title"] == "Hire 5 Employees"
    # one due notification per period, not repeated
    client.get("/api/hourly-updates/today", headers=h)
    notes = [n for n in client.get("/api/notifications", headers=h).json()["items"]
             if n["type"] == "Hourly Update Due"]
    assert len(notes) == 1
    # task is required when one is assigned; future hour refused
    assert hourly(client, h, 0).status_code == 422
    assert hourly(client, h, 3, task["id"]).json()["code"] == "SLOT_NOT_APPLICABLE"
    u = hourly(client, h, 0, task["id"], units=2)
    assert u.status_code == 201, u.text
    body = u.json()
    assert body["task_completed"] == 2 and body["task_remaining"] == 3 and body["assigned_by"]
    assert hourly(client, h, 0, task["id"]).json()["code"] == "ALREADY_SUBMITTED"
    att = client.post(f"/api/hourly-updates/{body['id']}/attachments",
                      files={"file": ("proof.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")}, headers=h)
    assert att.status_code == 200 and len(att.json()["attachments"]) == 1
    bad = client.post(f"/api/hourly-updates/{body['id']}/attachments",
                      files={"file": ("x.exe", io.BytesIO(b"MZ\x90"), "application/octet-stream")}, headers=h)
    assert bad.status_code in (400, 415, 422)
    notes = [n for n in client.get("/api/notifications", headers=h).json()["items"]
             if n["type"] == "Hourly Update Due"]
    assert notes[0]["is_read"] is True                             # cleared by the submission
    # HR sees who, which task, who assigned, hour, progress, attachments
    hr_rows = client.get("/api/hourly-updates", params={"employee_id": p["id"]}, headers=hr_headers).json()["items"]
    assert hr_rows[0]["task_title"] == "Hire 5 Employees" and hr_rows[0]["slot_label"] == "10:00 AM - 11:00 AM"
    assert hr_rows[0]["attachments"]
    # finishing the target completes the task
    at(12, 10)
    hourly(client, h, 1, task["id"], units=3)
    t = client.get(f"/api/tasks/{task['id']}", headers=h).json()
    assert t["status"] == "Completed" and t["remaining"] == 0 and t["progress_percent"] == 100


def test_hourly_update_after_1pm_satisfies_noon_report(client, hr_headers):
    p = new_person()
    at(9, 55)
    h = sign_in(client, p)
    task = assign(client, hr_headers, p, title="Prepare campaign", target=None)
    in_ok(client, h)
    at(12, 5)
    hourly(client, h, 1, task["id"], text="Drafted campaign copy")
    check = client.get("/api/reports/logout-check", headers=h).json()
    assert check["noon_submitted"] is False                       # before 1 PM: not yet
    at(13, 10)
    hourly(client, h, 2, task["id"], text="Designed banners")
    check = client.get("/api/reports/logout-check", headers=h).json()
    assert check["noon_submitted"] is True and check["noon_source"] == "Hourly Updates"
    noon = client.get("/api/reports/me/today", params={"report_type": "Noon"}, headers=h).json()
    assert "Designed banners" in noon["work_summary"] and noon["source"] == "Hourly Updates"
    # the Noon Report stays editable through the existing API
    edit = client.post("/api/reports", json={"report_type": "Noon", "work_summary": "Edited", "submit": True}, headers=h)
    assert edit.status_code in (200, 201) and edit.json()["work_summary"] == "Edited"


def test_no_hourly_updates_after_6pm_and_eod_unchanged(client, hr_headers):
    p = new_person()
    at(9, 55)
    h = sign_in(client, p)
    task = assign(client, hr_headers, p, target=None)
    in_ok(client, h)
    at(18, 20)
    state = client.get("/api/hourly-updates/today", headers=h).json()
    assert state["hourly_active"] is False
    assert all(s["status"] in ("Due", "Submitted") for s in state["slots"])   # no new periods after 6 PM
    assert with_attachment(client, h, "EOD").json()["status"] == "Submitted"


# ------------------------------------------------------------------ leave cases
def test_morning_half_leave(client, hr_headers):
    p = new_person()
    at(9, 0)
    h = sign_in(client, p)
    leave(client, h, hr_headers, "Morning Half", leave_type="Half Day Leave")
    task = assign(client, hr_headers, p, target=None)
    at(13, 0)
    s = in_ok(client, h)                                          # expected 1 PM: not late
    assert s["late_minutes"] == 0 and s["work_period"] == "Second Half"
    at(14, 5)
    state = client.get("/api/hourly-updates/today", headers=h).json()
    assert all(x["status"] == "Not Applicable" for x in state["slots"][:3])
    assert hourly(client, h, 0, task["id"]).status_code == 409   # leave period
    noon = report(client, h, "Noon")
    assert noon.status_code == 403
    assert noon.json()["detail"] == "Noon Report is not required because you are on approved Morning Half Leave."
    assert hourly(client, h, 3, task["id"]).status_code == 201   # 1-2 PM works
    assert client.get("/api/reports/logout-check", headers=h).json()["noon_submitted"] is False
    assert check_out(client, h).status_code == 409               # EOD pending
    at(18, 0)
    assert with_attachment(client, h, "EOD").json()["status"] == "Submitted"
    assert check_out(client, h).status_code == 200


def test_afternoon_half_leave_noon_is_closing_report_with_attachment(client, hr_headers):
    p = new_person(intern=True)
    at(9, 50)
    h = sign_in(client, p)
    leave(client, h, hr_headers, "Afternoon Half", leave_type="Half Day Leave")
    task = assign(client, hr_headers, p, target=None)
    in_ok(client, h)
    at(13, 1)
    eod = report(client, h, "EOD", submit=False)
    assert eod.status_code == 403
    assert eod.json()["detail"] == "EOD Report is not required because you are on approved Afternoon Half Leave."
    state = client.get("/api/hourly-updates/today", headers=h).json()
    assert all(x["status"] == "Not Applicable" for x in state["slots"][3:])
    assert hourly(client, h, 4, task["id"]).status_code == 409
    assert hourly(client, h, 2, task["id"]).status_code == 201   # 12-1 PM still due
    check = client.get("/api/reports/logout-check", headers=h).json()
    assert check["noon_attachment_required"] is True and check["noon_submitted"] is False
    no_file = report(client, h, "Noon")
    assert no_file.status_code == 422 and "attachment" in no_file.json()["detail"]
    assert check_out(client, h).status_code == 409
    assert with_attachment(client, h, "Noon").json()["status"] == "Submitted"
    out = check_out(client, h)
    assert out.status_code == 200, out.text
    assert last_session(p["user_id"]).extra_work_minutes == 1     # vs 1:00 PM expected logout


def test_full_day_leave_blocks_everything(client, hr_headers):
    p = new_person()
    at(9, 0, date(2026, 9, 14))
    h = sign_in(client, p)
    leave(client, h, hr_headers, "Full Day", leave_type="Sick Leave")
    task = assign(client, hr_headers, p, target=None)
    at(11, 0)
    r = check_in(client, h)
    assert r.status_code == 409 and r.json()["code"] == "ON_LEAVE"
    for rtype in ("Noon", "EOD"):
        rep = report(client, h, rtype, submit=False)
        assert rep.status_code == 403
        assert rep.json()["detail"] == "You are on approved Full Day Leave. Daily reports are not required."
    state = client.get("/api/hourly-updates/today", headers=h).json()
    assert all(x["status"] == "Not Applicable" for x in state["slots"])
    assert hourly(client, h, 0, task["id"]).status_code == 409
    notes = [n for n in client.get("/api/notifications", headers=h).json()["items"]
             if n["type"] == "Hourly Update Due"]
    assert notes == []


def test_leave_approved_after_check_in_applies_immediately(client, hr_headers):
    p = new_person()
    at(9, 50, date(2026, 9, 17))
    h = sign_in(client, p)
    in_ok(client, h)
    leave(client, h, hr_headers, "Afternoon Half", leave_type="Half Day Leave", day=date(2026, 9, 17))
    at(13, 5, date(2026, 9, 17))
    assert report(client, h, "EOD", day=date(2026, 9, 17), submit=False).status_code == 403
    assert with_attachment(client, h, "Noon", day=date(2026, 9, 17)).json()["status"] == "Submitted"
    assert check_out(client, h).status_code == 200
    assert last_session(p["user_id"]).expected_logout_time == time(13, 0)


def test_half_day_leave_validation_and_two_halves_same_day(client, hr_headers):
    p = new_person()
    at(9, 0)
    h = sign_in(client, p)
    bad = client.post("/api/leave-requests", json={
        "leave_type": "Half Day Leave", "from_date": "2026-09-21", "to_date": "2026-09-21",
        "reason": "Doctor visit"}, headers=h)
    assert bad.status_code == 422
    leave(client, h, hr_headers, "Morning Half", "Half Day Leave", day=date(2026, 9, 21))
    a = leave(client, h, hr_headers, "Afternoon Half", "Unpaid Leave", day=date(2026, 9, 21))
    assert a["is_paid"] is False
    at(10, 0, day=date(2026, 9, 21))
    assert client.get("/api/attendance/today", headers=h).json()["leave_period"] == "Full Day"


# ------------------------------------------------------------------ privacy
def test_privacy_of_tasks_updates_selfies_and_reports(client, hr_headers):
    a, b = new_person(), new_person(intern=True)
    at(9, 30)
    ha, hb = sign_in(client, a), sign_in(client, b)
    in_ok(client, ha)
    ta = assign(client, hr_headers, a, target=None)
    assert client.get(f"/api/tasks/{ta['id']}", headers=hb).status_code == 403
    assert client.post("/api/tasks", json={"employee_ids": [b["id"]], "title": "Self task"}, headers=hb).status_code == 403
    assert all(t["employee_id"] == b["id"] for t in client.get("/api/tasks", params={"employee_id": a["id"]}, headers=hb).json()["items"])
    sa = last_session(a["user_id"])
    assert client.get(f"/api/attendance/sessions/{sa.id}/selfie/check-in", headers=hb).status_code == 403
    assert client.get(f"/api/attendance/sessions/{sa.id}/selfie/check-in", headers=ha).status_code == 200
    assert client.get(f"/api/attendance/sessions/{sa.id}/selfie/check-in", headers=hr_headers).status_code == 200
    at(11, 5)
    u = hourly(client, ha, 1, ta["id"]).json()
    assert client.post(f"/api/hourly-updates/{u['id']}/attachments",
                       files={"file": ("p.png", MINIMAL_PNG, "image/png")}, headers=hb).status_code == 403
    assert all(x["employee_id"] == b["id"] for x in client.get("/api/hourly-updates", params={"employee_id": a["id"]}, headers=hb).json()["items"])
    assert all(x["employee_id"] == b["id"] for x in client.get("/api/attendance/sessions", headers=hb).json()["items"])
    for path in ("/api/attendance/monthly-report", "/api/attendance/monthly-pdf", "/api/attendance/months"):
        assert client.get(path, params={"employee_id": a["id"]}, headers=hb).status_code == 403
    assert client.get("/api/attendance/hr/today", headers=ha).status_code == 403
    mon = client.get("/api/attendance/hr/today", params={"date": DAY.isoformat()}, headers=hr_headers).json()
    row = next(r for r in mon["items"] if r["employee_id"] == a["id"])
    assert row["session"]["check_in_location"] and row["tasks"][0]["title"] == ta["title"]
    assert row["hourly_submitted"] == 1


# ------------------------------------------------------------------ monthly report
def test_monthly_report_reflects_database_values(client, hr_headers):
    p = new_person()
    at(10, 20)
    h = sign_in(client, p)
    in_ok(client, h, reason="Traffic jam")
    at(13, 5); report(client, h, "Noon")
    at(18, 1); with_attachment(client, h, "EOD")
    at(19, 30); assert check_out(client, h).status_code == 200
    at(9, 0, NEXT)
    lv = leave(client, h, hr_headers, "Morning Half", "Half Day Leave", day=NEXT)
    at(13, 0, NEXT); in_ok(client, h)
    at(18, 0, NEXT); with_attachment(client, h, "EOD", day=NEXT)
    at(18, 10, NEXT); assert check_out(client, h).status_code == 200
    leave(client, h, hr_headers, "Full Day", "Unpaid Leave", day=date(2026, 9, 18))
    sal = client.post("/api/salaries", json={
        "employee_id": p["id"], "period_year": 2026, "period_month": 9, "working_days": 22,
        "components": [{"component_type": "earning", "name": "Basic", "amount": 22000},
                       {"component_type": "deduction", "name": "PT", "amount": 200}]}, headers=hr_headers)
    assert sal.status_code == 201, sal.text
    at(12, 0, date(2026, 9, 30))
    data = client.get("/api/attendance/monthly-report", params={"month": "2026-09", "employee_id": p["id"]},
                      headers=hr_headers).json()
    days = {d["date"]: d for d in data["days"]}
    assert days["2026-09-15"]["late_minutes"] == 20 and days["2026-09-15"]["extra_minutes"] == 90
    assert days["2026-09-16"]["leave_status"] == "Morning Half Leave" and days["2026-09-16"]["noon_report"] == "Not Required"
    assert days["2026-09-18"]["attendance"] == "Full Day Leave"
    assert data["attendance"]["leave_days"] == 1.5 and data["hours"]["extra_minutes"] == 100
    s = data["salary"]
    assert s["estimated_payable"] == 21000.0 and s["estimated_net_payable"] == 20800.0
    assert any(l["id"] == lv["id"] for l in data["leave"]["items"])
    pdf = client.get("/api/attendance/monthly-pdf", params={"month": "2026-09", "employee_id": p["id"]}, headers=hr_headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


# ------------------------------------------------------------------ people / photo / notifications
def test_hr_creates_employee_and_intern_with_type(client, hr_headers):
    deps = {d["name"]: d["id"] for d in client.get("/api/departments", headers=hr_headers).json()}
    bgs = {b["name"]: b["id"] for b in client.get("/api/internship-backgrounds", headers=hr_headers).json()}
    tag = uuid.uuid4().hex[:6]
    base = {"designation": "Trainee", "joining_date": "2026-09-01", "send_account_email": False}
    wrong = client.post("/api/employees", json=dict(base, full_name="Wrong Type", email=f"w{tag}@t.com",
                        employee_type="Intern", department_id=deps["Marketing"]), headers=hr_headers)
    assert wrong.status_code == 422
    intern = client.post("/api/employees", json=dict(base, full_name="New Intern", email=f"i{tag}@t.com",
                         employee_type="Intern", department_id=deps["Internship"],
                         internship_background_id=bgs["Cyber Security"]), headers=hr_headers)
    assert intern.status_code == 201, intern.text
    assert intern.json()["employee"]["is_intern"] is True
    assert intern.json()["employee"]["internship_background"] == "Cyber Security"
    assert intern.json()["employee"]["employee_code"].startswith("RG-")
    emp = client.post("/api/employees", json=dict(base, full_name="New Employee", email=f"e{tag}@t.com",
                      employee_type="Employee", department_id=deps["Marketing"]), headers=hr_headers)
    assert emp.status_code == 201 and emp.json()["employee"]["is_intern"] is False


def test_photo_needs_hr_approval_before_profile_and_id_card(client, hr_headers):
    p = new_person()
    at(9, 30)
    h = sign_in(client, p)
    up = client.post("/api/employees/me/photo", files={"file": ("me.png", MINIMAL_PNG, "image/png")}, headers=h)
    assert up.json()["photo_status"] == "Pending" and up.json()["photo_path"] is None
    docs = client.get(f"/api/documents/employee/{p['id']}", headers=hr_headers).json()
    photo = next(i for i in docs["items"] if i["code"] == "PHOTO")
    assert client.post(f"/api/documents/{photo['document_id']}/verify", json={}, headers=hr_headers).status_code == 200
    me = client.get("/api/employees/me", headers=h).json()
    assert me["photo_status"] == "Verified" and me["photo_path"]
    assert client.get("/api/employees/me/id-card", headers=h).json()["photo_path"] == me["photo_path"]


def test_notifications_can_be_deleted_only_after_read_and_only_own(client, hr_headers):
    a, b = new_person(), new_person()
    at(9, 30)
    ha, hb = sign_in(client, a), sign_in(client, b)
    nid = client.get("/api/notifications", headers=ha).json()["items"][0]["id"]
    assert client.delete(f"/api/notifications/{nid}", headers=ha).status_code == 409
    assert client.delete(f"/api/notifications/{nid}", headers=hb).status_code == 404
    client.post(f"/api/notifications/{nid}/read", json={}, headers=ha)
    assert client.delete(f"/api/notifications/{nid}", headers=ha).status_code == 200
