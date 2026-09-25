# README Audit (Phase 0)

Every significant README claim checked against the actual code, artifacts,
and executed behavior. Evidence references point to verified facts in
`docs/legacy-ml-baseline.md` ("Baseline §") and executed tests.

| # | README claim | Actual implementation | Status | Evidence |
|---|--------------|----------------------|--------|----------|
| 1 | "Accuracy ~90%… 91.3% Voting Classifier on UCI Heart Disease" | No training code, no dataset, no evaluation artifacts in repo. Scaler fit on full dataset (leakage). Numbers unverifiable and inflated by leakage. | **Not implemented / unverifiable** | Baseline §1, §10 |
| 2 | "Combines three predictive models" | VotingClassifier has exactly **2** members (RF + LR). Third standalone models loaded but unused. | **Outdated / false** | Baseline §5.3 |
| 3 | "(optional GB)"/XGBoost implied in ensemble | No GradientBoosting/XGBoost in any artifact. xgboost only in requirements. | **Not implemented** | Baseline §5.3 |
| 4 | Project structure: `Models/`, `templates/`, `static/css`, `static/js`, `static/images`, `LICENSE`, `CONTRIBUTING.md`, `.gitignore` | None exist. Flat repo: app.py + index.html at root; pkls at root; no LICENSE, no CONTRIBUTING, no .gitignore, no static. | **Not implemented** | git ls-tree output |
| 5 | "Input Validation Layer: type checking, range validation, null/empty checks" | Only `int()`/`float()` casts; no range checks; 500 crash on malformed input. | **Not implemented** | Baseline §3 |
| 6 | "CSRF protection (Flask-WTF integration recommended)" | No Flask-WTF, no CSRF anywhere. | **Not implemented** | app.py |
| 7 | "Environment configuration via .env / python-dotenv" | No dotenv, no env vars read; hardcoded Windows paths + debug=True. | **Not implemented** (fixed in Phase 0) | app.py |
| 8 | API reference: "GET /", "POST /predict" with documented param ranges | Routes exist as documented; ranges in README conflict with HTML limits and dataset encodings (ca 0–4 vs HTML 0–3; thal 0–3 vs HTML 1–3). | **Partially implemented** | Baseline §3 |
| 9 | "Response Time <100ms, P95 120ms, P99 180ms" | No benchmarking code or evidence. | **Not implemented** | repo |
| 10 | "Memory footprint ~150MB, model load 2–3s" | No evidence. | **Not implemented** | repo |
| 11 | `get_remedies` documented signature/behavior | Function exists; behavior matches doc loosely; triggered rules verified. | **Verified** (with §6 inversion caveat) | Baseline §8 |
| 12 | "Evidence-based remedies align with AHA/ACC guidelines" | Hardcoded lifestyle strings; no citations; fires urgent advice for healthy users due to inversion. | **Partially implemented / misleading** | Baseline §6, §8 |
| 13 | Security checklist (auth, HIPAA, encryption…) | None implemented; README says "recommended" for some but implies production posture. | **Not implemented** | repo |
| 14 | Deployment guide (Gunicorn/Nginx/Docker/Heroku) | Only a Procfile exists; Procfile + gunicorn is consistent with Heroku. Dockerfile absent. | **Partially implemented** | Procfile |
| 15 | Troubleshooting section admits hardcoded Windows paths | True and was real: `C:\Users\priti\OneDrive\Desktop\MY_Project\Models\...` in app.py. | **Verified (bug now fixed in Phase 0)** | git history, app.py |
| 16 | "Flask 2.0+/2.3.0", scikit-learn 1.2+ badges | Actual pin 3.0.3 / mixed sklearn versions. | **Outdated** | dependency-audit.md |
| 17 | Citation "2026", version 1.1.0, "Active & Maintained" | README-only metadata. | **Outdated** | README |
| 18 | "enterprise-grade" | No tests (until Phase 0), no CI, no logging, debug=True, no validation, broken paths, inverted output semantics. | **Not implemented** | everywhere |
| 19 | Real-time predictions | Predictions are synchronous single-request; fine, but "real-time" implies streaming/latency engineering that doesn't exist. | **Needs re-evaluation** | app.py |
| 20 | "AI-driven, context-aware advice" | Static `if` rules on 5 features. | **Not implemented** | Baseline §8 |

## Notes

- The README is largely aspirational documentation written after the fact
  (git history shows it was added/expanded in dedicated README commits, while
  app.py never changed after its initial upload).
- No README content was deleted in Phase 0; this file is the authoritative
  correction record until the README rewrite phase.
