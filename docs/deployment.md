# Deployment Guide (Phase 9)

Production hardening and deployment foundations for Remedy-AI.

> ⚠️ **Remedy-AI is an educational prototype.** Its outputs are model estimates,
> not medical diagnoses, and they are not clinically validated risk scores. Do
> not deploy it as a diagnostic device or use it for real patient care.

---

## 1. Architecture

```
                 ┌──────────────────────┐
  Browser ──────▶│  frontend (Next.js)  │  :3000
                 └───────────┬──────────┘
                             │  NEXT_PUBLIC_API_URL (public, no secrets)
                             ▼
                 ┌──────────────────────┐
                 │  backend (FastAPI)   │  :8000
                 │  ├ ML prediction     │  scikit-learn, loaded once
                 │  ├ RAG + LLM         │  degrades gracefully if unset
                 │  ├ Report ingestion  │
                 │  └ Auth / FHIR R4    │
                 └──────┬────────┬──────┘
                        │        │
          ┌─────────────▼──┐  ┌──▼─────────────┐
          │ PostgreSQL 18  │  │     Redis 7    │
          │  + pgvector    │  │  sessions/cache│
          └────────────────┘  └────────────────┘

          Report bytes ──▶ S3-compatible object storage (private bucket)
          Traces      ──▶ OTLP collector (optional, opt-in)
```

| Service | Image | Purpose |
| --- | --- | --- |
| `backend` | built from `backend/Dockerfile` | FastAPI API |
| `frontend` | built from `frontend/Dockerfile` | Next.js standalone server |
| `postgres` | `pgvector/pgvector:pg18` | Primary store + vector index |
| `redis` | `redis:7-alpine` | Sessions and short-lived cache |
| `minio` | `minio/minio` (profile `storage`) | Optional local S3 for development |

---

## 2. Quick start

```bash
cp .env.example .env        # then fill in the required values (section 4)
docker compose up -d --build
curl -fsS http://localhost:8000/health
```

For local S3-compatible storage, add the `storage` profile:

```bash
docker compose --profile storage up -d
```

`minio-init` creates the bucket once and explicitly denies anonymous access.

Apply schema migrations after the database is healthy:

```bash
docker compose exec backend alembic upgrade head
```

---

## 3. Container images

Both images are multi-stage, run as non-root, and contain no secrets.

**Backend** (`backend/Dockerfile`, build context = repository root)

- Builder stage compiles dependencies into `/opt/venv`; the runtime stage is
  `python:3.12-slim` with no build toolchain.
- Runs as uid `10001` (`remedy`); application code is read-only.
- Health check hits `/health` (liveness only) so a slow database never
  restarts the container.
- `CMD` runs a single `uvicorn` worker with `--no-access-log`, because the app
  emits its own structured JSON logs. Scale with replicas, not workers.


---

## 4. Configuration

All secrets come from the environment. Never commit a real `.env`; it is
gitignored, and CI fails the build if a secret-bearing file is ever tracked.

### Required in production

| Variable | Notes |
| --- | --- |
| `SECRET_KEY` | ≥ 32 chars of high-entropy material. Signs cookies and CSRF tokens. |
| `DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://host:6379/0` |
| `COOKIE_SECURE` | Must be `true`; startup fails otherwise. |
| `CORS_ORIGINS` | Comma-separated explicit origins. `*` is refused in production. |
| `S3_BUCKET` | Required when `STORAGE_BACKEND=s3`. |

`POSTGRES_PASSWORD`, `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` are also
required by the Compose file via `${VAR:?message}`, so Compose refuses to start
rather than booting with an empty password.

### Report storage

`STORAGE_BACKEND` selects the implementation. `local` remains the default so
existing development setups are unaffected.

| `STORAGE_BACKEND` | When to use |
| --- | --- |
| `local` | Single container, no redeploys, non-sensitive data. **Files are lost on redeploy.** |
| `s3` | Any real or multi-instance deployment. |

S3 options: `S3_ENDPOINT_URL` (empty → AWS S3), `S3_REGION`, `S3_BUCKET`,
`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ADDRESSING_STYLE`
(`path` for MinIO, `virtual` for AWS), `S3_SERVER_SIDE_ENCRYPTION`
(`AES256` or `aws:kms`), `S3_KMS_KEY_ID`, `S3_PRESIGNED_EXPIRY_SECONDS`.

