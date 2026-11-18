"""Admin / HR / Manager / Employee / Intern hierarchy and API security.

Builds an isolated organisation:

    Admin
     |- HR A ----- Manager A ---- Employee A1, Intern A1
     |              (+ Employee A2 reporting to HR A directly)
     |- HR B ----- Manager B ---- Employee B1, Intern B1

and calls the API directly as each role (never through the UI) to prove the
hierarchy is enforced by the backend in every module.
"""
import uuid
from datetime import date, datetime, time

import pytest

from app.core.constants import ApprovalStage, RoleName
from app.database.database import SessionLocal
from app.models.daily_report import DailyReport
from app.models.employee import Employee
from app.models.employee_document import EmployeeDocument
from app.models.document_type import DocumentType
from app.models.notification import Notification
from app.services import hierarchy_service
from app.utils import clock
from app.utils.timeutil import utcnow
from tests.conftest import EMP_PASSWORD, MINIMAL_PDF, SUITE_NOW, _make_user, selfie_data_url

LOC = {"latitude": 28.6304, "longitude": 77.2773, "accuracy": 15}
WORKDAY = date(2026, 9, 15)  # Tuesday


def _assign(person, **kw):
    db = SessionLocal()
    try:
        e = db.query(Employee).filter(Employee.id == person["id"]).first()
        hierarchy_service.apply_assignment(db, None, e, notify=False, **kw)
        db.commit()
    finally:
        db.close()


