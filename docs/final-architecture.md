# Final Architecture (Phase 10 — end state)

The system as it exists after Phases 0–10. This is the authoritative overview;
phase-specific deep dives remain in their own docs and are listed at the end.

## System overview

```text
                 ┌────────────────────────────┐
  Browser ─────▶ │  Next.js 16 frontend       │ :3000
                 │  app router, TS strict     │
                 └─────────────┬──────────────┘
                               │ typed client (lib/api.ts), cookie sessions,
                               │ credentials: "include", CSRF header on unsafe methods
                               ▼
                 ┌────────────────────────────┐
                 │  FastAPI backend           │ :8000
                 │  ├ /health  /ready         │   operational probes (root)
                 │  ├ /api/v1/auth/*          │   register/login/logout/me/csrf
                 │  ├ /api/v1/assessments/*   │   create · list · get · explanation · guidance
                 │  ├ /api/v1/reports/*       │   upload · list · get · confirm
                 │  └ /api/v1/fhir/*          │   read-only R4 export
                 └──────┬──────────┬──────────┘
                        │          │
         ┌──────────────▼───┐  ┌───▼──────────────┐
         │ PostgreSQL 18    │  │     Redis 7      │
         │ + pgvector       │  │  cache/limiter   │
         │ users, sessions, │  └──────────────────┘
         │ assessments,     │
         │ reports,         │   Report bytes ─▶ S3-compatible private bucket
         │ knowledge_*,     │   (or data/reports locally; presigned reads)
         │ embeddings       │
         └──────────────────┘

  ML inference : models/v2/cardio_risk_pipeline.joblib (sklearn Pipeline,
                 calibrated, loaded once at startup) + SHAP background sample
  Guidance     : RAG (pgvector) → LLM (OpenAI-compatible) → validation →
                 LangGraph workflow (fallback: direct path)
  Telemetry    : OpenTelemetry spans (opt-in; operational attributes only)
```

## Backend layers

| Layer | Location | Responsibility |
| --- | --- | --- |
| API | `backend/app/api/v1/` | Routers, auth/session/CSRF dependencies, error contract |
| Services | `backend/app/services/` | Business logic (assessments, sessions, rate limiting) |
| ML serving | `ml/inference/` | v2 predictor + SHAP; loaded once per process |
| RAG | `backend/app/rag/` | Embeddings provider, retrieval, safety filter |
| LLM | `backend/app/llm/` | OpenAI-compatible chat client, prompts, validation |
| Workflow | `backend/app/agents/` | LangGraph guidance workflow |
| Reports | `backend/app/reports/` | Multimodal ingestion + extraction + confirmation flow |
| Storage | `backend/app/storage/` | `local` and `s3` backends behind one protocol |
| FHIR | `backend/app/fhir/` | Read-only R4 mapper (explicitly non-diagnostic) |
| DB | `backend/app/db/` | SQLAlchemy models, Alembic-migrated schema |
| Core | `backend/app/core/` | Settings (fail-fast production validation), logging, errors |

Error contract: every error is a JSON envelope with `error.code`,
`error.message`, and a `request_id` for correlation; the frontend `ApiError`
class mirrors it.

## Frontend structure

- `app/` — routes: `/`, `/assessment`, `/results/[id]`, `/history`, `/report`,
  `/report/[id]`, `/login`, `/register`.
- `lib/api.ts` — the only place that talks HTTP; typed against `types/api.ts`.
- `lib/auth.ts` / `lib/use-auth.tsx` — session auth helpers + `RequireAuth`.
- `components/` — assessment form, results (gauge, contributions, AI guidance),
  history (cards/table), report (uploader/review), layout.

## Data model (PostgreSQL, Alembic-managed)

`users`, `sessions` (Redis holds the TTL cache), `assessments` (ownership
scoped), `medical_reports` + extractions (status: uploaded → extracted →
reviewed/confirmed → prediction seeded), `knowledge_documents` +
`knowledge_chunks` (pgvector embeddings, model-stamped).

## Model serving contract

- `MODEL_VERSION=v2` (default). The v2 artifact is a single sklearn Pipeline
  whose output is `P(disease)` — semantics corrected and documented at every
  boundary (artifact metadata, API schema, FHIR note, MCP tool description).
- The legacy Flask app (`app.py`) and root `.pkl` files exist **only** for
  Phase 0 regression comparison; they are not part of the modern stack and not
  routed behind the API.

## Security posture

Argon2 password hashing · HttpOnly session cookies (`__Host-` option) · CSRF
double-submit tokens · generic auth failures · Redis fixed-window rate limits ·
per-user ownership scoping on every query · production fail-fast config
validation (no wildcard CORS, `SECRET_KEY` required, `COOKIE_SECURE=true`,
`LOG_LEVEL=DEBUG` refused) · HSTS in production · private bucket + presigned
URLs for reports · telemetry allowlist that never records medical data.

## Phase docs

| Doc | Phase |
| --- | --- |
| `docs/legacy-ml-baseline.md` | 0 — verified legacy behavior |
| `docs/ml-modernization-results.md`, `docs/model-card.md` | 1 — modern pipeline |
| `docs/backend-architecture.md` | 2 — FastAPI |
| `docs/frontend-architecture.md` | 3 — Next.js |
| `docs/rag-architecture.md` | 4 — RAG + LLM |
| `docs/langgraph-architecture.md` | 5 — LangGraph workflow |
| `docs/auth-security.md` | 6 — auth, sessions, CSRF |
| `docs/report-ingestion.md` | 7 — multimodal reports |
| `docs/fhir-mcp.md` | 8 — FHIR + MCP |
| `docs/deployment.md` | 9 — Docker, S3, telemetry, CI |
| `docs/limitations.md` | 10 — honest limitations |
