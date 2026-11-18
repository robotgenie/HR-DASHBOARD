"""Lightweight static verification for the requested HRMS updates."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

checks = [
    (
        "View payslip uses authenticated PDF blob endpoint",
        ROOT / "frontend/js/salary.js",
        lambda t: 'API.blob("/salaries/" + salary.id + "/payslip")' in t,
    ),
    (
        "Download payslip endpoint remains in place",
        ROOT / "frontend/js/salary.js",
        lambda t: 'API.download("/salaries/" + salary.id + "/payslip/download")' in t,
    ),
    (
        "Finance department is in defaults",
        ROOT / "backend/app/core/constants.py",
        lambda t: '("Finance", "FIN")' in t,
    ),
    (
        "Finance migration exists",
        ROOT / "backend/migrations/versions/c4f6a7b8d9e0_add_finance_department.py",
        lambda t: '"name": "Finance"' in t and '"code": "FIN"' in t,
    ),
    (
        "Profile requests UI stylesheet is included",
        ROOT / "frontend/hr/profile-requests.html",
        lambda t: "profile-requests.css" in t,
    ),
    (
        "Profile requests search field is present",
        ROOT / "frontend/js/profile-requests.js",
        lambda t: 'id="q"' in t and 'Search employee, ID or new value' in t,
    ),
    (
        "Requested database setup script exists",
        ROOT / "backend/create_robo_gini_hr_records.sql",
        lambda t: 'Robo Gini HR Records' in t,
    ),
    (
        "Alembic percent-encoding protection exists",
        ROOT / "backend/migrations/env.py",
        lambda t: 'settings.DATABASE_URL.replace("%", "%%")' in t,
    ),
]

failed = []
for label, path, predicate in checks:
    if not path.exists() or not predicate(path.read_text(encoding="utf-8")):
        failed.append(label)

if failed:
    raise SystemExit("FAILED:\n- " + "\n- ".join(failed))

print(f"PASS: {len(checks)}/{len(checks)} requested-update checks")
