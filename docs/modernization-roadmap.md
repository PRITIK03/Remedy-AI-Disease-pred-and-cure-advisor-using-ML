# Modernization Roadmap

Phase 0 (this phase) delivered the audited, test-pinned legacy baseline.
Everything below is **planned, not implemented**. Each phase ends with the
system runnable and tested.

## Phase 0 — Audit + baseline (DONE)
- Repository audit, artifact inspection, legacy behavior verification.
- Foundational fixes: paths, template resolution, env config, validation,
  logging, tests, docs.
- Deliverables: `docs/legacy-ml-baseline.md`, `docs/dependency-audit.md`,
  `docs/readme-audit.md`, `docs/current-architecture.md`, this roadmap,
  `scripts/inspect_models.py`, pytest suite, `.env.example`, `.gitignore`.

## Phase 1 — ML modernization
- Fix the **class-semantics inversion** (docs/legacy-ml-baseline.md §6) as a
  deliberate, tested change; decide label semantics and threshold policy.
- Recover/rebuild the training pipeline: proper train/test split, scaler fit
  on train only (fix the documented leakage), cross-validation, calibration
  (isotonic/Platt), model comparison (LR / RF / boosting), SHAP explainability.
- Reproducible preprocessing as a single sklearn `Pipeline` + `ColumnTransformer`
  serialized as one artifact.
- MLflow tracking, model registry, model card with honest metrics; DVC or
  committed dataset snapshot with provenance.
- Migrate dependencies to `pyproject.toml` + lockfile; resolve the sklearn
  1.4.2/1.3.2/1.5.2 three-way mismatch; drop dev-env noise (jupyter, pywin32,
  openai 0.28, xgboost unless actually adopted).

## Phase 2 — Backend modernization
- FastAPI + Pydantic v2 request/response models (typed, validated, OpenAPI).
- PostgreSQL + SQLAlchemy 2.0 (assessments, users), Redis (cache/rate limit).
- Structured logging, request IDs, central error handling, health/readiness
  endpoints. Keep the Flask app importable-free separation; deprecate app.py.

## Phase 3 — Frontend redesign
- Next.js + TypeScript + Tailwind, component system, accessible forms with
  real validation, results dashboard with visual explanations (SHAP-backed),
  assessment history, report upload UI, conversational assistant shell.

## Phase 4 — RAG (GenAI)
- LLM abstraction layer (provider-agnostic), structured outputs.
- Medical guidance corpus → embeddings → pgvector, reranking, evidence
  citations for every recommendation; refusal/safety guardrails.
- Replace the rule-based `get_remedies()` with retrieval-grounded,
  citation-backed advice; keep rules as deterministic fallback.

## Phase 5 — Agentic AI (LangGraph)
- Controlled workflow graph: intake → risk → explanation → recommendation →
  human-review path for high-risk outputs.
- Tool calling (read-only initially), state persistence, safety checks,
  evaluation harness for agent trajectories.

## Phase 6 — Multimodal
- Medical/lab report extraction (PDF/image → structured fields) with
  human confirmation before any prediction; OCR/vision model evaluation;
  confidence gating and audit trail.

## Phase 7 — Healthcare interoperability (FHIR / MCP)
- FHIR resources (Observation, Patient, RiskAssessment) on synthetic data
  (Synthea); possibly SMART on FHIR.
- MCP server exposing read-only tools (assess, explain, history).

## Phase 8 — Production hardening
- Docker + docker-compose, CI/CD (lint, typecheck, tests, image build).
- OpenTelemetry traces/metrics, audit logging, authn/authz (OAuth2/OIDC),
  rate limiting, secrets management, WAF, backups.
- Cloud deployment (IaC), monitoring/alerting, drift detection feeding back
  into Phase 1 retraining loop.

## Cross-cutting sequencing rules
1. No phase begins until the previous phase's tests are green.
2. Model-behavior changes require updating `tests/test_legacy_model.py` pins
   consciously (never silently).
3. Every phase updates `docs/current-architecture.md` to match reality.
4. No new technology is added without a documented reason in the phase notes.
