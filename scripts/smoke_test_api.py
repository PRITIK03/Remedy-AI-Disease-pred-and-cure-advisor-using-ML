"""Live HTTP smoke test for the Phase 2 API.

Boots uvicorn on a scratch port, then exercises /docs, /health, /ready and
the full assessments workflow (create → fetch → list) over real HTTP.

Usage:
    .venv/Scripts/python scripts/smoke_test_api.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Ensure the project root is importable when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

BASE = "http://127.0.0.1:8123"
PAYLOAD = {
    "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180,
    "fbs": 0, "restecg": 0, "thalach": 170, "exang": 0,
    "oldpeak": 0.5, "slope": 1, "ca": 0, "thal": 2,
}


def _req(path: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, dict(r.headers), json.loads(r.read().decode())


def wait_up(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=2):
                return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import uvicorn

    from backend.app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=8123, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    failures: list[str] = []
    try:
        if not wait_up():
            print("FAIL: server did not come up")
            return 1
        print("server up")

        # /docs
        req = urllib.request.Request(BASE + "/docs")
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = r.status == 200
        print(("PASS" if ok else "FAIL"), "GET /docs")
        if not ok:
            failures.append("/docs")

        # /health
        status, headers, body = _req("/health")
        ok = status == 200 and body["status"] == "ok"
        print(("PASS" if ok else "FAIL"), "GET /health →", body)
        if not ok:
            failures.append("/health")

        # /ready
        status, headers, body = _req("/ready")
        db_ok = body["services"]["database"] == "ok"
        model_ok = body["services"]["model"] == "ok"
        print(("PASS" if (status == 200 and db_ok and model_ok) else "FAIL"),
              "GET /ready →", body["services"])
        if not (status == 200 and db_ok and model_ok):
            failures.append("/ready")

        # POST assessment
        status, headers, created = _req("/api/v1/assessments", "POST", PAYLOAD)
        ok = (
            status == 201
            and created["model_version"] == "2.0.0"
            and created["probability_label"] == "model_estimated_probability"
            and 0.0 <= created["disease_probability"] <= 1.0
            and "x-request-id" in {k.lower() for k in headers}
        )
        rid = headers.get("X-Request-ID", headers.get("x-request-id", "?"))
        print(("PASS" if ok else "FAIL"),
              f"POST /api/v1/assessments -> prob={created['disease_probability']:.4f} "
              f"predicted={created['predicted_disease']} rid={rid}")
        if not ok:
            failures.append("POST /api/v1/assessments")

        # GET one
        status, _, fetched = _req(f"/api/v1/assessments/{created['id']}")
        ok = status == 200 and fetched["id"] == created["id"]
        print(("PASS" if ok else "FAIL"), "GET /api/v1/assessments/{id}")
        if not ok:
            failures.append("GET assessment")

        # GET list (pagination)
        status, _, listing = _req("/api/v1/assessments?limit=5&offset=0")
        ok = status == 200 and listing["total"] >= 1 and len(listing["items"]) <= 5
        print(("PASS" if ok else "FAIL"),
              f"GET /api/v1/assessments?limit=5 -> total={listing['total']}")
        if not ok:
            failures.append("GET assessments list")

        # 404
        try:
            _req("/api/v1/assessments/00000000-0000-0000-0000-000000000000")
            ok = False
        except urllib.error.HTTPError as e:
            ok = e.code == 404
        print(("PASS" if ok else "FAIL"), "GET missing assessment → 404")
        if not ok:
            failures.append("404 handling")

        # 422 strict validation
        try:
            _req("/api/v1/assessments", "POST", {**PAYLOAD, "cp": 9})
            ok = False
        except urllib.error.HTTPError as e:
            ok = e.code == 422
        print(("PASS" if ok else "FAIL"), "POST invalid cp=9 → 422")
        if not ok:
            failures.append("422 validation")

    finally:
        server.should_exit = True
        thread.join(timeout=10)

    print()
    if failures:
        print("SMOKE TEST FAILED:", failures)
        return 1
    print("SMOKE TEST PASSED: all checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
