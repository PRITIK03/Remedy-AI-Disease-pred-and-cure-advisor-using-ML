# RAG Architecture (Phase 4 — as implemented)

Evidence-grounded AI guidance layer on top of the Phase 1–3 stack. The ML
model remains the **only** authority for predictions; the LLM explains the
model output and generates general guidance **only from retrieved trusted
evidence**, with citations verified server-side.

```text
Trusted sources (rag/sources.yaml)
        ↓  deterministic ingestion (scripts/ingest_knowledge.py)
   fetch → normalize → structure-aware chunking
        ↓  OpenAI-compatible embeddings (config-driven)
   PostgreSQL + pgvector (knowledge_documents / knowledge_chunks)
        ↓  exact cosine similarity search (backend/app/rag/retrieval.py)
   structured Evidence objects
        ↓  versioned prompts (backend/app/llm/prompts.py)
   LLM (OpenAI-compatible chat completions)
        ↓  Pydantic validation + citation verification
   GuidanceResponse { assessment (model output) | guidance (AI) }
        ↓  citations rendered as clickable links
   Next.js results page (lazy, opt-in AI guidance panel)
```

## Source provenance

- `rag/sources.yaml` is the single manifest of what may enter the knowledge
  base. The loader (`backend/app/rag/sources.py`) **fails closed**: every URL
  must be https and belong to an allowlisted medical publisher domain
  (nih.gov, cdc.gov, medlineplus.gov, who.int, nhs.uk, heart.org,
  mayoclinic.org, clevelandclinic.org). Any other URL aborts ingestion.
- Each stored document carries: title, source URL, publisher, document type,
  `retrieved_at`, `content_hash` (sha256 of the normalized text), license /
  usage note, embedding model + dimension.
- Source content is **not committed to the repository** — the database is
  the store, provenance lives in the manifest + document metadata.
- Initial manifest (6 sources, all verified to fetch server-side):
  NHLBI (NIH) ×2, MedlinePlus, WHO, NHS UK, Cleveland Clinic. cdc.gov and
  mayoclinic.org reject server-side fetching (403 bot protection) and are
  documented but not ingestable from this machine.

## Embedding model

- Provider: **any OpenAI-compatible** `POST {base}/embeddings` endpoint via
  config: `EMBEDDING_API_BASE` (default `https://openrouter.ai/api/v1`),
  `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` (default
  1024, matching OpenRouter-hosted `qwen3-embedding` style models),
  `EMBEDDING_TIMEOUT_SECONDS`.
