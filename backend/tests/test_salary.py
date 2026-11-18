"""Salary calculation, payslip generation and the credit workflow."""
import pytest

from app.utils.amount_words import amount_to_words


@pytest.fixture(scope="module")
def salary_id(client, hr_headers, employee_a):
    response = client.post(
        "/api/salaries",
        json={
            "employee_id": employee_a["id"],
            "period_year": 2026, "period_month": 3, "working_days": 31,
            "components": [
                # Salary structure is Basic + Incentive; the same 11,129 total
                # as before, so the amount-in-words assertions still hold.
                {"component_type": "earning", "name": "Basic", "amount": "6958"},
                {"component_type": "earning", "name": "Incentive", "amount": "4171"},
            ],
        },
        headers=hr_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_totals_are_computed_server_side(client, hr_headers, salary_id):
    body = client.get(f"/api/salaries/{salary_id}", headers=hr_headers).json()
    assert float(body["total_earnings"]) == 11129.0
    assert float(body["total_deductions"]) == 0.0
    assert float(body["net_pay"]) == 11129.0
    assert body["period_label"] == "March 2026"


def test_amount_in_words_matches_the_reference(client, hr_headers, salary_id):
    body = client.get(f"/api/salaries/{salary_id}", headers=hr_headers).json()
    assert body["amount_in_words"] == "Eleven Thousand One Hundred Twenty Nine Only"


def test_amount_in_words_handles_indian_grouping():
    assert amount_to_words(25500) == "Twenty Five Thousand Five Hundred Only"
    assert amount_to_words(100000) == "One Lakh Only"
    assert amount_to_words(12500000) == "One Crore Twenty Five Lakh Only"


def test_new_salary_starts_pending(client, hr_headers, salary_id):
    assert client.get(f"/api/salaries/{salary_id}", headers=hr_headers).json()["status"] == "Pending"


def test_employee_cannot_see_a_payslip_before_it_is_credited(
    client, emp_a_headers, salary_id
):
    assert client.get(
        f"/api/salaries/{salary_id}/payslip", headers=emp_a_headers
    ).status_code == 403


def test_employee_cannot_create_or_modify_salary(client, emp_a_headers, employee_a, salary_id):
    assert client.post(
        "/api/salaries",
        json={"employee_id": employee_a["id"], "period_year": 2026,
              "period_month": 9, "working_days": 30, "components": []},
        headers=emp_a_headers,
    ).status_code == 403
    assert client.put(
        f"/api/salaries/{salary_id}", json={"working_days": 1}, headers=emp_a_headers
    ).status_code == 403
    assert client.post(
        f"/api/salaries/{salary_id}/credit", json={}, headers=emp_a_headers
    ).status_code == 403


def test_employee_b_cannot_read_employee_a_salary(client, emp_b_headers, salary_id):
    assert client.get(
        f"/api/salaries/{salary_id}", headers=emp_b_headers
    ).status_code == 403
    assert client.get(
        f"/api/salaries/{salary_id}/payslip/download", headers=emp_b_headers
    ).status_code == 403


def test_crediting_fans_out_notification_email_and_payslip(
    client, hr_headers, salary_id
):
    response = client.post(
        f"/api/salaries/{salary_id}/credit",
        json={"credit_date": "2026-04-01", "attach_payslip": True},
        headers=hr_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["salary"]["status"] == "Credited"
    assert body["notification_created"] is True
    assert body["email_sent"] is True
    assert body["payslip_ready"] is True


def test_crediting_again_does_not_duplicate(client, hr_headers, salary_id):
    """The spec's idempotency requirement: salary_id + credit_event runs once."""
    response = client.post(
        f"/api/salaries/{salary_id}/credit", json={}, headers=hr_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["notification_created"] is False
    assert body["email_sent"] is False
    assert "no duplicate" in body["detail"]


def test_only_one_credit_notification_exists(client, emp_a_headers, salary_id):
    items = client.get("/api/notifications", headers=emp_a_headers).json()["items"]
    credited = [
        n for n in items
        if n["type"] == "Salary Credited" and n["related_id"] == salary_id
    ]
    assert len(credited) == 1


def test_only_one_credit_email_was_logged(client, hr_headers, salary_id):
    """Scoped to this salary: other tests credit their own records too."""
    logs = client.get("/api/audit-logs/emails?limit=200", headers=hr_headers).json()
    matching = [
        e for e in logs
        if e["template"] == "salary_credited" and e["related_id"] == salary_id
    ]
    assert len(matching) == 1


def test_updating_an_already_credited_salary_does_not_re_notify(
    client, hr_headers, emp_a_headers, salary_id
):
    before = len(client.get("/api/notifications", headers=emp_a_headers).json()["items"])
    response = client.put(
        f"/api/salaries/{salary_id}",
        json={"status": "Credited", "remarks": "Re-saved by HR"},
        headers=hr_headers,
    )
    assert response.status_code == 200
    after = len(client.get("/api/notifications", headers=emp_a_headers).json()["items"])
    assert after == before


def test_employee_can_view_and_download_the_payslip_once_credited(
    client, emp_a_headers, salary_id
):
    view = client.get(f"/api/salaries/{salary_id}/payslip", headers=emp_a_headers)
    assert view.status_code == 200
    assert view.headers["content-type"] == "application/pdf"
    assert view.content.startswith(b"%PDF")

    download = client.get(
        f"/api/salaries/{salary_id}/payslip/download", headers=emp_a_headers
    )
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]


def test_payslip_contains_the_dynamic_values(client, emp_a_headers, salary_id):
    import pdfplumber, io

    content = client.get(
        f"/api/salaries/{salary_id}/payslip", headers=emp_a_headers
    ).content
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = pdf.pages[0].extract_text()

    # Header follows the supplied reference: company, address, Udyam NI
    assert "Robot Genie" in text
    assert "Laxmi Nagar" in text
    assert "Udyam NI" in text
    assert "UDYAM-DL-02-0061089" in text
    assert "GST" not in text                       # explicitly not on the payslip

    # Title carries the period from the salary record, not a hard-coded month
    assert "Payslip for the Month of March, 2026" in text

    # Employee block
    assert "Employee A" in text
    assert "Digital Marketing" in text
    assert "Employee ID" in text
    assert "Bank Name" in text
    assert "Bank Account No." in text
    assert "PAN No." in text
    assert "Location" in text
    assert "Effective Work Days" in text
    assert "LOP" in text

    # Earnings are Basic/Incentive only
    assert "HRA" not in text
    assert "House Rent Allowance" not in text
    assert "Special Allowance" not in text

    # Totals and net pay
    assert "11,129" in text
    assert "Total Earnings" in text
    assert "Total Deductions" in text
    assert "Net Pay For The Month" in text
    assert "Eleven Thousand One Hundred Twenty Nine Only" in text

    # Footer: director above the closing rule, system-generated note, no signature
    assert "Director: Mr. Ali Alvi" in text
    assert "This is a system generated payslip and does not require signature." in text
    assert "Employer Signature" not in text


def test_changing_components_changes_the_payslip(client, hr_headers, salary_id):
    """The dynamic payslip test from the spec: raise pay, regenerate, re-verify."""
    import pdfplumber, io

    response = client.put(
        f"/api/salaries/{salary_id}",
        json={
            "components": [
                {"component_type": "earning", "name": "Basic", "amount": "12750"},
                {"component_type": "earning", "name": "House Rent Allowance", "amount": "12750"},
            ]
        },
        headers=hr_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert float(body["net_pay"]) == 25500.0
    assert body["amount_in_words"] == "Twenty Five Thousand Five Hundred Only"

    regenerated = client.post(
        f"/api/salaries/{salary_id}/payslip/generate", headers=hr_headers
    )
    assert regenerated.status_code == 200

    content = client.get(f"/api/salaries/{salary_id}/payslip", headers=hr_headers).content
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = pdf.pages[0].extract_text()
    assert "25,500" in text
    assert "Twenty Five Thousand Five Hundred Only" in text
    assert "Employee A" in text  # employee details stay correct


def test_negative_component_amounts_are_refused(client, hr_headers, salary_id):
    response = client.put(
        f"/api/salaries/{salary_id}",
        json={"components": [
            {"component_type": "earning", "name": "Basic", "amount": "-500"}
        ]},
        headers=hr_headers,
    )
    assert response.status_code == 422


def test_duplicate_pay_period_is_refused(client, hr_headers, employee_a):
    response = client.post(
        "/api/salaries",
        json={"employee_id": employee_a["id"], "period_year": 2026,
              "period_month": 3, "working_days": 31, "components": []},
        headers=hr_headers,
    )
    assert response.status_code == 409


def test_deductions_reduce_net_pay(client, hr_headers, employee_b):
    response = client.post(
        "/api/salaries",
        json={
            "employee_id": employee_b["id"], "period_year": 2026,
            "period_month": 4, "working_days": 30,
            "components": [
                {"component_type": "earning", "name": "Basic", "amount": "20000"},
                {"component_type": "deduction", "name": "PF", "amount": "2400"},
                {"component_type": "deduction", "name": "Professional Tax", "amount": "200"},
            ],
        },
        headers=hr_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert float(body["total_earnings"]) == 20000.0
    assert float(body["total_deductions"]) == 2600.0
    assert float(body["net_pay"]) == 17400.0
