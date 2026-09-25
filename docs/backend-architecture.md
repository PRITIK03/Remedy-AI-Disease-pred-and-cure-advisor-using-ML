# Backend Architecture (Phase 2 — as implemented)

API-first backend built around the Phase 1 ML foundation. The old Flask app
remains functional for regression compatibility; FastAPI is the future
primary backend.

```text
Next.js frontend (Phase 3 — planned, not implemented)
        ↓
FastAPI (backend/app/main.py)
   ├── request-ID + structured-logging middleware
   ├── CORS (configuration-driven; wildcard refused in production)
   ├── centralized exception handlers (no stack traces in responses)
        ↓
API v1 routers (backend/app/api/v1/)
   ├── /health, /ready        (operational, at root)
   └── /api/v1/assessments    (business, versioned)
        ↓
Pydantic schemas (backend/app/schemas/)
   AssessmentCreate: strict, 13 explicit typed fields, ranges + categorical
   Literals, extra="forbid"
        ↓
Service layer (backend/app/services/)
   ├── model_service.py        → wraps ml.inference.predictor (loaded ONCE
   │                              at startup; no per-request artifact loads;
   │                              ml package remains owner of all ML logic)
   ├── assessment_service.py   → predict + persist + paginated queries
   └── redis_service.py        → health ping + 60s model-metadata cache
        ↓
SQLAlchemy 2.0 (backend/app/db/)
   Assessment, User ORM models (UUID PKs, timestamps, indexes)
        ↓
PostgreSQL (psycopg 3 driver)          Redis (redis-py async)
   via Alembic migrations               health + short-lived cache only;
                                        NEVER patient assessments
```

## Database schema

- `assessments`: UUID PK, 13 explicit feature columns (age, sex, cp,
  trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal),
  model_version, predicted_disease, disease_probability Numeric(6,5),
  selected_model, extra_metadata JSON, created_at/updated_at; indexes on
  age, created_at, model_version, predicted_disease.
- `users`: UUID PK, email (unique), display_name, is_active, timestamps.
  No credentials column — authentication is a later phase (no security
  theater).

## Health & readiness

- `GET /health` → liveness: `{"status","app_env","model_version"}`
- `GET /ready` → structured per-dependency status:
  `{"status":"ready|not_ready","services":{"database","redis","model"}}`
  Database = SELECT 1; Redis = PING; model = loaded artifact in app state.
  Never exposes connection strings; never raises.

## Logging & request IDs

- One JSON line per log record (timestamp, level, logger, message,
  request_id, method, path, status_code, latency_ms, model_version).
- Middleware assigns/propagates `X-Request-ID` (echoed in responses).
- Never logged: full medical inputs, secrets, API keys, personal data.

## CORS

`CORS_ORIGINS` env var (comma-separated explicit origins, default
`http://localhost:3000`). `*` is refused when `APP_ENV=production`.

## Redis usage (deliberately minimal)

- health ping for `/ready`,
- read-through 60s cache of model metadata.
- explicitly NOT used for assessment caching (privacy/consistency).
- async client closed on shutdown.

## Local running experience

```bash
docker compose up -d            # PostgreSQL + Redis (if Docker available)
alembic upgrade head            # apply migrations
.venv/Scripts/python -m uvicorn backend.app.main:app --reload
# → http://localhost:8000/docs  |  /health  |  /ready
```

If Docker is unavailable (e.g. this machine uses a native PostgreSQL 18
service), point `DATABASE_URL` at the local instance and run migrations the
same way. Redis is optional: the API degrades gracefully and `/ready`
reports `redis: unavailable`.

## Planned (NOT implemented in Phase 2)

Next.js frontend, authentication/authorization (users table ready), rate
limiting, RAG/LLM advice, LangGraph agents, FHIR/MCP, multimodal extraction,
Kubernetes, CI/CD, OpenTelemetry.
