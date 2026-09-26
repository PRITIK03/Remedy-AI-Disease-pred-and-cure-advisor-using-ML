# Multimodal Report Ingestion (Phase 7 — as implemented)

This document describes the medical-report ingestion workflow delivered after
authentication (Phase 6). It implements the roadmap's "Multimodal" item
(docs/modernization-roadmap.md): *medical/lab report extraction
(PDF/image → structured fields) with human confirmation before any
prediction; confidence gating and audit trail.*

```text
Upload (PDF/JPEG/PNG/WEBP)
      │
      ├─ magic-byte + size validation        (reject spoofed content types)
      ├─ SHA-256 hash + storage write        (per-user, non-guessable key)
      ▼
Document parsing (backend/app/reports/parser.py)
      ├─ text PDF  → pypdf text extraction → text prompt
      └─ scan/PDF/image → pypdfium2/Pillow render → vision prompt
      ▼
Multimodal LLM (provider-agnostic) → STRICT Pydantic schema
      CardiovascularReportExtraction: per-field {value, confidence, evidence}
      ▼
Persisted as report_extractions (model + prompt version + confidences)
      ▼
USER REVIEW / EDIT  (frontend /report/{id})
      ▼
POST /reports/{id}/confirm  → existing AssessmentCreate validation
      → existing ML predictor → assessments row (source='report', report_id=…)
```

The invariant is deliberate: **document AI extracts → Pydantic validates →
the user confirms → the existing ML model predicts → the existing RAG/LangGraph
flow provides guidance.** Extraction never writes a prediction by itself.

## Module layout

| Path | Responsibility |
|---|---|
| `backend/app/storage/` | `StorageProvider` ABC + `LocalStorageProvider` (path-traversal safe) and the `get_storage_provider()` factory |
| `backend/app/reports/parser.py` | MIME/magic validation, PDF text extraction, page rendering, image normalization/encoding |
| `backend/app/reports/prompts.py` | Versioned extraction system prompt + text/image user prompts |
| `backend/app/reports/schemas.py` | `ExtractedField`, `CardiovascularReportExtraction`, API response schemas, `ConfirmReportAssessmentRequest` |
| `backend/app/reports/service.py` | Upload orchestration, extraction, ownership-scoped reads, response mapping |
| `backend/app/api/v1/reports.py` | HTTP endpoints (auth + CSRF enforced at the router level) |
| `backend/app/llm/client.py` | `generate_structured_multimodal(...)` added to the existing provider-agnostic client |
| `backend/app/db/models/report.py` | `MedicalReport`, `ReportExtraction`, `ReportStatus` |


## Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/reports` | multipart upload; 201 with status + latest extraction |
| `GET` | `/api/v1/reports` | paginated (`limit`, `offset`), newest first, owner-scoped |
| `GET` | `/api/v1/reports/{report_id}` | owner-scoped; 404 for missing **and** foreign ids |
| `POST` | `/api/v1/reports/{report_id}/confirm` | user-confirmed values → assessment (201) |

All four require an authenticated session; unsafe methods also require the
CSRF double-submit token. The confirm endpoint re-validates the 13 values with
the **existing** `AssessmentCreate` rules — the report path adds no relaxed
validation.

## File safety

- **Magic bytes, not headers.** The declared `Content-Type`/extension is
  ignored; the detected signature must be PDF (`%PDF`), JPEG (`FF D8 FF`),
  PNG (`89 50 4E 47 0D 0A 1A 0A`) or WEBP (`RIFF`+`WEBP`). Anything else is a
  422. A `.pdf` filename containing text bytes is rejected.
- **Size limit** `REPORTS_MAX_BYTES` (default 10 MB), checked before parsing.
- **Page limit** `REPORTS_MAX_PDF_PAGES` (default 10); oversized PDFs are
  rejected rather than silently truncated.
- **Image integrity** is verified with Pillow (`verify()`), oversized images
  are downscaled, and re-encoded before being sent to a provider.
