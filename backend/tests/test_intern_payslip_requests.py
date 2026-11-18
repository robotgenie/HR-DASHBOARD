"""Intern payslip download requests: reason, HR decision, per-payslip permission.

Covers the nine scenarios in the specification, including the security cases
where the intern goes straight at the API instead of using the button.
"""
from app.core.constants import AuditAction, NotificationType
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.intern_payslip_request import InternPayslipDownloadRequest
from app.models.notification import Notification

INTERN_COMPONENTS = [
    {"name": "Basic", "component_type": "earning", "amount": 8333},
    {"name": "Incentive", "component_type": "earning", "amount": 5000},
    {"name": "PT", "component_type": "deduction", "amount": 200},
]


def credit(client, hr_headers, employee_id, month):
    created = client.post("/api/salaries", json={
        "employee_id": employee_id, "period_year": 2026, "period_month": month,
        "working_days": 26, "components": INTERN_COMPONENTS,
    }, headers=hr_headers)
    assert created.status_code in (200, 201), created.text
    salary_id = created.json()["id"]
    client.post(f"/api/salaries/{salary_id}/payslip/generate", headers=hr_headers)
    assert client.post(
        f"/api/salaries/{salary_id}/credit",
        json={"credit_date": f"2026-{month:02d}-28"}, headers=hr_headers,
    ).status_code == 200
    return salary_id


def audits(action):
    with SessionLocal() as db:
        return db.query(AuditLog).filter(AuditLog.action == action).count()


# ---------------------------------------------------------------- Test 1
def test_regular_employee_download_is_unchanged(client, hr_headers, employee_b,
                                                emp_b_headers):
    """The request workflow must not leak onto non-interns."""
    salary_id = credit(client, hr_headers, employee_b["id"], 7)
    detail = client.get(f"/api/salaries/{salary_id}", headers=emp_b_headers).json()
    assert detail["is_intern"] is False
    assert detail["employee_can_download_payslip"] is True
    assert detail["can_request_download"] is False

    assert client.get(f"/api/salaries/{salary_id}/payslip/download",
                      headers=emp_b_headers).status_code == 200

    asked = client.post(f"/api/salaries/{salary_id}/download-request",
                        json={"reason": "I would like a copy for my records."},
                        headers=emp_b_headers)
    assert asked.status_code == 422
    assert "interns only" in asked.json()["detail"]


# ---------------------------------------------------------------- Test 2
def test_intern_can_view_but_not_download(client, hr_headers, intern_ds,
                                          intern_ds_headers):
    salary_id = credit(client, hr_headers, intern_ds["id"], 7)

    detail = client.get(f"/api/salaries/{salary_id}", headers=intern_ds_headers).json()
    assert detail["is_intern"] is True
    assert detail["employee_can_view_payslip"] is True
    assert detail["employee_can_download_payslip"] is False
    assert detail["can_request_download"] is True
    assert detail["download_request_status"] is None

    view = client.get(f"/api/salaries/{salary_id}/payslip", headers=intern_ds_headers)
    assert view.status_code == 200
    assert view.content.startswith(b"%PDF")


# ---------------------------------------------------------------- Test 3
def test_reason_is_required_and_must_be_meaningful(client, intern_ds_headers,
                                                   intern_ds):
    salaries = client.get("/api/salaries", headers=intern_ds_headers,
                          params={"page_size": 50}).json()["items"]
    salary_id = next(s["id"] for s in salaries if s["can_request_download"])

    for bad in ("", "   ", "\n\t "):
        response = client.post(f"/api/salaries/{salary_id}/download-request",
                               json={"reason": bad}, headers=intern_ds_headers)
        assert response.status_code == 422, f"{bad!r} should be rejected"

    thin = client.post(f"/api/salaries/{salary_id}/download-request",
                       json={"reason": "abc"}, headers=intern_ds_headers)
    assert thin.status_code == 422

    numbers_only = client.post(f"/api/salaries/{salary_id}/download-request",
                               json={"reason": "1234567890123"},
                               headers=intern_ds_headers)
    assert numbers_only.status_code == 422

    with SessionLocal() as db:
        assert db.query(InternPayslipDownloadRequest).filter(
            InternPayslipDownloadRequest.salary_id == salary_id).count() == 0


