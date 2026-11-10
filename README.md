# Remedy AI

**Understand the estimate. Keep the human in charge.**

Remedy AI is an educational cardiovascular decision-support prototype. It combines a calibrated machine-learning estimate, per-assessment feature contributions, and optional source-grounded health information in one reviewable workflow.

> **Research prototype — not for clinical use.** Results are statistical estimates, not diagnoses or medical advice. The model has not been clinically validated. It was trained on a small, historical 303-row dataset. Read the [limitations](docs/limitations.md) and [model card](docs/model-card.md) before interpreting results.

## Product principles

- **One result, with its reasoning:** show the estimate alongside model contributions, not as a diagnosis.
- **Human review before action:** extracted report values require explicit confirmation before assessment.
- **Clear boundaries:** optional AI guidance is distinct from model output, requires configured providers, and cites retrieved sources.
- **Simple product, explicit systems:** assessments, history, reports, model status, and exports use the same authenticated API and ownership rules.
- **No invented certainty:** unavailable services and limitations should be visible; a score is not a clinical confidence guarantee.

## What works

| Capability | Current behavior |
| --- | --- |
| Risk estimate | Calibrated scikit-learn pipeline; probability semantics are `P(disease)`. |
| Explanation | Per-assessment feature contributions, described as model contributions—not causes. |
| Accounts | Registration/login, Argon2 password hashing, session cookies, CSRF, rate limits, and ownership scoping. |
| Report review | PDF/image extraction flow with user confirmation before values can seed an assessment. |
| AI health information | Optional RAG/LLM guidance with retrieved-source citation checks. Requires configured providers and knowledge ingestion; live provider validation is not claimed here. |
| History and interoperability | Assessment history, read-only FHIR R4 export, and a scoped read-only MCP server. |
| Operations | Docker Compose services, migrations, tests, CI, and opt-in OpenTelemetry. |

## Architecture

```text
Browser
  └─ Next.js 16 · TypeScript · App Router
       └─ FastAPI · typed JSON API · cookie sessions
            ├─ PostgreSQL + pgvector · SQLAlchemy · Alembic
            ├─ Redis · sessions / rate limits
            ├─ ML pipeline · scikit-learn · SHAP explanations
            └─ Optional RAG / LLM guidance · retrieved evidence + checked citations

Private report storage: local development or S3-compatible storage
```

The supported product frontend is `frontend/`; the root `app.py` Flask app and root-level pickle artifacts are legacy regression material, not the modern API or model service.

## Technology

- **Web:** Next.js 16, React 19, TypeScript, Tailwind CSS, shadcn/ui, Vitest
- **API:** Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, Alembic
- **ML:** scikit-learn pipeline, sigmoid calibration, SHAP, MLflow tracking
- **Services:** PostgreSQL/pgvector, Redis, Docker Compose; optional S3-compatible storage and OpenTelemetry

## Run locally

Requirements: Python 3.12+, Node.js 22+, and Docker.

```bash
# Start PostgreSQL/pgvector and Redis
docker compose up -d postgres redis

# Configure local secrets and database settings
cp .env.example .env
# Set SECRET_KEY, DATABASE_URL / POSTGRES_PASSWORD, and TEST_DB_PASSWORD as needed.

# Install and start the API
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn backend.app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local               # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                               # http://localhost:3000
```

### Optional AI guidance

Configure `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `LLM_API_KEY`, and `LLM_MODEL` in `.env`, then ingest the declared knowledge sources:

```bash
python scripts/ingest_knowledge.py
```

Without providers, the core assessment app remains usable and guidance reports that it is unavailable. Automated tests use fakes; they do not establish live-provider quality.

## Model facts and limits

- Training data: 303 rows from a historical UCI-derived heart-disease dataset; see [`ml/data/README.md`](ml/data/README.md) for provenance and target encoding.
- Evaluation: stratified train/test split, five-fold CV on training data, calibration and subgroup reporting. Review the [model card](docs/model-card.md) for actual metrics.
- The dataset is small and old, subgroup estimates are noisy, and there is no external or prospective validation. Do not use the reported metrics to make patient-care decisions.
- A displayed probability or threshold band is not a calibrated measure of an individual’s clinical risk or the model’s uncertainty.
- This project does not claim production clinical readiness, regulatory approval, HIPAA/GDPR compliance, multi-tenant isolation, high availability, or completed security audit.

## Tests

```bash
# Python
python -m pytest tests backend/tests -q

# Frontend
cd frontend
npm run typecheck
npm test
npm run build
```

CI also runs lint, focused backend tests, frontend checks, Docker builds, and smoke tests.

## Project map

```text
backend/app/       FastAPI API, services, auth, reports, RAG, storage, FHIR
backend/tests/     Backend tests
frontend/          Next.js application and UI
ml/                Training, preprocessing, inference, evaluation, explanations
models/v2/         Versioned modern model artifacts
rag/               Knowledge-source manifest
mcp/               Scoped read-only MCP server
alembic/            Database migrations
scripts/            Dataset, ingestion, and validation utilities
docs/               Architecture, deployment, model card, limitations
```

Further reading: [deployment](docs/deployment.md) · [architecture](docs/final-architecture.md) · [security](docs/auth-security.md) · [RAG](docs/rag-architecture.md) · [report ingestion](docs/report-ingestion.md) · [FHIR/MCP](docs/fhir-mcp.md).

## License

MIT. See [LICENSE](LICENSE) if present in your checkout.