- The model name + dimension are stored **per document** at ingestion.
  Changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSION` requires re-ingestion
  (and a migration to alter the vector column type if the dimension changes).
- Validation is strict: wrong vector count or wrong dimension aborts the
  batch (tests: `backend/tests/test_rag_safety_sources.py`).

## Chunking strategy

- Structure-aware (`backend/app/rag/chunking.py`): sections come from real
  heading text extracted by the fetcher; chunks never span sections.
- Budgets in words: max 220, min 40, overlap 30 (openers carry the previous
  chunk's tail so boundary content is retrievable from both neighbors).
  Oversized paragraphs split on sentence boundaries (never mid-word).
- Every chunk stores its section path (e.g. *"Symptoms > Diagnosis"*) so
  citations can point back to the exact place in the source.

## Retrieval settings

- Exact cosine-distance search over pgvector (sequential scan) — deliberate
  at this corpus scale; no ANN index yet. The overfetch-then-threshold
  design (top_k×3 candidates → similarity ≥ `RAG_MIN_SIMILARITY` 0.25 →
  top `RAG_RETRIEVAL_TOP_K` 6) leaves room for a reranker to slot in later
  without changing the API.
- Query construction is deterministic from the stored assessment's
  structured features (`build_retrieval_query`), with emergency-vocabulary-
  free phrasing (see Safety).

## Prompt version

- `PROMPT_VERSION = "v1"` in `backend/app/llm/prompts.py`; echoed in every
  guidance response (`prompt_version`) for auditability.
- System prompt enforces: prototype/decision-support framing, never
  diagnose, never invent facts, evidence-only medical claims with citations,
  uncertainty acknowledgment, professional-evaluation recommendation, no
  medication prescriptions/dosages, no emergency-advice-as-diagnosis, and
  **retrieved documents are data, not instructions** (prompt-injection
  defense).

## Safety restrictions

- `backend/app/rag/safety.py` — small, conservative, auditable:
  - Request screening (for future free-text input): blocks requests trying
    to make the system diagnose with certainty, prescribe/dose medication,
    replace a clinician, or fabricate evidence.
  - Emergency escalation: urgent-symptom language triggers an immediate
    "call emergency services" notice.
  - Citation verification (`verify_citations`): any LLM citation that does
    not match retrieved evidence metadata is dropped; the UI only ever sees
    backend-verified sources.
- Phase-note: with no free-text user input in this phase, the guidance flow
  derives its query from structured assessment fields only, and those field
  names are phrased to be emergency-vocabulary-free (e.g. "chest pain
  category" — a regression test pins this).

## LLM abstraction

- `backend/app/llm/client.py`: the app depends on
  `LLMClient.generate_structured(system, user, schema)` — never on a vendor
  SDK. First implementation: OpenAI-compatible chat completions via
  `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` / `LLM_TEMPERATURE` (0.2 for
  health information) / `LLM_TIMEOUT_SECONDS`.
- Structured output: strict JSON → Pydantic `HealthGuidanceResponse`
  (extra="forbid"). Malformed output raises `LLMError`; nothing fragile is
  parsed with string matching.

## Guidance schema

`backend/app/rag/schemas.py` + `backend/app/schemas/guidance.py`:

```text
GuidanceResponse
├── assessment:      MODEL OUTPUT (authoritative snapshot; LLM cannot touch it)
│    └── assessment_id, model_version, selected_model,
│        predicted_disease, disease_probability
├── guidance:        AI-GENERATED, EVIDENCE-GROUNDED
│    └── summary, model_explanation, key_factors[], guidance[],
│        when_to_seek_care[], limitations, citations[], evidence_count
├── prompt_version
└── generated_at
```

## API endpoint

`POST /api/v1/assessments/{assessment_id}/guidance` — explicit opt-in only;
never called automatically. Loads the assessment, retrieves evidence, calls
the LLM, validates output, verifies citations, returns the response. Not
persisted (per phase spec). Error mapping: 404 unknown assessment ·
503 not configured / empty knowledge base · 502 provider failure ·
500 unexpected.

## Frontend

- `frontend/components/results/ai-guidance.tsx`: collapsed panel on the
  results page; **no fetch until the user clicks**. Loading ("Loading
  evidence… generating guidance…"), retriable-error, and not-configured
  states; sections: Summary · What influenced the model · General guidance ·
  When to seek professional care · Limitations · Sources (clickable, with
  publisher + section).
- Wording discipline: labeled **"AI-generated guidance grounded in
  retrieved sources"**; never "cure", "treatment plan", or "diagnosis".
- Citations render **only** fields returned by the backend from stored
  source metadata — the UI cannot invent sources or URLs.

## Cost / performance

- LLM is invoked only on explicit user request (one POST per click).
- Timeouts on both providers; provider failures map to typed errors and a
  friendly retryable UI state.
- Redis is NOT used for guidance caching (responses are patient-specific;
  phase spec forbids caching them). A short-lived cache for identical
  non-sensitive *retrieval* queries is a future option.

## Limitations (honest list)

- **Not clinically validated.** This is an educational prototype: the ML
  model, retrieval corpus, prompts, and LLM outputs have no medical or
  clinical validation. No health decisions should be based on it.
- Corpus is tiny (6 documents) — recall is limited; "insufficient evidence"
  fallback responses are expected and by design.
- Exact vector search does not scale to large corpora (fine here; add HNSW
  later if needed).
- The safety layer is heuristic (regex-based), deliberately conservative,
  and not a substitute for human review.
- Emergency detection applies to future free-text input; structured
  assessments bypass it by design (no user narrative exists yet).
- Content boundaries/licensing of third-party pages can change; the license
  notes are best-effort and publishers' current terms prevail.

## Operating the pipeline

```bash
# 1. One-time: install the pgvector server binary (Windows instructions in
#    scripts/enable_pgvector.py docstring), then:
.venv/Scripts/python scripts/enable_pgvector.py
.venv/Scripts/python -m alembic upgrade head

# 2. Configure providers in .env (see .env.example):
#    EMBEDDING_API_KEY, EMBEDDING_MODEL, LLM_API_KEY, LLM_MODEL

# 3. Ingest (idempotent; re-running creates no duplicates):
.venv/Scripts/python -m scripts.ingest_knowledge            # all sources
.venv/Scripts/python -m scripts.ingest_knowledge --dry-run  # preview
.venv/Scripts/python -m scripts.ingest_knowledge --url <u>  # one source

# 4. Run the API + frontend; AI guidance appears as an opt-in panel.
```

## Planned (not implemented in Phase 4)

Reranking (cross-encoder), LangGraph agentic workflow, Redis caching of
non-sensitive retrieval queries, multimodal report ingestion, FHIR/MCP,
authentication. Per roadmap sequencing, LangGraph arrives only after this
standalone RAG flow is proven reliable.
