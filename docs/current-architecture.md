# Current Architecture (after Phase 1 — as actually implemented)

This documents what exists **today**, after Phase 0 (audit + baseline) and
Phase 1 (ML modernization). Planned-but-unbuilt items are listed explicitly
at the end and must not be read as implemented.

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

**Implemented (verified by tests):** the two flows above, model-provider
abstraction, corrected semantics, calibration, CV, SHAP explainability,
MLflow tracking, dataset provenance, 80 passing tests.

**NOT implemented (later phases per docs/modernization-roadmap.md):** FastAPI
backend, PostgreSQL/Redis, Next.js frontend, RAG/LLM advice engine, LangGraph
agents, multimodal extraction, FHIR/MCP, Docker/CI/CD, OpenTelemetry, auth,
rate limiting.
