#!/usr/bin/env python3
"""Static + HTTP smoke checks for the operator console.

Used by CI in lieu of a separate frontend toolchain (vanilla JS, no npm).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_STATIC = [
    "index.html",
    "operator.js",
    "operator.css",
    "workbench.html",
    "workbench.js",
    "workbench.css",
]

REQUIRED_NAV = [
    "Overview",
    "Evaluation Runs",
    "Baselines",
    "Regressions",
    "Policy Gates",
    "Evidence",
    "Approvals",
    "Audit Log",
    "Research / Benchmarks",
    "Settings",
]

REQUIRED_JS_SYMBOLS = [
    "OperatorAPI",
    "renderOverview",
    "renderRunDetail",
    "renderApprovals",
    "renderAudit",
]


def check_static_files() -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_STATIC:
        path = STATIC / name
        if not path.is_file():
            errors.append(f"missing static file: {name}")
            continue
        if path.stat().st_size < 50:
            errors.append(f"static file too small: {name}")
    return errors


def check_operator_js() -> list[str]:
    errors: list[str] = []
    js = (STATIC / "operator.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for label in REQUIRED_NAV:
        if label not in js:
            errors.append(f"nav label missing in operator.js: {label}")
    for symbol in REQUIRED_JS_SYMBOLS:
        if symbol not in js:
            errors.append(f"symbol missing in operator.js: {symbol}")
    if "operator.js" not in html:
        errors.append("index.html does not load operator.js")
    if "Evaluation Control Plane" not in html:
        errors.append("index.html missing control-plane branding")
    return errors


def check_http_smoke() -> list[str]:
    errors: list[str] = []
    try:
        from fastapi.testclient import TestClient

        from app import db
        from app.control_plane import operator_service
        from app.main import app
    except Exception as exc:  # pragma: no cover
        return [f"import failure: {exc}"]

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "smoke.db"
        db.init_db()
        operator_service.reset_demo()
        client = TestClient(app)
        checks = [
            ("/", 200, b"Evaluation Control Plane"),
            ("/workbench", 200, b"workbench"),
            ("/api/operator/overview", 200, b"release_readiness"),
            ("/api/operator/runs", 200, b"run_cs_agent_v12_001"),
            ("/api/health", 200, None),
        ]
        for path, status, needle in checks:
            res = client.get(path)
            if res.status_code != status:
                errors.append(f"{path} expected {status}, got {res.status_code}")
            if needle is not None and needle not in res.content:
                errors.append(f"{path} missing expected content {needle!r}")
    return errors


def main() -> int:
    errors = check_static_files() + check_operator_js() + check_http_smoke()
    if errors:
        print("operator console checks FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("operator console checks OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