def test_reason_is_trimmed_before_storing(client, intern_ds_headers, intern_ds):
    salaries = client.get("/api/salaries", headers=intern_ds_headers,
                          params={"page_size": 50}).json()["items"]
    salary_id = next(s["id"] for s in salaries if s["can_request_download"])

    response = client.post(
        f"/api/salaries/{salary_id}/download-request",
        json={"reason": "   Needed for my bank account opening documents.   "},
        headers=intern_ds_headers,
    )
    assert response.status_code == 201
    assert response.json()["reason"] == "Needed for my bank account opening documents."
    assert response.json()["status"] == "Pending"


# ---------------------------------------------------------------- Test 4
def test_request_appears_for_hr_with_the_reason(client, hr_headers, intern_ds):
    queue = client.get("/api/payslip-download-requests",
                       headers=hr_headers, params={"status": "Pending"}).json()
    mine = [r for r in queue["items"] if r["employee_id"] == intern_ds["id"]]
    assert mine, "the request should be waiting in HR's queue"
    row = mine[0]
    assert row["reason"] == "Needed for my bank account opening documents."
    assert row["employee_name"]
    assert row["period_label"]
    assert row["status"] == "Pending"


def test_hr_is_notified_of_the_request(client, hr_user):
    with SessionLocal() as db:
        found = (
            db.query(Notification)
            .filter(
                Notification.user_id == hr_user["user_id"],
                Notification.type == NotificationType.PAYSLIP_DOWNLOAD_REQUESTED,
            )
            .first()
        )
    assert found is not None
    assert "download request received" in found.message


def test_request_is_audit_logged():
    assert audits(AuditAction.INTERN_PAYSLIP_DOWNLOAD_REQUESTED) >= 1


def test_duplicate_pending_request_is_refused(client, intern_ds_headers, intern_ds):
    pending = client.get("/api/payslip-download-requests",
                         headers=intern_ds_headers,
                         params={"status": "Pending"}).json()["items"][0]
    response = client.post(f"/api/salaries/{pending['salary_id']}/download-request",
                           json={"reason": "Asking again for the same payslip."},
                           headers=intern_ds_headers)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Your download request is already pending HR approval."
    )


def test_download_still_blocked_while_pending(client, intern_ds_headers):
    pending = client.get("/api/payslip-download-requests",
                         headers=intern_ds_headers,
                         params={"status": "Pending"}).json()["items"][0]
    assert client.get(f"/api/salaries/{pending['salary_id']}/payslip/download",
                      headers=intern_ds_headers).status_code == 403


