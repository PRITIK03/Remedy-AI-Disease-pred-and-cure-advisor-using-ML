# Limitations

Honest, current limitations of Remedy-AI. Read this before drawing any
conclusion from the system or deploying it.

## Scope

- **Educational/research prototype.** Not a medical device, not a clinical
  tool, and not approved for any clinical use anywhere.
- Outputs are **model estimates, not diagnoses**, and are not clinically
  validated risk scores. Nothing the system produces is medical advice.
- No prospective study, no external validation, no regulatory review has been
  performed.

## Data limitations

- The dataset (`ml/data/heart.csv`, 303 rows) is a UCI/Kaggle-derived heart
  dataset: **small, single-cohort, and dated**. It over-represents one
  population and cannot represent modern, diverse clinical populations.
- The legacy pipeline (kept only for regression comparison) was trained with
  scaler-fit-on-full-dataset **leakage**; its reported accuracy is inflated and
  meaningless. The modern pipeline fixes this, but no retraining on better data
  has occurred.
- Class balance and subgroup sizes are small; subgroup metrics are reported in
  `models/v2/metrics.json` but are **noisy** and not fairness guarantees.

## Model limitations

- The model uses **13 tabular features only** — no history, medication,
  labs beyond the classic set, or follow-up outcomes.
- Calibration is in-sample (sigmoid, CV on train); it does not guarantee
  calibration on other populations.
- `P(disease) ≥ 0.5` is a threshold convention, not a clinical decision rule.

## AI guidance limitations (RAG / LLM / LangGraph)

- **Live provider validation is pending**: the code is complete and tested
  against fakes, but this environment has no embedding/LLM provider
  configured, so no real end-to-end generation has been validated here.
- Guidance quality depends entirely on the configured provider and the
  ingested knowledge base (`rag/sources.yaml`). It can be unavailable, stale,
  or wrong.
- Citation verification enforces that citations come from retrieved sources;
  it cannot guarantee the sources themselves are current or authoritative.
- The safety layer refuses diagnosis/prescription-style requests and routes
  emergency vocabulary to professional care — it is heuristic, not airtight.

## Report ingestion limitations

- Extraction from images/PDFs uses a vision-capable LLM and **requires human
  confirmation** before values affect anything; OCR/extraction errors are
  expected and the review step is the mitigation.
- PDF page and file-size caps are deliberate (10 MB / 10 pages by default).

## Security & privacy limitations

- The prototype implements solid baseline controls (Argon2, CSRF, ownership
  scoping, rate limiting, private storage), but it has **not had a security
  audit or penetration test**.
- Deployers are responsible for TLS, encryption at rest, backups, secret
  management, and compliance with applicable health-data regulation
  (HIPAA/GDPR/local equivalents). Nothing here certifies compliance.

## Operational limitations

- Single-region, single-database design; no multi-region or HA story.
- `STORAGE_BACKEND=local` loses uploaded reports on redeploy; real deployments
  must use S3-compatible storage.
- OpenTelemetry is opt-in and records operational attributes only — there is
  no business/clinical analytics.

## Environment-specific status (this workspace)

- PostgreSQL/Redis: available via Docker Compose configuration; migrations
  exist for all tables including pgvector.
- pgvector: **unverified live** in this workspace (extension available via the
  `pgvector/pgvector:pg18` image; not exercised end-to-end here).
- LLM/embedding providers: **not configured** — AI guidance returns an explicit
  "unavailable" response by design.
