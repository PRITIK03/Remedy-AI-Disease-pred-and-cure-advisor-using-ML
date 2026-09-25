"""
Phase 3 E2E smoke test: Next.js frontend + FastAPI backend, live.

Steps (per the Phase 3 plan):
 1. start FastAPI (uvicorn, scratch port)
 2. start `next start` (production build, scratch port)
 3. fetch /  (dashboard)                       -> 200 + hero text
 4. fetch /assessment                          -> 200 + form sections
 5. POST /api/v1/assessments via frontend-origin CORS preflight
 6. fetch /results/{id}                        -> 200 + client shell
 7. fetch /history                             -> 200
 8. verify results page shows assessment id in RSC payload
 9. stop backend -> verify frontend still serves + API fails gracefully
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = "http://127.0.0.1:8010"
FRONTEND = "http://127.0.0.1:3100"
PROJ = str(Path(__file__).resolve().parents[1])
FRONTEND_DIR = str(Path(__file__).resolve().parents[1] / "frontend")

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + detail if detail else ""))


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.read().decode("utf-8", "replace")


def post_json(url, body, headers=None):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read().decode())


def main():
    venv_python = sys.executable
    backend_proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "backend.app.main:app", "--port", "8010"],
        cwd=PROJ, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3100"},
    )
    frontend_proc = subprocess.Popen(
        ["npx", "next", "start", "-p", "3100"],
        cwd=FRONTEND_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        shell=(sys.platform == "win32"),
    )
    try:
        # wait for both servers
        deadline = time.time() + 60
        backend_up = frontend_up = False
        while time.time() < deadline and not (backend_up and frontend_up):
            if not backend_up:
                try:
                    get(f"{BACKEND}/health")
                    backend_up = True
                except Exception:
                    pass
            if not frontend_up:
                try:
                    get(FRONTEND)
                    frontend_up = True
                except Exception:
                    pass
            time.sleep(0.5)
        check("backend started", backend_up)
        check("frontend started", frontend_up)
        if not (backend_up and frontend_up):
            return

        # 3. dashboard
        status, html = get(f"{FRONTEND}/")
        check(
            "dashboard renders hero",
            status == 200 and "Cardiovascular Health Assessment" in html,
        )

        # 4. assessment page
        status, html = get(f"{FRONTEND}/assessment")
        check(
            "assessment page renders form sections",
            status == 200
            and "Basic Information" in html
            and "13 inputs" in html,
        )

        # 5. CORS preflight + create assessment (as the browser would)
        req = urllib.request.Request(
            f"{BACKEND}/api/v1/assessments", method="OPTIONS",
            headers={
                "Origin": FRONTEND,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            allow_origin = r.headers.get("access-control-allow-origin", "")
        check("CORS allows frontend origin", allow_origin in ("*", FRONTEND), allow_origin)

        payload = {
            "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180,
            "fbs": 0, "restecg": 0, "thalach": 170, "exang": 0,
            "oldpeak": 0.5, "slope": 1, "ca": 0, "thal": 2,
        }
        status, body = post_json(
            f"{BACKEND}/api/v1/assessments", payload, {"Origin": FRONTEND}
        )
        check(
            "assessment created via API",
            status == 201 and body["model_version"] == "2.0.0",
            f"prob={body['disease_probability']}",
        )
        aid = body["id"]

        # invalid payload rejected
        try:
            post_json(f"{BACKEND}/api/v1/assessments", {**payload, "cp": 9})
            check("invalid assessment rejected", False)
        except urllib.error.HTTPError as e:
            check("invalid assessment rejected (422)", e.code == 422)

        # 6. results page (client component; verify page shell + id present)
        status, html = get(f"{FRONTEND}/results/{aid}")
        check("results page loads", status == 200 and aid in html)

        # explanation endpoint consumed by results page
        status, expl = get(f"{BACKEND}/api/v1/assessments/{aid}/explanation")
        expl = json.loads(expl)
        check(
            "explanation endpoint returns contributions",
            status == 200 and len(expl["contributions"]) > 0,
            f"n={len(expl['contributions'])}",
        )

        # 7. history page
        status, html = get(f"{FRONTEND}/history")
        check("history page loads", status == 200 and "Assessment History" in html)

        # 9. stop backend -> frontend up, backend down
        backend_proc.terminate()
        backend_proc.wait(timeout=15)
        try:
            get(f"{FRONTEND}/")
            check("frontend survives backend outage", True)
        except Exception as e:
            check("frontend survives backend outage", False, str(e))
        try:
            get(f"{BACKEND}/health")
            check("backend actually stopped", False)
        except Exception:
            check("backend actually stopped", True)
    finally:
        for proc in (backend_proc, frontend_proc):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