def _login(client, email, password=EMP_PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def org(client):
    tag = uuid.uuid4().hex[:5]
    mk = lambda dept, title, who, role=RoleName.EMPLOYEE, bg=None: _make_user(  # noqa: E731
        dept, title, f"{who}.{tag}@orgtest.com", f"{who.replace('_', ' ').title()} {tag}", role, EMP_PASSWORD, bg)
    o = {
        "hr_a": mk("HR", "HR Executive", "hr_a", RoleName.HR_ADMIN),
        "hr_b": mk("Senior HR", "HR Lead", "hr_b", RoleName.HR_ADMIN),
        "mgr_a": mk("Managers", "Project Manager", "mgr_a"),
        "mgr_b": mk("Managers", "Operations Manager", "mgr_b"),
        "emp_a1": mk("Digital Marketing", "SEO Specialist", "emp_a1"),
        "emp_a2": mk("Teaching", "Trainer", "emp_a2"),
        "int_a1": mk("Internship", "Trainee", "int_a1", bg="Data Science"),
        "emp_b1": mk("Marketing", "Sales Associate", "emp_b1"),
        "int_b1": mk("Internship", "Trainee", "int_b1", bg="Cyber Security"),
    }
    _assign(o["mgr_a"], role=RoleName.MANAGER, reporting_hr_id=o["hr_a"]["id"])
    _assign(o["mgr_b"], role=RoleName.MANAGER, reporting_hr_id=o["hr_b"]["id"])
    for k in ("emp_a1", "int_a1"):
        _assign(o[k], reporting_manager_id=o["mgr_a"]["id"])
    for k in ("emp_b1", "int_b1"):
        _assign(o[k], reporting_manager_id=o["mgr_b"]["id"])
    _assign(o["emp_a2"], reporting_hr_id=o["hr_a"]["id"])

    db = SessionLocal()
    try:
        from app.api.admin import create_admin_account
        user, _ = create_admin_account(db, f"admin.{tag}@orgtest.com", "Org Admin", password="AdminPass@2026")
        user.must_change_password = False
        db.commit()
    finally:
        db.close()
    o["admin"] = {"email": f"admin.{tag}@orgtest.com", "password": "AdminPass@2026"}

    for k, v in o.items():
        data = _login(client, v["email"], v.get("password", EMP_PASSWORD))
        v["home"] = data["home"]
        v["user"] = data["user"]
        v["h"] = _h(data["access_token"])
    return o


@pytest.fixture(autouse=True)
def _restore_clock():
    yield
    clock.set_fixed_now(SUITE_NOW)


def at(hh, mm=0, day=WORKDAY):
    clock.set_fixed_now(datetime.combine(day, time(hh, mm)))


def ids(response):
    return {i["id"] for i in response.json()["items"]}


# ======================================================== login / routing
def test_role_based_login_routing(org):
    assert org["admin"]["home"] == "/admin/dashboard.html"
    assert org["hr_a"]["home"] == "/hr/dashboard.html"
    assert org["mgr_a"]["home"] == "/manager/dashboard.html"
    assert org["emp_a1"]["home"] == "/employee/dashboard.html"
    assert org["int_a1"]["home"] == "/intern/dashboard.html"
    assert org["admin"]["user"]["has_employee_record"] is False
    assert org["admin"]["user"]["portal"] == "admin"
    assert org["mgr_a"]["user"]["role"] == "MANAGER"
    assert org["emp_a1"]["user"]["reporting_manager"].startswith("Mgr A")


# ======================================================== admin
def test_admin_has_no_check_in(client, org):
    at(10, 0)
    st = client.get("/api/attendance/status", headers=org["admin"]["h"]).json()
    assert st["applicable"] is False
    body = dict(LOC, selfie_data=selfie_data_url())
    assert client.post("/api/attendance/check-in", json=body, headers=org["admin"]["h"]).status_code == 403
    assert client.get("/api/hourly-updates/today", headers=org["admin"]["h"]).status_code == 404


def test_admin_sees_everyone_and_filters(client, org):
    h = org["admin"]["h"]
    for k in org:
        if k != "admin":
            assert client.get(f"/api/employees/{org[k]['id']}", headers=h).status_code == 200, k
    hrs = client.get("/api/admin/hr", headers=h).json()["items"]
    assert {org["hr_a"]["id"], org["hr_b"]["id"]} <= {x["id"] for x in hrs}
    mgrs = ids(client.get("/api/employees", params={"person_type": "Manager", "page_size": 100}, headers=h))
    assert {org["mgr_a"]["id"], org["mgr_b"]["id"]} <= mgrs
    interns = ids(client.get("/api/employees", params={"person_type": "Intern", "page_size": 100}, headers=h))
    assert {org["int_a1"]["id"], org["int_b1"]["id"]} <= interns and org["emp_a1"]["id"] not in interns
    dept = org["emp_b1"]["department_id"]
    in_dept = client.get("/api/employees", params={"department_id": dept, "page_size": 100}, headers=h).json()["items"]
    assert all(i["department_id"] == dept for i in in_dept) and org["emp_b1"]["id"] in {i["id"] for i in in_dept}
    team = ids(client.get("/api/employees", params={"reporting_hr_id": org["hr_b"]["id"], "page_size": 100}, headers=h))
    assert team == {org["mgr_b"]["id"], org["emp_b1"]["id"], org["int_b1"]["id"]}


def test_admin_hr_overview_and_dashboard(client, org):
    h = org["admin"]["h"]
    ov = client.get(f"/api/admin/people/{org['hr_a']['id']}/overview", headers=h)
    assert ov.status_code == 200, ov.text
    data = ov.json()
    assert data["type"] == "HR"
    assert [m["id"] for m in data["managers"]] == [org["mgr_a"]["id"]]
    assert {t["id"] for t in data["managers"][0]["team"]} == {org["emp_a1"]["id"], org["int_a1"]["id"]}
    assert {t["id"] for t in data["direct_team"]} == {org["emp_a2"]["id"]}
    for key in ("attendance", "reports", "hourly_updates", "tasks", "leave", "documents", "salary"):
        assert key in data
    dash = client.get("/api/admin/dashboard", headers=h).json()
    assert dash["scope"] == "organisation" and dash["hr_monitoring"]
    tree = client.get("/api/hierarchy/tree", headers=h).json()["items"]
    assert any(n["id"] == org["hr_a"]["id"] for n in tree)


def test_admin_endpoints_are_admin_only(client, org):
    for who in ("hr_a", "mgr_a", "emp_a1", "int_a1"):
        assert client.get("/api/admin/dashboard", headers=org[who]["h"]).status_code == 403
        assert client.get(f"/api/admin/people/{org['hr_a']['id']}/overview", headers=org[who]["h"]).status_code == 403


def test_admin_profile(client, org):
    h = org["admin"]["h"]
    r = client.put("/api/admin/profile", json={"full_name": "Org Admin Updated", "phone": "+91 9000000000"}, headers=h)
    assert r.status_code == 200 and r.json()["full_name"] == "Org Admin Updated"
    assert client.get("/api/auth/me", headers=h).json()["full_name"] == "Org Admin Updated"


# ======================================================== HR
def test_hr_checks_in_with_employee_flow(client, org):
    at(10, 30)
    h = org["hr_a"]["h"]
    body = dict(LOC, selfie_data=selfie_data_url())
    r = client.post("/api/attendance/check-in", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["session"]["late_minutes"] == 0       # HR late-login exception kept
    mine = client.get("/api/attendance/sessions", params={"employee_id": org["hr_a"]["id"]}, headers=h).json()["items"]
    assert mine and mine[0]["employee_id"] == org["hr_a"]["id"]
    assert client.get("/api/hourly-updates/today", headers=h).status_code == 200


def test_hr_sees_own_hierarchy_only(client, org):
    h = org["hr_a"]["h"]
    visible = ids(client.get("/api/employees", params={"page_size": 100}, headers=h))
    assert {org[k]["id"] for k in ("hr_a", "mgr_a", "emp_a1", "int_a1", "emp_a2")} <= visible
    assert not ({org[k]["id"] for k in ("hr_b", "mgr_b", "emp_b1", "int_b1")} & visible)
    assert client.get(f"/api/employees/{org['mgr_a']['id']}", headers=h).status_code == 200
    for k in ("hr_b", "mgr_b", "emp_b1", "int_b1"):
        assert client.get(f"/api/employees/{org[k]['id']}", headers=h).status_code == 403, k
        assert client.get(f"/api/attendance/employee/{org[k]['id']}", headers=h).status_code == 403
        assert client.get(f"/api/documents/employee/{org[k]['id']}", headers=h).status_code == 403
    tree = client.get("/api/hierarchy/tree", headers=h).json()["items"]
    assert org["hr_b"]["id"] not in {n["id"] for n in tree}


def test_hr_cannot_manage_other_hr_hierarchy(client, org):
    h = org["hr_a"]["h"]
    assert client.put(f"/api/employees/{org['emp_b1']['id']}", json={"designation": "X Y"}, headers=h).status_code == 403
    assert client.put(f"/api/hierarchy/employees/{org['emp_b1']['id']}",
                      json={"reporting_hr_id": org["hr_a"]["user"]["employee_id"]}, headers=h).status_code == 403
    assert client.put(f"/api/hierarchy/employees/{org['emp_a1']['id']}", json={"role": "HR_ADMIN"},
                      headers=h).status_code == 403
    assert client.post("/api/tasks", json={"employee_ids": [org["emp_b1"]["id"]], "title": "Not mine"},
                       headers=h).status_code == 403


# ======================================================== manager
def test_manager_dashboard_routing_and_check_in(client, org):
    at(10, 5)
    h = org["mgr_a"]["h"]
    body = dict(LOC, selfie_data=selfie_data_url(), late_login_reason="Traffic")
    r = client.post("/api/attendance/check-in", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["session"]["late_minutes"] == 5       # managers follow the late-login rule


def test_manager_sees_own_team_only(client, org):
    h = org["mgr_a"]["h"]
    team = ids(client.get("/api/hierarchy/team", headers=h))
    assert team == {org["emp_a1"]["id"], org["int_a1"]["id"]}
    listed = ids(client.get("/api/employees", params={"page_size": 100, "include_self": "false"}, headers=h))
    assert listed == team
    detail = client.get(f"/api/employees/{org['emp_a1']['id']}", headers=h).json()
    assert detail["uan_number"] is None and detail["salary_status"] is None   # no salary/UAN for managers
    for k in ("emp_b1", "int_b1", "mgr_b", "hr_a", "emp_a2"):
        assert client.get(f"/api/employees/{org[k]['id']}", headers=h).status_code == 403, k
        assert client.get(f"/api/attendance/monthly-report", params={"employee_id": org[k]["id"]}, headers=h).status_code == 403
    monitor = client.get("/api/attendance/hr/today", headers=h).json()["items"]
    assert {r["employee_id"] for r in monitor} == team
    month = client.get("/api/attendance/monthly-report", params={"employee_id": org["emp_a1"]["id"]}, headers=h).json()
    assert month["salary"] is None


def test_manager_cannot_reach_hr_only_actions(client, org):
    h = org["mgr_a"]["h"]
    assert client.get("/api/documents", headers=h).status_code == 403
    assert client.get("/api/uan", headers=h).status_code == 403
    assert client.post("/api/employees", json={}, headers=h).status_code in (403, 422)
    assert client.get("/api/dashboard/hr", headers=h).status_code == 403
    assert client.get("/api/excel/template", headers=h).status_code == 403


# ======================================================== employees / interns
def test_employee_and_intern_isolation(client, org):
    for me, other in (("emp_a1", "emp_b1"), ("int_a1", "emp_a1"), ("emp_b1", "int_b1"), ("int_b1", "emp_b1")):
        h = org[me]["h"]
        assert client.get(f"/api/employees/{org[other]['id']}", headers=h).status_code == 403
        assert client.get(f"/api/attendance/employee/{org[other]['id']}", headers=h).status_code == 403
        assert client.get(f"/api/documents/employee/{org[other]['id']}", headers=h).status_code == 403
        assert client.get("/api/employees", headers=h).status_code == 403
        assert client.get(f"/api/employees/{org[me]['id']}", headers=h).status_code == 200
    items = client.get("/api/tasks", headers=org["emp_a1"]["h"]).json()["items"]
    assert all(t["employee_id"] == org["emp_a1"]["id"] for t in items)


def test_employee_flow_check_in_out_and_reports(client, org):
    at(9, 58)
    h = org["emp_a1"]["h"]
    r = client.post("/api/attendance/check-in", json=dict(LOC, selfie_data=selfie_data_url()), headers=h)
    assert r.status_code == 200, r.text
    reports = client.get("/api/reports", params={"mine": "true"}, headers=h)
    assert reports.status_code == 200


# ======================================================== leave flow
def _leave(client, h, day):
    r = client.post("/api/leave-requests", json={
        "leave_type": "Casual Leave", "from_date": day, "to_date": day,
        "leave_period": "Full Day", "reason": "Family function"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_leave_employee_to_manager_to_hr(client, org):
    row = _leave(client, org["emp_a1"]["h"], "2026-12-01")
    assert row["approval_stage"] == ApprovalStage.MANAGER
    lid = row["id"]
    # Wrong manager / wrong HR / the employee: denied
    assert client.patch(f"/api/leave-requests/{lid}", json={"status": "Approved"}, headers=org["mgr_b"]["h"]).status_code == 403
    assert client.patch(f"/api/leave-requests/{lid}", json={"status": "Approved"}, headers=org["hr_b"]["h"]).status_code == 403
    assert client.patch(f"/api/leave-requests/{lid}", json={"status": "Approved"}, headers=org["emp_a1"]["h"]).status_code == 403
    # Manager sees it waiting and forwards it
    waiting = client.get("/api/leave-requests", params={"awaiting_me": "true"}, headers=org["mgr_a"]["h"]).json()["items"]
    assert lid in {i["id"] for i in waiting} and all(i["can_act"] for i in waiting)
    r = client.patch(f"/api/leave-requests/{lid}", json={"status": "Approved", "hr_remarks": "OK from me"},
                     headers=org["mgr_a"]["h"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Pending" and r.json()["approval_stage"] == ApprovalStage.HR
    assert r.json()["manager_status"] == "Approved"
    # Manager cannot act twice
    assert client.patch(f"/api/leave-requests/{lid}", json={"status": "Approved"}, headers=org["mgr_a"]["h"]).status_code == 403
    # HR of that hierarchy finalises
    r = client.patch(f"/api/leave-requests/{lid}", json={"status": "Approved"}, headers=org["hr_a"]["h"])
    assert r.status_code == 200 and r.json()["status"] == "Approved" and r.json()["approval_stage"] == ApprovalStage.CLOSED
    # Notifications followed the hierarchy
    db = SessionLocal()
    try:
        mgr_note = db.query(Notification).filter(Notification.user_id == org["mgr_a"]["user_id"],
                                                 Notification.related_id == lid).count()
        hr_note = db.query(Notification).filter(Notification.user_id == org["hr_a"]["user_id"],
                                                Notification.related_id == lid).count()
        other = db.query(Notification).filter(Notification.user_id.in_([org["hr_b"]["user_id"], org["mgr_b"]["user_id"]]),
                                              Notification.related_id == lid, Notification.related_entity == "leave_request").count()
    finally:
        db.close()
    assert mgr_note >= 1 and hr_note >= 1 and other == 0


def test_leave_manager_rejection_closes(client, org):
    row = _leave(client, org["int_a1"]["h"], "2026-12-02")
    r = client.patch(f"/api/leave-requests/{row['id']}", json={"status": "Rejected", "hr_remarks": "Deadline week"},
                     headers=org["mgr_a"]["h"])
    assert r.status_code == 200 and r.json()["status"] == "Rejected"


def test_leave_manager_to_hr_and_hr_to_admin(client, org):
    mrow = _leave(client, org["mgr_a"]["h"], "2026-12-03")
    assert mrow["approval_stage"] == ApprovalStage.HR
    assert client.patch(f"/api/leave-requests/{mrow['id']}", json={"status": "Approved"}, headers=org["mgr_a"]["h"]).status_code == 403
    assert client.patch(f"/api/leave-requests/{mrow['id']}", json={"status": "Approved"}, headers=org["hr_b"]["h"]).status_code == 403
    assert client.patch(f"/api/leave-requests/{mrow['id']}", json={"status": "Approved"}, headers=org["hr_a"]["h"]).json()["status"] == "Approved"

    hrow = _leave(client, org["hr_a"]["h"], "2026-12-04")
    assert hrow["approval_stage"] == ApprovalStage.ADMIN
    assert client.patch(f"/api/leave-requests/{hrow['id']}", json={"status": "Approved"}, headers=org["hr_a"]["h"]).status_code == 403
    assert client.patch(f"/api/leave-requests/{hrow['id']}", json={"status": "Approved"}, headers=org["hr_b"]["h"]).status_code == 403
    listed = ids(client.get("/api/leave-requests", params={"stage": "Admin", "page_size": 100}, headers=org["admin"]["h"]))
    assert hrow["id"] in listed
    r = client.patch(f"/api/leave-requests/{hrow['id']}", json={"status": "Approved"}, headers=org["admin"]["h"])
    assert r.status_code == 200 and r.json()["status"] == "Approved"
    # HR B never sees HR A's leave or HR A's team leave
    seen_b = ids(client.get("/api/leave-requests", params={"page_size": 100}, headers=org["hr_b"]["h"]))
    assert hrow["id"] not in seen_b and mrow["id"] not in seen_b


# ======================================================== reports
def _report_for(person, rtype="EOD", day=WORKDAY):
    db = SessionLocal()
    try:
        r = DailyReport(employee_id=person["id"], report_date=day, report_type=rtype, status="Submitted",
                        work_summary="Did the work", submitted_at=utcnow())
        db.add(r)
        db.commit()
        return r.id
    finally:
        db.close()


def test_report_review_follows_hierarchy(client, org):
    rid = _report_for(org["emp_a1"])
    for who in ("mgr_b", "hr_b", "emp_a1", "int_a1"):
        assert client.post(f"/api/reports/{rid}/review", json={"review_notes": "x"}, headers=org[who]["h"]).status_code == 403, who
    assert client.get(f"/api/reports/{rid}", headers=org["mgr_b"]["h"]).status_code == 403
    listed = ids(client.get("/api/reports", params={"page_size": 200}, headers=org["mgr_a"]["h"]))
    assert rid in listed
    r = client.post(f"/api/reports/{rid}/review", json={"review_notes": "Good"}, headers=org["mgr_a"]["h"])
    assert r.status_code == 200 and r.json()["status"] == "Reviewed"
    # Manager report -> HR; HR report -> Admin
    mid = _report_for(org["mgr_a"], "Noon")
    assert client.post(f"/api/reports/{mid}/review", json={}, headers=org["mgr_a"]["h"]).status_code == 403
    assert client.post(f"/api/reports/{mid}/review", json={}, headers=org["hr_a"]["h"]).status_code == 200
    hid = _report_for(org["hr_a"], "Noon")
    assert client.post(f"/api/reports/{hid}/review", json={}, headers=org["hr_a"]["h"]).status_code == 403
    assert client.post(f"/api/reports/{hid}/review", json={}, headers=org["hr_b"]["h"]).status_code == 403
    assert client.post(f"/api/reports/{hid}/review", json={}, headers=org["admin"]["h"]).status_code == 200
    admin_view = ids(client.get("/api/reports", params={"report_type": "Noon", "page_size": 200}, headers=org["admin"]["h"]))
    assert {mid, hid} <= admin_view


# ======================================================== tasks
def test_task_flow_admin_hr_manager_division(client, org):
    r = client.post("/api/tasks", json={"employee_ids": [org["hr_a"]["id"]], "title": "Quarterly hiring plan"},
                    headers=org["admin"]["h"])
    assert r.status_code == 201, r.text
    r = client.post("/api/tasks", json={"employee_ids": [org["mgr_a"]["id"]], "title": "Launch campaign",
                                        "target": 3, "unit": "posts"}, headers=org["hr_a"]["h"])
    assert r.status_code == 201, r.text
    parent = r.json()["items"][0]["id"]
    d = client.post(f"/api/tasks/{parent}/divide", json={"parts": [
        {"employee_id": org["emp_a1"]["id"], "title": "Write posts", "target": 2},
        {"employee_id": org["int_a1"]["id"], "title": "Design creatives", "target": 1},
    ]}, headers=org["mgr_a"]["h"])
    assert d.status_code == 201, d.text
    subs = d.json()["items"]
    assert {s["employee_id"] for s in subs} == {org["emp_a1"]["id"], org["int_a1"]["id"]}
    assert all(s["parent_task_id"] == parent for s in subs)
    # Manager B can't divide Manager A's task; Manager A can't give work outside the team or upwards
    assert client.post(f"/api/tasks/{parent}/divide", json={"parts": [{"employee_id": org["emp_b1"]["id"]}]},
                       headers=org["mgr_b"]["h"]).status_code == 403
    assert client.post(f"/api/tasks/{parent}/divide", json={"parts": [{"employee_id": org["emp_b1"]["id"]}]},
                       headers=org["mgr_a"]["h"]).status_code == 403
    assert client.post("/api/tasks", json={"employee_ids": [org["hr_a"]["id"]], "title": "Upwards"},
                       headers=org["mgr_a"]["h"]).status_code == 403
    assert client.post("/api/tasks", json={"employee_ids": [org["emp_a2"]["id"]], "title": "Not my team"},
                       headers=org["mgr_a"]["h"]).status_code == 403
    assert client.post("/api/tasks", json={"employee_ids": [org["emp_a1"]["id"]], "title": "Peer task"},
                       headers=org["emp_a2"]["h"]).status_code == 403
    # Monitoring: HR B never sees these tasks
    seen = {t["id"] for t in client.get("/api/tasks", headers=org["hr_b"]["h"]).json()["items"]}
    assert parent not in seen and not ({s["id"] for s in subs} & seen)
    dept = org["emp_a1"]["department_id"]
    by_dept = client.get("/api/tasks", params={"department_id": dept}, headers=org["admin"]["h"]).json()["items"]
    assert all(t["department"] for t in by_dept) and any(t["employee_id"] == org["emp_a1"]["id"] for t in by_dept)


# ======================================================== documents
def _doc_for(person):
    db = SessionLocal()
    try:
        t = db.query(DocumentType).filter(DocumentType.code == "AADHAAR").first()
        d = db.query(EmployeeDocument).filter_by(employee_id=person["id"], document_type_id=t.id).first()
        if d is None:
            d = EmployeeDocument(employee_id=person["id"], document_type_id=t.id, status="Pending")
            db.add(d)
            db.commit()
        return d.id
    finally:
        db.close()


def test_documents_follow_hierarchy(client, org):
    up = client.post("/api/documents/upload", data={"document_type_id": 2},
                     files={"file": ("aadhaar.pdf", MINIMAL_PDF, "application/pdf")}, headers=org["emp_a1"]["h"])
    assert up.status_code == 201, up.text
    doc_a = up.json()["document_id"]
    doc_b = _doc_for(org["emp_b1"])
    # Manager: status yes, files and verification no
    assert client.get(f"/api/documents/employee/{org['emp_a1']['id']}", headers=org["mgr_a"]["h"]).status_code == 200
    assert client.get(f"/api/documents/{doc_a}/download", headers=org["mgr_a"]["h"]).status_code == 403
    assert client.post(f"/api/documents/{doc_a}/verify", json={}, headers=org["mgr_a"]["h"]).status_code == 403
    # HR B can't, HR A can
    assert client.post(f"/api/documents/{doc_a}/verify", json={}, headers=org["hr_b"]["h"]).status_code == 403
    assert client.post(f"/api/documents/{doc_a}/verify", json={}, headers=org["hr_a"]["h"]).status_code == 200
    queue = {d["document_id"] for d in client.get("/api/documents", params={"page_size": 200}, headers=org["hr_a"]["h"]).json()["items"]}
    assert doc_b not in queue
    admin_queue = {d["document_id"] for d in client.get("/api/documents", params={"page_size": 200, "employee_id": org["emp_b1"]["id"]},
                                                       headers=org["admin"]["h"]).json()["items"]}
    assert doc_b in admin_queue
    # HR's own documents are verified by the Admin
    own = _doc_for(org["hr_a"])
    assert client.post(f"/api/documents/{own}/verify", json={}, headers=org["hr_a"]["h"]).status_code == 403
    assert client.post(f"/api/documents/{own}/verify", json={}, headers=org["admin"]["h"]).status_code in (200, 409, 422)


# ======================================================== salary
def _salary(client, h, person, month):
    return client.post("/api/salaries", json={
        "employee_id": person["id"], "period_year": 2026, "period_month": month, "working_days": 22,
        "components": [{"component_type": "earning", "name": "Basic", "amount": "30000"}]}, headers=h)


def test_salary_access(client, org):
    assert _salary(client, org["hr_a"]["h"], org["hr_a"], 7).status_code == 403      # not own
    r = _salary(client, org["admin"]["h"], org["hr_a"], 7)
    assert r.status_code == 201, r.text
    hr_salary = r.json()["id"]
    r = _salary(client, org["hr_a"]["h"], org["emp_a1"], 7)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert _salary(client, org["hr_b"]["h"], org["emp_a1"], 8).status_code == 403
    assert _salary(client, org["mgr_a"]["h"], org["emp_a1"], 8).status_code == 403
    assert client.get(f"/api/salaries/{sid}", headers=org["emp_a1"]["h"]).status_code == 200
    for who in ("mgr_a", "hr_b", "emp_b1", "int_a1"):
        assert client.get(f"/api/salaries/{sid}", headers=org[who]["h"]).status_code == 403, who
    assert client.get(f"/api/salaries/{hr_salary}", headers=org["hr_a"]["h"]).status_code == 200   # own: view
    assert client.put(f"/api/salaries/{hr_salary}", json={"remarks": "x"}, headers=org["hr_a"]["h"]).status_code == 403
    mgr_list = client.get("/api/salaries", headers=org["mgr_a"]["h"]).json()["items"]
    assert all(s["employee_id"] == org["mgr_a"]["id"] for s in mgr_list)
    admin_list = {s["id"] for s in client.get("/api/salaries", params={"page_size": 200}, headers=org["admin"]["h"]).json()["items"]}
    assert {sid, hr_salary} <= admin_list


# ======================================================== hierarchy management
def test_hierarchy_validation_and_cascade(client, org):
    h = org["admin"]["h"]
    # employee -> manager of another HR while naming HR A: rejected
    r = client.put(f"/api/hierarchy/employees/{org['emp_a2']['id']}",
                   json={"reporting_manager_id": org["mgr_b"]["id"], "reporting_hr_id": org["hr_a"]["id"]}, headers=h)
    assert r.status_code == 422 and "not to" in r.json()["detail"]
    # manager reporting to a manager: rejected
    r = client.put(f"/api/hierarchy/employees/{org['mgr_a']['id']}", json={"reporting_manager_id": org["mgr_b"]["id"]}, headers=h)
    assert r.status_code == 422
    # reporting to a non-manager: rejected
    r = client.put(f"/api/hierarchy/employees/{org['emp_a2']['id']}", json={"reporting_manager_id": org["emp_b1"]["id"]}, headers=h)
    assert r.status_code == 422
    # demoting a manager with a team: rejected
    r = client.put(f"/api/hierarchy/employees/{org['mgr_a']['id']}", json={"role": "EMPLOYEE"}, headers=h)
    assert r.status_code == 409
    # an intern can't be a manager
    r = client.put(f"/api/hierarchy/employees/{org['int_b1']['id']}", json={"role": "MANAGER"}, headers=h)
    assert r.status_code == 422


def test_moving_a_manager_moves_the_team(client, org):
    tag = uuid.uuid4().hex[:5]
    hr_c = _make_user("HR", "HR", f"hrc.{tag}@orgtest.com", f"HR C {tag}", RoleName.HR_ADMIN, EMP_PASSWORD)
    mgr = _make_user("Managers", "Lead", f"mgrc.{tag}@orgtest.com", f"Mgr C {tag}", RoleName.EMPLOYEE, EMP_PASSWORD)
    mem = _make_user("Marketing", "Exec", f"memc.{tag}@orgtest.com", f"Mem C {tag}", RoleName.EMPLOYEE, EMP_PASSWORD)
    h = org["admin"]["h"]
    assert client.put(f"/api/hierarchy/employees/{mgr['id']}", json={"role": "MANAGER", "reporting_hr_id": org["hr_a"]["id"]}, headers=h).status_code == 200
    assert client.put(f"/api/hierarchy/employees/{mem['id']}", json={"reporting_manager_id": mgr["id"]}, headers=h).status_code == 200
    assert client.get(f"/api/employees/{mem['id']}", headers=h).json()["reporting_hr_id"] == org["hr_a"]["id"]
    assert client.put(f"/api/hierarchy/employees/{mgr['id']}", json={"reporting_hr_id": hr_c["id"]}, headers=h).status_code == 200
    assert client.get(f"/api/employees/{mem['id']}", headers=h).json()["reporting_hr_id"] == hr_c["id"]
    assert client.get(f"/api/employees/{mem['id']}", headers=org["hr_a"]["h"]).status_code == 403


def test_hr_can_build_own_hierarchy(client, org):
    tag = uuid.uuid4().hex[:5]
    r = client.post("/api/employees", json={
        "full_name": f"New Hire {tag}", "email": f"new.{tag}@orgtest.com", "department_id": org["emp_a1"]["department_id"],
        "designation": "Executive", "joining_date": "2026-09-01", "send_account_email": False,
        "reporting_manager_id": org["mgr_a"]["id"]}, headers=org["hr_a"]["h"])
    assert r.status_code == 201, r.text
    e = r.json()["employee"]
    assert e["reporting_manager_id"] == org["mgr_a"]["id"] and e["reporting_hr_id"] == org["hr_a"]["id"]
    r = client.post("/api/employees", json={
        "full_name": f"Other {tag}", "email": f"other.{tag}@orgtest.com", "department_id": org["emp_a1"]["department_id"],
        "designation": "Executive", "joining_date": "2026-09-01", "send_account_email": False,
        "reporting_manager_id": org["mgr_b"]["id"]}, headers=org["hr_a"]["h"])
    assert r.status_code == 403
    r = client.post("/api/employees", json={
        "full_name": f"Boss {tag}", "email": f"boss.{tag}@orgtest.com", "department_id": org["emp_a1"]["department_id"],
        "designation": "HR", "joining_date": "2026-09-01", "send_account_email": False, "role": "HR_ADMIN"},
        headers=org["hr_a"]["h"])
    assert r.status_code == 403


def test_legacy_reporting_manager_hr_becomes_reporting_hr(client, org):
    tag = uuid.uuid4().hex[:5]
    r = client.post("/api/employees", json={
        "full_name": f"Legacy {tag}", "email": f"legacy.{tag}@orgtest.com", "department_id": org["emp_a1"]["department_id"],
        "designation": "Executive", "joining_date": "2026-09-01", "send_account_email": False,
        "reporting_manager_id": org["hr_b"]["id"]}, headers=org["admin"]["h"])
    assert r.status_code == 201, r.text
    e = r.json()["employee"]
    assert e["reporting_hr_id"] == org["hr_b"]["id"] and e["reporting_manager_id"] is None


def test_unassigned_pool_setting(client, org):
    tag = uuid.uuid4().hex[:5]
    loose = _make_user("Marketing", "Exec", f"loose.{tag}@orgtest.com", f"Loose {tag}", RoleName.EMPLOYEE, EMP_PASSWORD)
    assert client.get(f"/api/employees/{loose['id']}", headers=org["hr_a"]["h"]).status_code == 200
    assert client.put("/api/settings", json={"values": {"hr_sees_unassigned": False}}, headers=org["hr_a"]["h"]).status_code == 403
    assert client.put("/api/settings", json={"values": {"hr_sees_unassigned": False}}, headers=org["admin"]["h"]).status_code == 200
    try:
        assert client.get(f"/api/employees/{loose['id']}", headers=org["hr_a"]["h"]).status_code == 403
        assert client.get(f"/api/employees/{loose['id']}", headers=org["admin"]["h"]).status_code == 200
    finally:
        client.put("/api/settings", json={"values": {"hr_sees_unassigned": True}}, headers=org["admin"]["h"])


def test_denied_access_is_audited(client, org):
    client.get(f"/api/employees/{org['emp_b1']['id']}", headers=org["mgr_a"]["h"])
    logs = client.get("/api/audit-logs", params={"action": "access_denied", "page_size": 200}, headers=org["admin"]["h"]).json()["items"]
    assert any(l["actor_email"] == org["mgr_a"]["email"] and l["entity_id"] == org["emp_b1"]["id"] for l in logs)


def test_notifications_are_personal(client, org):
    mine = client.get("/api/notifications", headers=org["mgr_a"]["h"]).json()["items"]
    db = SessionLocal()
    try:
        owners = {n.user_id for n in db.query(Notification).filter(Notification.id.in_([n["id"] for n in mine] or [0]))}
    finally:
        db.close()
    assert owners <= {org["mgr_a"]["user_id"]}
    db = SessionLocal()
    try:
        nid = db.query(Notification.id).filter(Notification.user_id == org["hr_b"]["user_id"]).first()
    finally:
        db.close()
    if nid:
        assert client.post(f"/api/notifications/{nid[0]}/read", headers=org["mgr_a"]["h"]).status_code == 404
