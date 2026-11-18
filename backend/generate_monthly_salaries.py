"""Create the monthly salary records that are due (same logic as the API's
background loop). Safe to run as often as you like: an existing month is never
created twice.

    python generate_monthly_salaries.py                 # up to the current month
    python generate_monthly_salaries.py --month 2026-11 # up to a given month (not later than today)
    python generate_monthly_salaries.py --force         # run even if the setting is switched off

Example cron (01:15 on the 1st of every month):
    15 1 1 * *  cd /path/to/backend && venv/bin/python generate_monthly_salaries.py
"""
import argparse
import sys

from app.database.database import SessionLocal
import app.models  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate due monthly salary records")
    parser.add_argument("--month", help="YYYY-MM (default: current month)")
    parser.add_argument("--force", action="store_true", help="ignore the salary_auto_generate setting")
    args = parser.parse_args()

    from app.services import salary_autogen_service
    from app.utils.clock import local_today

    up_to = None
    if args.month:
        try:
            year, month = (int(x) for x in args.month.split("-"))
            assert 1 <= month <= 12
        except Exception:
            print("--month must look like 2026-11", file=sys.stderr)
            return 2
        today = local_today()
        if (year, month) > (today.year, today.month):
            print("Future months are not generated.", file=sys.stderr)
            return 2
        up_to = (year, month)

    db = SessionLocal()
    try:
        if not args.force and not salary_autogen_service.is_enabled(db):
            print("Automatic salary slips are switched off in Settings (use --force to run anyway).")
            return 0
        summary = salary_autogen_service.run(db, up_to=up_to)
        db.commit()
    finally:
        db.close()
    print(f"Up to {summary['period']}: created {summary['created']}, "
          f"already present {summary['skipped_existing']}, "
          f"no previous salary {summary['skipped_no_previous']}, "
          f"last salary too old {summary['skipped_stale']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
