# Remedy-AI — AI-Assisted Cardiovascular Health Assessment.

An **educational/research prototype**: a full-stack, AI-assisted cardiovascular
health **decision-support** system. A machine-learning model estimates a
probability that the disease class applies to the provided features, explains
that estimate, and — only on explicit request — generates health *information*
grounded in retrieved guideline sources.

> ⚠️ **This is not a medical product.** Outputs are model estimates, **not
> diagnoses**, and are **not clinically validated risk scores**. Nothing here is
> medical advice. See [docs/limitations.md](docs/limitations.md).

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.11x-green)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](#license)

---

## What it does

| Capability | Status | Notes |
| --- | --- | --- |
| ML risk estimate | ✅ Working | Calibrated logistic-regression pipeline (v2), SHAP explanations |
| User accounts | ✅ Working | Register/login, Argon2 hashing, Redis-backed sessions, CSRF, ownership scoping |
| Explanations | ✅ Working | SHAP contributions per assessment |
| AI guidance (RAG + LLM) | ⚙️ Code complete | Requires a pgvector database + an OpenAI-compatible embedding/LLM provider; degrades gracefully without |
| LangGraph guidance workflow | ⚙️ Code complete | Same provider requirement; falls back to the direct path |
| Medical report upload | ✅ Working | Image/PDF ingestion, extraction review, human confirmation before any prediction |
| FHIR R4 export | ✅ Working | Read-only Observation/Patient resources, explicitly marked non-diagnostic |
| MCP server | ✅ Working | Read-only, single-user, token-scoped access to one account's assessments |
| Storage | ✅ Working | Local disk (dev) or any S3-compatible store with presigned URLs |
| Telemetry | ⚙️ Opt-in | OpenTelemetry spans; only operational attributes, never medical data |

**Honest AI status:** the RAG/LLM/LangGraph layers are fully implemented and
covered by tests with fakes, but live provider validation (real embedding +
LLM endpoints) is **pending** in the current environment — no provider keys are
configured. The system is designed to degrade gracefully: AI guidance simply
reports that it is unavailable.

---

## Architecture

```text
                     ┌────────────────────────────┐
   Browser ────────▶ │  Next.js 16 frontend       │  :3000
                     │  app router, TS strict     │
                     └─────────────┬──────────────┘
                                   │ typed client, cookie sessions (credentials: include)
                                   ▼
                     ┌────────────────────────────┐
                     │  FastAPI backend           │  :8000
                     │  ├ /health  /ready         │
                     │  ├ /api/v1/auth/*          │  register/login/logout/me/csrf
                     │  ├ /api/v1/assessments/*   │  create, list, get, explanation, guidance
                     │  ├ /api/v1/reports/*       │  upload, list, get, confirm
                     │  └ /api/v1/fhir/*          │  read-only R4 export
                     └──────┬──────────┬──────────┘
                            │          │
             ┌──────────────▼──┐   ┌───▼──────────────┐
             │ PostgreSQL 18   │   │     Redis 7      │
             │ + pgvector      │   │  cache / limiter │
             └─────────────────┘   └──────────────────┘

   ML: models/v2/cardio_risk_pipeline.joblib (sklearn Pipeline,
   calibrated, loaded once) + SHAP background sample
   Reports: local disk or S3-compatible private bucket (presigned URLs)
```

### Request flow for AI guidance (when providers are configured)

```text
assessment ─▶ build retrieval query ─▶ pgvector cosine search
          ─▶ evidence chunks ─▶ LLM (structured output, temperature 0.2)
          ─▶ Pydantic validation ─▶ citation verification
          ─▶ (LangGraph workflow: retrieve → draft → verify → finalize)
          ─▶ final guidance with cited sources
```

---

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pydantic-settings,
  Argon2 (pwdlib), pgvector, Redis, boto3 (S3), OpenTelemetry (opt-in)
- **ML:** scikit-learn 1.7 (v2 pipeline: ColumnTransformer → LogisticRegression
  → sigmoid calibration), SHAP, MLflow tracking
- **Frontend:** Next.js 16 (app router), TypeScript strict, Tailwind, shadcn/ui,
  Vitest
- **Infra:** Docker (multi-stage, non-root), docker-compose (Postgres+pgvector,
  Redis, MinIO profile), GitHub Actions CI

## ML pipeline

- Dataset: UCI-derived heart dataset (303 rows), SHA-256-verified provenance
  (`ml/data/`). **Known limitation:** small, single-cohort, older era — see
  [docs/limitations.md](docs/limitations.md).
- Split-first training (stratified 80/20, test locked), 5-fold CV on train
  only, sigmoid calibration, documented selection policy, subgroup evaluation.
- Target semantics are explicitly corrected and documented: the model
  estimates `P(disease)`; every artifact and API response restates this.
- Artifacts: `models/v2/*.joblib`, `metadata.json`, `metrics.json`.
- The legacy Flask app (`app.py`) and root-level `.pkl` models are kept only
  for historical regression comparison and are **not** part of the modern stack.

## RAG + LangGraph

- Knowledge ingestion: manifest (`rag/sources.yaml`) → fetch → chunk → embed →
  pgvector store (idempotent, model-stamped).
- Retrieval: cosine similarity with a configurable top-k and minimum
  similarity; the query is stripped of emergency vocabulary by a safety layer.
- Generation: OpenAI-compatible chat endpoint, low temperature, structured
  output validated against a strict schema; citations must match retrieved
  sources or the guidance is refused.
- Workflow: LangGraph orchestrates retrieve → draft → verify → finalize; a
  direct path is used when LangGraph is not installed.
- Safety: refusal patterns for diagnosis/prescription requests; emergency
  guidance always routes to professional care.

## Multimodal reports

Upload an image or PDF lab report → extraction with a vision-capable model →
**human review screen** → confirmed values may seed an assessment. No report
ever changes a result without explicit confirmation. Files live in a private
bucket (or local dir in dev) and are read via short-lived presigned URLs.

## FHIR + MCP

- **FHIR R4:** read-only export of an assessment as Observation + Patient
  resources, explicitly annotated "not a diagnosis".
- **MCP:** a read-only Model Context Protocol server bound to exactly one user
  ID, exposing that account's assessments to MCP clients. Refuses to start
  unscoped.

## Authentication & security

- Session cookies (HttpOnly; `__Host-` prefix support), CSRF double-submit,
  generic auth failures (anti-enumeration), Redis fixed-window rate limiting,
  ownership scoping on every query, security headers/HSTS in production,
  fail-fast production config validation (no wildcard CORS, `SECRET_KEY`
  required, `COOKIE_SECURE=true` enforced).

---

## Quick start (local)

Prerequisites: Python 3.12+, Node 22+, Docker (for Postgres/Redis).

```bash
# 1. Infrastructure (Postgres + pgvector, Redis)
docker compose up -d postgres redis

# 2. Environment
cp .env.example .env
#    → set SECRET_KEY (python -c "import secrets; print(secrets.token_urlsafe(48))")
#    → set DATABASE_URL / POSTGRES_PASSWORD to matching values
#    → set TEST_DB_PASSWORD if you run backend tests

# 3. Backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn backend.app.main:app --reload --port 8000

# 4. Frontend
cd frontend
npm ci
cp .env.example .env.local          # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                          # http://localhost:3000
```

### Optional: enable AI guidance (RAG/LLM)

Set in `.env` (any OpenAI-compatible provider):

```text
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=...
LLM_API_KEY=...
LLM_MODEL=...
```

Then ingest the knowledge base and restart:

```bash
python scripts/ingest_knowledge.py
```

Without these variables the app works fine — AI guidance just reports that it
is unavailable.

### Docker (full stack)

```bash
cp .env.example .env    # fill in required values (see docs/deployment.md)
docker compose up -d --build
docker compose exec backend alembic upgrade head
# optional local S3: docker compose --profile storage up -d
```

Full variable reference and production checklist:
[docs/deployment.md](docs/deployment.md).

---

## Project structure

```text
├── backend/app/          FastAPI app (api, services, rag, llm, agents, reports, fhir, storage, db, core)
├── backend/tests/        Backend test suite
├── frontend/             Next.js app (app/, components/, lib/, tests/)
├── ml/                   Modern training/inference/explainability package
├── models/v2/            Production artifacts (tracked, versioned)
├── mcp/                  Read-only MCP server
├── rag/                  Knowledge source manifest
├── alembic/              Migrations (incl. pgvector)
├── scripts/              Ingestion, smoke tests, dataset verification
├── docs/                 Architecture, deployment, limitations
├── app.py                Legacy Flask app (regression comparison only)
├── docker-compose.yml    Postgres+pgvector / Redis / backend / frontend / MinIO
└── .github/workflows/    CI (lint, tests, typecheck, Docker build + smoke)
```

---

## Documentation

| Doc | Content |
| --- | --- |
| [docs/final-architecture.md](docs/final-architecture.md) | End-state architecture across all phases |
| [docs/deployment.md](docs/deployment.md) | Docker, configuration, production checklist |
| [docs/limitations.md](docs/limitations.md) | Honest limitations (data, model, AI, security) |
| [docs/model-card.md](docs/model-card.md) | Model details and evaluation |
| [docs/auth-security.md](docs/auth-security.md) | Auth/session/CSRF design |
| [docs/rag-architecture.md](docs/rag-architecture.md) | RAG ingestion + retrieval design |
| [docs/langgraph-architecture.md](docs/langgraph-architecture.md) | Guidance workflow |
| [docs/report-ingestion.md](docs/report-ingestion.md) | Multimodal report flow |
| [docs/fhir-mcp.md](docs/fhir-mcp.md) | Interoperability surfaces |

## Testing

```bash
.venv/Scripts/python -m pytest tests backend/tests -q   # backend (see pytest.ini)
cd frontend && npm run typecheck && npm test && npm run build
```

CI runs lint, focused backend tests, frontend lint/typecheck/build, and builds
+ smoke-tests both Docker images on every push/PR to `main`.

---

## Limitations (read this)

- **Educational/research prototype.** Not a medical device; no clinical
  validation; not approved for any clinical use.
- Model outputs are **statistical estimates**, not diagnoses.
- The training dataset is small (303 rows), single-cohort, and dated; subgroup
  fairness is reported but not guaranteed out of distribution.
- AI-generated guidance is **evidence-grounded general health information**,
  not medical advice; it requires configured external providers and can be
  unavailable or wrong.
- Reports and assessments are stored **as configured**; deployers are
  responsible for encryption-at-rest, access control, and any applicable
  health-data regulation (HIPAA/GDPR).

Full list: [docs/limitations.md](docs/limitations.md).

## License

MIT — see the license header in the repository.