**Leave the access-key pair empty in production** to use the pod's IAM role or
workload identity. That is preferred over static keys. The bucket must stay
private — the app reads objects through short-lived presigned URLs, never
public links.

### AI providers (optional)

`LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` and `EMBEDDING_API_BASE` /
`EMBEDDING_API_KEY` / `EMBEDDING_MODEL` accept any OpenAI-compatible endpoint
(OpenRouter, OpenAI, Ollama, vLLM). When the keys are unset the API still
boots and serves predictions; guidance and RAG return an explicit
"unavailable" response rather than an error. A startup warning records this,
and CI deliberately tests that unconfigured path.

Changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSION` requires re-running
ingestion: the database stores the model name per document, and the pgvector
column width must match the new dimension.

### Telemetry (optional)

`OTEL_ENABLED` and `OTEL_EXPORTER_OTLP_ENDPOINT` (OTLP/HTTP base URL). With
both unset, spans are created but dropped, so telemetry costs nothing.

**What is recorded:** HTTP method, route template, status code, latency,
error type, service name, environment.

**What is never recorded:** request or response bodies, report contents,
clinical values, passwords, tokens, API keys, cookies, session identifiers, or
raw query strings. `backend/app/telemetry.py` enforces this two ways: an
explicit span-attribute allowlist, and a URL scrubber that keeps only the path
(discarding scheme, host, and query string entirely).

---

## 5. Health and readiness

| Endpoint | Purpose | Checks |
| --- | --- | --- |
| `GET /health` | Liveness | Process is up. Used by the container `HEALTHCHECK`. |
| `GET /ready` | Readiness | Database, Redis, ML model, storage. |

`/ready` returns `status: "ready"` only when every dependency is healthy;
otherwise `not_ready` with a per-service status. Point your orchestrator's
readiness probe at `/ready` and its liveness probe at `/health` so a database
blip drains traffic without triggering a restart loop.

---

## 6. Database, pgvector, and frontend images

The Compose stack uses `pgvector/pgvector:pg18` and runs
`scripts/docker/postgres-init.sql` on first boot to `CREATE EXTENSION vector`.
The init script only runs when the volume is empty; on an existing volume:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The `vector` column dimension must match the configured embedding model. A
mismatch produces insert failures, so changing embedding models requires a
migration.

**Frontend** (`frontend/Dockerfile`)

- `output: "standalone"` in `next.config.ts` produces a minimal server.
- Runs as uid `1001` (`nextjs`).
- Only `NEXT_PUBLIC_*` values are baked in at build time. No `.env` file is
  copied into any image — `.dockerignore` enforces this.


---

## 7. Production checklist

- [ ] `APP_ENV=production`
- [ ] `SECRET_KEY` is 32+ random characters, unique per environment
- [ ] `COOKIE_SECURE=true`, TLS terminated in front of both services
- [ ] `CORS_ORIGINS` lists only real frontends; no `*`
- [ ] `LOG_LEVEL=INFO` (the app refuses `DEBUG` in production)
- [ ] `STORAGE_BACKEND=s3` with a private, encrypted, versioned bucket
- [ ] S3 credentials come from an IAM role, not static keys
- [ ] `POSTGRES_PASSWORD` and provider keys supplied by a secret manager
- [ ] Database backups scheduled and a restore rehearsed
- [ ] `/ready` wired as the readiness probe; `/health` as the liveness probe
- [ ] Container images scanned; both run as non-root
- [ ] `docker compose config` reviewed before the first deploy

---

## 8. CI

`.github/workflows/ci.yml` runs on every push and pull request:

- **backend** — `ruff check`, `compileall`, `pytest`, plus a check that an
  insecure production configuration is rejected
- **frontend** — `npm run lint`, `npm run typecheck`, `npm run build`
- **security** — fails if a secret-bearing file is tracked, and scans tracked
  source for credential patterns

No workflow requires or references a secret. Provider keys are explicitly set
to empty strings so the "AI unavailable" path is what CI exercises.

---

## 9. Scaling notes

- Scale the backend with **replicas**, not multiple uvicorn workers: the ML
  model is loaded once per process, so workers multiply memory for no gain.
- With more than one replica, `STORAGE_BACKEND=local` is unsafe — uploads land
  on whichever container received them. Use `s3`.
- Sessions live in Redis, so replicas are stateless with respect to auth.
- Rate limiting is Redis-backed and therefore consistent across replicas.

Both images ship a `HEALTHCHECK`; Compose also defines matching health checks
so dependent services wait for readiness.
