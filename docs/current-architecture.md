# Current Architecture (after Phase 4 — as actually implemented)

This documents what exists **today**, after Phases 0–4. Phase-specific deep
dives: `docs/backend-architecture.md` (Phase 2),
`docs/frontend-architecture.md` (Phase 3), `docs/rag-architecture.md`
(Phase 4). Planned-but-unbuilt items are listed at the end and must not be
read as implemented.

## System overview (Phases 2–4)

```text
Next.js 16 frontend (app router, TypeScript strict)
   ↓  typed API client (lib/api.ts; NEXT_PUBLIC_API_URL)
FastAPI (backend/app/main.py)
   ├── /health, /ready
   └── /api/v1/assessments (+/{id}, /{id}/explanation, POST /{id}/guidance)
         ↓                          ↓
ModelService (v2 predictor)   Guidance flow (Phase 4):
   loaded once at startup       assessment → retrieval query → pgvector
   SHAP explain() hook          cosine search → evidence → LLM (structured)
         ↓                      → Pydantic validation → citation check
PostgreSQL (assessments, users, knowledge_documents, knowledge_chunks)
Redis (health + 60s metadata cache only)
   ↓
ml.inference.predictor (models/v2/cardio_risk_pipeline.joblib — unchanged)
```

The legacy Flask app (app.py) remains runnable for regression comparison;
the rule-based `get_remedies()` is superseded in the modern stack by the
Phase 4 evidence-grounded guidance endpoint (rules are not wired into the
modern API).

```text
Browser (legacy single-page HTML form — unchanged by design)
   ↓  POST /predict (form-encoded)
Flask 3.x app (app.py)
   ↓
parse_features(): required-field checks + casts + soft range validation
   ↓
Model-provider selection via MODEL_VERSION env var:
   ├─ v2 (default)  → ml.inference.predictor.Predictor
   │                    loads ONE artifact: models/v2/cardio_risk_pipeline.joblib
   │                    (ColumnTransformer + LogisticRegression + sigmoid
   │                     calibration, all inside the serialized object)
   │                    returns disease_probability = P(disease)  ✅ correct
   │                    semantics; explain() hook available (SHAP, member-
   │                    averaged, train-split background)
   └─ v1            → legacy path: scaler.pkl → VotingClassifier.predict_proba()[:,1]
                    → P(healthy) labeled as "risk" ⚠ documented inversion,
                      kept ONLY for regression comparison
   ↓
Legacy rule-based get_remedies() (unchanged; LLM/RAG replacement deferred)
   ↓
render_template("index.html", result, remedies)
   ↓
HTML response
```

## ML training architecture (new in Phase 1)

```text
ml/data/heart.csv (303 rows, SHA-256 verified, provenance documented)
   ↓  load_data(): hash check + target flip (y_modern = 1 − y_source)
split-first: stratified train/test 80/20 (test LOCKED, seed=42)
   ↓
ml/training/models.py candidates (Pipeline = preprocessor ∘ classifier):
   logistic_regression | random_forest | hist_gradient_boosting
   ↓
StratifiedKFold(5) CV on TRAIN ONLY (leakage-free by construction)
   ↓
CalibratedClassifierCV(sigmoid, internal 5-fold) per candidate (TRAIN only)
   ↓
Selection: CV ROC-AUC → calibration → parsimony (documented policy)
   ↓
Final fit on TRAIN → locked test evaluation (full metrics, subgroups,
   curves) → SHAP explainability (global + local)
   ↓
Artifacts:
   models/v2/cardio_risk_pipeline.joblib   ← ONE production artifact
   models/v2/metadata.json                 ← version, seeds, hashes, versions
   models/v2/metrics.json                  ← CV/calibration/test/subgroups
   models/v2/background_sample.joblib      ← 80 TRAIN rows for inference SHAP
   ml/artifacts/evaluation.json            ← machine-readable evaluation
   mlflow.db (sqlite)                      ← experiment tracking (cardio-risk)
```

## Configuration surface

| Env var          | Default      | Purpose                                   |
|------------------|--------------|-------------------------------------------|
| `MODEL_VERSION`  | `v2`         | model generation served by /predict       |
| `MODEL_DIR`      | repo root    | legacy .pkl directory (v1 mode)           |
| `TEMPLATE_FOLDER`| repo root    | index.html location                       |
| `HOST`/`PORT`/`FLASK_DEBUG` | 127.0.0.1/5000/0 | dev server                  |
| `LOG_LEVEL`      | INFO         | logging verbosity                         |
| `RISK_THRESHOLD` | 0.5          | High/Low cutoff (both model generations)  |

## Environments

| Environment       | Python  | Purpose                                       |
|-------------------|---------|-----------------------------------------------|
| System Python     | 3.10.11 | legacy artifacts + Phase 0 regression tests   |
| `.venv`           | 3.14.7  | modern stack (sklearn 1.7.2, mlflow, shap)    |

Legacy pickles load under **both** environments (warned but verified
deterministic; see docs/dependency-audit.md).

## Implemented vs planned

**Implemented (verified by tests):** the ML training/inference flows,
model-provider abstraction, corrected semantics, calibration, CV, SHAP
explainability, MLflow tracking, dataset provenance; FastAPI backend with
assessments + explanation + guidance endpoints, PostgreSQL (Alembic
migrations incl. pgvector tables), Redis caching; Next.js frontend with
dashboard/assessment/results/history and the opt-in AI guidance panel with
verified citations; RAG ingestion pipeline (manifest → fetch → chunk →
embed → store, idempotent); safety layer + citation verification; session
authentication with ownership scoping (docs/auth-security.md); multimodal
medical-report ingestion with human confirmation before prediction
(docs/report-ingestion.md); read-only FHIR R4 interoperability
(`Patient`/`Observation`/`DiagnosticReport`, ownership-scoped) and a
read-only MCP server over stdio (docs/fhir-mcp.md).

**NOT implemented (later phases per docs/modernization-roadmap.md):**
Docker/CI/CD, OpenTelemetry, reranker, Kubernetes, OCR model evaluation
harness, SMART-on-FHIR, multi-user/Streamable-HTTP MCP, write-capable MCP
tools.
