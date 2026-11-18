"""Create an Admin account (the Admin is not an employee and never checks in).

    python create_admin.py --email admin@company.com --name "Org Admin"
    python create_admin.py --email admin@company.com --name "Org Admin" --password "S3cure!Pass"

Without --password a temporary password is generated and printed once; the
Admin must change it at first sign-in.
"""
import argparse
import sys

from app.database.database import SessionLocal
import app.models  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an HRMS Admin account")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="Full name shown in the portal")
    parser.add_argument("--password", help="Initial password (min 8 chars, letters and numbers)")
    parser.add_argument("--phone")
    parser.add_argument("--title", default="Administrator")
    args = parser.parse_args()

    from fastapi import HTTPException
    from app.api.admin import create_admin_account
    from app.services.auth_service import validate_password_strength

    db = SessionLocal()
    try:
        if args.password:
            validate_password_strength(args.password)
        user, raw = create_admin_account(db, args.email, args.name, password=args.password,
                                         phone=args.phone, title=args.title)
        db.commit()
        print(f"Admin created: {user.email}")
        if not args.password:
            print(f"Temporary password (shown once): {raw}")
        return 0
    except HTTPException as exc:
        db.rollback()
        print(f"Error: {exc.detail}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
