"""Static verification of the complete requested HRMS update.

This verifies that the ZIP contains the required backend routes/models/migrations
and the corresponding employee/HR frontend flows. It is intentionally static;
real PostgreSQL/browser/camera execution must be performed on the target machine.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = []

def check(label, path, needles):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    ok = path.exists() and all(n in text for n in needles)
    checks.append((label, ok))

check("ID approval model fields", ROOT / "backend/app/models/employee.py", ["id_card_status", "id_card_requested_at", "id_card_approved_by_id"])
check("ID approval User relationship", ROOT / "backend/app/models/user.py", ["approved_id_cards", "Employee.id_card_approved_by_id"])
check("ID approval migration", ROOT / "backend/migrations/versions/f2a3b4c5d6e7_id_approval_and_two_reports.py", ["id_card_status", "uq_daily_report_employee_date_type", "Approved"])
check("Employee request/approval routes", ROOT / "backend/app/api/employees.py", ["request-id-approval", "approve-id", "reject-id"])
check("Final ID only after approval", ROOT / "backend/app/services/employee_service.py", ["request_employee_id_approval", "approve_employee_id", 'id_card_status'])
check("Approved ID card security", ROOT / "backend/app/services/idcard_service.py", ["id_card_status", "awaiting HR/Admin approval"])
check("Noon/EOD model", ROOT / "backend/app/models/daily_report.py", ["report_type", "uq_daily_report_employee_date_type"])
check("Noon/EOD service", ROOT / "backend/app/services/report_service.py", ["ReportType", "Noon", "EOD", "noon_submitted", "eod_submitted"])
check("Noon/EOD API filter", ROOT / "backend/app/api/reports.py", ["report_type", "ReportType.ALL"])
check("Logout checks both reports", ROOT / "backend/app/services/report_service.py", ["noon_submitted", "eod_submitted", "missing_reports"])
check("HR ID approval UI", ROOT / "frontend/hr/id-approvals.html", ["id-approvals.js"])
check("HR ID approval JS", ROOT / "frontend/js/id-approvals.js", ["approve-id", "reject-id"])
check("Employee ID request UI", ROOT / "frontend/js/profile.js", ["request-id-approval", "Request ID Approval"])
check("Employee/intern daily report UI", ROOT / "frontend/js/reports.js", ["reportCard(\"Noon\")", "reportCard(\"EOD\")", "report_type"])
check("HR Noon/EOD filter UI", ROOT / "frontend/js/reports.js", ["All report types", 'value="Noon"', 'value="EOD"'])
check("Employee + intern Check-Out report gate", ROOT / "frontend/js/work.js", ["CHECKOUT_BLOCKED", "pending_actions", "/attendance/check-out"])
check("Live selfie + location at Check-In/Check-Out", ROOT / "backend/app/services/attendance_service.py", ["save_selfie_data_url", "_validate_location", "def check_in", "def check_out"])

failed = [label for label, ok in checks if not ok]
print(f"STATIC CHECKS: {len(checks)-len(failed)}/{len(checks)} passed")
if failed:
    print("FAILED:")
    for x in failed:
        print("-", x)
    raise SystemExit(1)
