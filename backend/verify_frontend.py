"""Smoke-test that every frontend page and asset is served correctly by FastAPI."""
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

client = TestClient(app)
failures = []
checked_assets = set()


def check(path, expect=200, ctype=None):
    r = client.get(path, follow_redirects=False)
    ok = r.status_code == expect
    if ok and ctype and ctype not in r.headers.get("content-type", ""):
        ok = False
    if not ok:
        failures.append(f"{path} -> {r.status_code} {r.headers.get('content-type','')}")
    return r


print("=" * 72)
print("ROOT REDIRECT")
print("=" * 72)
r = client.get("/", follow_redirects=False)
print(f"  GET /  -> {r.status_code}  Location: {r.headers.get('location')}")
if r.status_code not in (302, 307) or "login" not in (r.headers.get("location") or ""):
    failures.append("root redirect")

pages = sorted(p for p in FRONTEND.rglob("*.html"))
print()
print("=" * 72)
print(f"HTML PAGES ({len(pages)})")
print("=" * 72)

for page in pages:
    rel = page.relative_to(FRONTEND).as_posix()
    r = check(f"/app/{rel}", ctype="text/html")
    html = r.text if r.status_code == 200 else ""
    # collect referenced local assets
    for m in re.finditer(r'(?:href|src)="([^"]+)"', html):
        ref = m.group(1)
        if ref.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if ref.endswith(".html"):
            continue
        base = Path(rel).parent
        resolved = (base / ref).as_posix() if not ref.startswith("/") else ref.lstrip("/")
        checked_assets.add(resolved.replace("app/", "", 1) if resolved.startswith("app/") else resolved)
    print(f"  {r.status_code}  /app/{rel:<38} {len(html):>6} bytes")

print()
print("=" * 72)
print(f"REFERENCED ASSETS ({len(checked_assets)})")
print("=" * 72)
for asset in sorted(checked_assets):
    norm = asset
    while norm.startswith("../"):
        norm = norm[3:]
    r = check(f"/app/{norm}")
    print(f"  {r.status_code}  /app/{norm}")

print()
print("=" * 72)
if failures:
    print(f"FAILURES ({len(failures)})")
    for f in failures:
        print("  !!", f)
    sys.exit(1)
print(f"ALL CLEAR: {len(pages)} pages + {len(checked_assets)} assets served, root redirect OK")