# ---------------------------------------------------------------- Test 5
def test_hr_approval_grants_permission_and_notifies(client, hr_headers,
                                                    intern_ds, intern_ds_headers):
    pending = client.get("/api/payslip-download-requests", headers=hr_headers,
                         params={"status": "Pending"}).json()["items"]
    request = next(r for r in pending if r["employee_id"] == intern_ds["id"])

    response = client.post(f"/api/payslip-download-requests/{request['id']}/approve",
                           json={"remarks": "Fine for bank purposes."},
                           headers=hr_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Approved"
    assert body["hr_remarks"] == "Fine for bank purposes."
    assert body["hr_reviewer"]
    assert body["reviewed_at"] is not None

    detail = client.get(f"/api/salaries/{request['salary_id']}",
                        headers=intern_ds_headers).json()
    assert detail["intern_download_allowed"] is True
    assert detail["employee_can_download_payslip"] is True
    assert detail["download_block_reason"] is None

    with SessionLocal() as db:
        note = (
            db.query(Notification)
            .filter(
                Notification.user_id == intern_ds["user_id"],
                Notification.type == NotificationType.PAYSLIP_DOWNLOAD_GRANTED,
            )
            .first()
        )
    assert note is not None
    assert "permission to download" in note.message
    assert audits(AuditAction.INTERN_PAYSLIP_REQUEST_APPROVED) >= 1


def test_intern_can_download_after_approval(client, intern_ds_headers):
    approved = client.get("/api/payslip-download-requests", headers=intern_ds_headers,
                          params={"status": "Approved"}).json()["items"][0]
    response = client.get(f"/api/salaries/{approved['salary_id']}/payslip/download",
                          headers=intern_ds_headers)
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert audits(AuditAction.INTERN_PAYSLIP_DOWNLOADED) >= 1


def test_approving_twice_is_refused(client, hr_headers, intern_ds_headers):
    approved = client.get("/api/payslip-download-requests", headers=intern_ds_headers,
                          params={"status": "Approved"}).json()["items"][0]
    response = client.post(f"/api/payslip-download-requests/{approved['id']}/approve",
                           json={}, headers=hr_headers)
    assert response.status_code == 409


# ---------------------------------------------------------------- Test 6
def test_hr_rejection_keeps_download_blocked(client, hr_headers, intern_cy,
                                             intern_cy_headers):
    salary_id = credit(client, hr_headers, intern_cy["id"], 7)
    created = client.post(f"/api/salaries/{salary_id}/download-request",
                          json={"reason": "I want a copy of this payslip please."},
                          headers=intern_cy_headers)
    assert created.status_code == 201
    request_id = created.json()["id"]

    # a rejection with no reason is refused: the intern needs to know why
    assert client.post(f"/api/payslip-download-requests/{request_id}/reject",
                       json={}, headers=hr_headers).status_code == 422

    response = client.post(f"/api/payslip-download-requests/{request_id}/reject",
                           json={"remarks": "Ask your mentor for a stamped copy."},
                           headers=hr_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "Rejected"

    detail = client.get(f"/api/salaries/{salary_id}", headers=intern_cy_headers).json()
    assert detail["intern_download_allowed"] is False
    assert detail["employee_can_download_payslip"] is False
    assert detail["download_request_status"] == "Rejected"
    assert detail["can_request_download"] is True      # may ask again

    assert client.get(f"/api/salaries/{salary_id}/payslip/download",
                      headers=intern_cy_headers).status_code == 403

    with SessionLocal() as db:
        note = (
            db.query(Notification)
            .filter(
                Notification.user_id == intern_cy["user_id"],
                Notification.type == NotificationType.PAYSLIP_DOWNLOAD_REJECTED,
            )
            .first()
        )
    assert note is not None
    assert "rejected" in note.message.lower()
    assert audits(AuditAction.INTERN_PAYSLIP_REQUEST_REJECTED) >= 1


def test_intern_may_request_again_after_a_rejection(client, intern_cy_headers,
                                                    intern_cy):
    rejected = client.get("/api/payslip-download-requests", headers=intern_cy_headers,
                          params={"status": "Rejected"}).json()["items"][0]
    response = client.post(f"/api/salaries/{rejected['salary_id']}/download-request",
                           json={"reason": "My mentor asked me to request it here."},
                           headers=intern_cy_headers)
    assert response.status_code == 201
    assert response.json()["status"] == "Pending"


# ---------------------------------------------------------------- Test 7
def test_direct_api_download_without_permission_is_403(client, hr_headers,
                                                       intern_ds, intern_ds_headers):
    """No button involved: straight at the endpoint."""
    salary_id = credit(client, hr_headers, intern_ds["id"], 8)
    response = client.get(f"/api/salaries/{salary_id}/payslip/download",
                          headers=intern_ds_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Download permission has not been granted by HR."
    )
    assert audits(AuditAction.INTERN_PAYSLIP_DOWNLOAD_DENIED) >= 1


def test_intern_cannot_grant_their_own_permission(client, intern_ds_headers):
    salary = client.get("/api/salaries", headers=intern_ds_headers,
                        params={"page_size": 50}).json()["items"][0]
    assert client.post(f"/api/salaries/{salary['id']}/payslip-permission",
                       json={"allowed": True},
                       headers=intern_ds_headers).status_code == 403


def test_intern_cannot_approve_a_request(client, intern_ds_headers):
    request = client.get("/api/payslip-download-requests", headers=intern_ds_headers,
                         params={"page_size": 5}).json()["items"][0]
    assert client.post(f"/api/payslip-download-requests/{request['id']}/approve",
                       json={}, headers=intern_ds_headers).status_code == 403
    assert client.post(f"/api/payslip-download-requests/{request['id']}/reject",
                       json={"remarks": "no"},
                       headers=intern_ds_headers).status_code == 403


# ---------------------------------------------------------------- Test 8
def test_intern_cannot_reach_another_employees_payslip(client, hr_headers,
                                                       employee_a, intern_ds_headers):
    """Changing the salary id in the URL must not work."""
    other = credit(client, hr_headers, employee_a["id"], 9)
    assert client.get(f"/api/salaries/{other}", headers=intern_ds_headers
                      ).status_code in (403, 404)
    assert client.get(f"/api/salaries/{other}/payslip/download",
                      headers=intern_ds_headers).status_code in (403, 404)
    assert client.get(f"/api/salaries/{other}/payslip",
                      headers=intern_ds_headers).status_code in (403, 404)

    asked = client.post(f"/api/salaries/{other}/download-request",
                        json={"reason": "Trying to reach someone else's payslip."},
                        headers=intern_ds_headers)
    assert asked.status_code in (403, 404)


def test_intern_sees_only_their_own_requests(client, intern_ds_headers, intern_cy):
    listing = client.get("/api/payslip-download-requests",
                         headers=intern_ds_headers).json()
    assert all(r["employee_id"] != intern_cy["id"] for r in listing["items"])


def test_intern_cannot_open_another_interns_request(client, intern_ds_headers,
                                                    hr_headers, intern_cy):
    other = client.get("/api/payslip-download-requests", headers=hr_headers,
                       params={"employee_id": intern_cy["id"]}).json()["items"][0]
    assert client.get(f"/api/payslip-download-requests/{other['id']}",
                      headers=intern_ds_headers).status_code == 403


# ---------------------------------------------------------------- Test 9
def test_approval_is_per_payslip_not_blanket(client, hr_headers, intern_ds,
                                             intern_ds_headers):
    """An approved March must not unlock April."""
    salaries = client.get("/api/salaries", headers=intern_ds_headers,
                          params={"page_size": 50}).json()["items"]
    allowed = [s for s in salaries if s["intern_download_allowed"]]
    blocked = [s for s in salaries if not s["intern_download_allowed"]
               and s["status"] == "Credited"]
    assert allowed, "expected one approved payslip"
    assert blocked, "expected at least one still-blocked payslip"

    assert client.get(f"/api/salaries/{allowed[0]['id']}/payslip/download",
                      headers=intern_ds_headers).status_code == 200
    for salary in blocked:
        assert client.get(f"/api/salaries/{salary['id']}/payslip/download",
                          headers=intern_ds_headers).status_code == 403


def test_hr_can_filter_and_search_the_queue(client, hr_headers, intern_ds):
    approved = client.get("/api/payslip-download-requests", headers=hr_headers,
                          params={"status": "Approved"}).json()
    assert all(r["status"] == "Approved" for r in approved["items"])

    by_employee = client.get("/api/payslip-download-requests", headers=hr_headers,
                             params={"employee_id": intern_ds["id"]}).json()
    assert all(r["employee_id"] == intern_ds["id"] for r in by_employee["items"])

    searched = client.get("/api/payslip-download-requests", headers=hr_headers,
                          params={"search": "bank account"}).json()
    assert all("bank account" in r["reason"].lower() for r in searched["items"])

    bad = client.get("/api/payslip-download-requests", headers=hr_headers,
                     params={"status": "Nonsense"})
    assert bad.status_code == 422