- **Storage keys** are `{user_id}/{report_uuid}_{filename}` under
  `REPORTS_STORAGE_DIR`; `LocalStorageProvider` resolves and re-checks every
  path against its base directory, so traversal sequences cannot escape.
- **Integrity** — the SHA-256 of the raw bytes is stored
  (`medical_reports.file_hash`) for audit and future de-duplication.

## Extraction contract

`CardiovascularReportExtraction` maps the 13 model inputs, each as
`{value, confidence, evidence}`:

- `value` is `null` when the metric is absent — the schema never invents data.
- `confidence` is 0.0–1.0 and is surfaced in the review UI per field.
- `evidence` carries the snippet that justified the value.

The response keeps the raw confidence/evidence maps so the UI can flag
low-confidence fields. Stored alongside each extraction: `extraction_model`,
`prompt_version` (`"v1"`), and free-text `notes` (e.g. unit conversions).

Prompt rules require explicit unit handling (cholesterol mmol/L → mg/dl,
fasting glucose threshold), explicit "not found" behaviour, and no guessing.
Today the gate is the human review screen plus the strict schema; a
dedicated confidence-gating/escalation step is the natural next increment.

## Provenance

`assessments` gained two columns (migration `b7d19c34e8f2`):

- `source` — `'manual'` (default, form entry) or `'report'`.
- `report_id` — FK → `medical_reports.id`, `ON DELETE SET NULL`, indexed.

`AssessmentResponse` exposes both, so History and the results page can show
where a prediction came from. `source` is server-set: a client cannot claim a
manual assessment came from a report.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `STORAGE_BACKEND` | `local` | storage provider selection (extensible) |
| `REPORTS_STORAGE_DIR` | `data/reports` | base directory for uploaded files (gitignored) |
| `REPORTS_MAX_BYTES` | `10485760` | maximum upload size in bytes |
| `REPORTS_MAX_PDF_PAGES` | `10` | maximum PDF page count |
| `MULTIMODAL_MODEL` | *(empty)* | vision model; falls back to `LLM_MODEL` |

Provider credentials reuse the existing `LLM_API_BASE` / `LLM_API_KEY` /
`LLM_MODEL` settings. When unset, extraction fails with the existing
"provider not configured" error and the report is stored with
`status='failed'` plus a human-readable `error_message` — the user can still
key values in manually.

## Frontend

- `/report` — upload page (file picker, client-side size check, progress state).
- `/report/{id}` — review screen: every field pre-filled from the extraction,
  labelled with its confidence and evidence quote, validated with the same Zod
  schema as the manual form, then confirmed → redirect to `/results/{id}`.
- Dashboard hero and the header nav (desktop + mobile) link to the upload flow.

## Tests

- `backend/tests/test_reports_api.py` — magic-byte rejection (including a
  spoofed `.pdf`), anonymous 401, extraction happy path with a stub LLM,
  listing, cross-user 404, confirm creating a `source='report'` assessment,
  invalid confirm payload 422, and pure-parser unit checks.
- `frontend/tests/report.test.tsx` — pre-fill from extraction, missing values
  block confirmation, numeric payload + redirect on confirm.
- `frontend/tests/api-client.test.ts` — `listReports` pagination and
  `confirmReport` request shape.

```bash
.venv/Scripts/python.exe -m pytest backend/tests/test_reports_api.py
cd frontend && npx vitest run tests/report.test.tsx
```

## Limits / honest scope

- Text PDFs are parsed deterministically; scanned PDFs and images depend on a
  vision-capable model. Without a configured provider, extraction fails
  closed (no fabricated values).
- Extracted values are **not** medical measurements: they are model
  suggestions that a human must confirm. Nothing is predicted before that
  confirmation.
- Uploaded files are stored on the local filesystem in this deployment; the
  storage provider interface exists so an object store can replace it without
  touching the API or models.
- No OCR-quality evaluation harness yet (the roadmap's "OCR/vision model
  evaluation" item remains open).

