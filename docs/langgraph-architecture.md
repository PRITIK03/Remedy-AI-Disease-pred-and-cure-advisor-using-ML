# LangGraph Architecture (Phase 5 — as implemented)

LangGraph is the **orchestration layer** for the Phase 4 guidance flow. It
does not replace any existing capability — the ML predictor, RAG retrieval,
LLM abstraction, and safety/citation validation are reused unchanged; the
graph only sequences them and adds deterministic routing, checkpointing,
and a human-review boundary.

```text
START
  ↓
load_assessment        (authoritative model result read once from the DB)
  ↓
retrieve_evidence      (existing Phase 4 RAG service)
  ↓
generate_guidance      (existing Phase 4 LLM abstraction + schema)
  ↓
safety_check           (existing Phase 4 citation verification + safety)
  ↓
review_router ──── deterministic, pure-function routing ────┐
  ├── normal            → finalize  → END                   │
  ├── safety flag       → human_review → finalize → END     │
  ├── high risk (≥0.75) → human_review → finalize → END     │
  ├── RAG degraded      → human_review → finalize → END     │
  └── failure           → error → END                       │
```

## Why a workflow, not a multi-agent system

- Every node has ONE functional job; there are no persona agents ("doctor
  agent", "nutrition agent") — those would add prompt-injection surface and
  fake authority without adding capability.
- Every edge is hard-coded. The LLM never chooses the next node, never
  writes to the database, never touches the filesystem, shell, or network
  beyond its single structured-completion call through the existing client.
- Routing decisions are pure functions of state
  (`backend/app/agents/routing.py`) — auditable and unit-testable in
  isolation.

## State schema (`backend/app/agents/state.py`)

Typed `GuidanceGraphState` (TypedDict) holding **raw structured values** —
never formatted prompt strings, never secrets, no identifiers beyond the
assessment ID:

| Field | Notes |
|---|---|
| `assessment_id` | workflow input / thread key (demo; see Checkpointing) |
| `assessment` | raw ML feature values |
| `model_result` | **AUTHORITATIVE** — set once by `load_assessment`; no LLM-derived node may write it |
| `evidence` | list of dict-form Evidence (checkpoint-serializable) |
| `evidence_available` / `rag_error` | RAG health for routing |
| `guidance` | validated guidance as dict (state stores data, not objects) |
| `safety_flags` | flags from the safety node (force review) |
| `review_required` / `review_reason` / `review_status` | review boundary |
| `errors` | append-only channel (reducer: `operator.add`) |
| `metadata` | merge-reducer dict (attempt counts, degradation markers) |

Boundaries convert between Pydantic and dict: nodes `model_dump()` on the
way in, `model_validate()` on the way out, so nothing unvalidated ever
leaves the graph.

## Node responsibilities

- **load_assessment** — loads the stored row once; missing → terminal error
  state (router → error). The stored `model_version` / `predicted_disease` /
  `disease_probability` are the only values ever served as "model output".
- **retrieve_evidence** — calls the existing `retrieve_relevant_evidence`.
  Unconfigured RAG or exhausted transient retries degrade deterministically
  (`rag_error` + metadata marker), never crash.
- **generate_guidance** — calls the existing `LLMClient` only; fails fast
  (no retry) when providers are unconfigured; retries only transient LLM
  network errors; schema-validation failures are terminal.
- **safety_check** — reuses `verify_citations` (fabricated citations are
  dropped AND flagged), scans generated text for emergency language and
  diagnostic-certainty phrasing (flag, not delete).
- **review_router** — deterministic decision + review payload assembly.
- **human_review** — the pause boundary; no auto-approval ever.
- **finalize / error** — terminal stamps only.

## Routing rules (deterministic)

```text
missing assessment            → error
workflow failure (LLM etc.)   → error
any safety flag               → human_review
probability >= 0.75           → human_review
RAG degraded / empty          → human_review
otherwise                     → finalize
```

`HIGH_RISK_PROBABILITY = 0.75` lives in `routing.py` — a deliberate,
documented demo policy, changeable in one place.

## Human-review mechanism

- No authenticated clinicians exist yet, so the review boundary is a **safe
  demo**: `review_required=true`, `review_status="pending"`, guidance is
  **NOT released** to the client (the API answers `202` with the model
  snapshot and a plain-language flag message).
- Nothing anywhere claims a clinician reviewed or approved anything; there
  is no admin portal and no reviewer identity.
- Resume operation (`agents/service.resume_review`) accepts
  `"approve"` (release the held guidance) or `"reject"` (discard) via
  LangGraph `update_state` on the checkpointed thread.
- The review payload contains exactly: `assessment_id`, `model_result`,
  `generated_guidance`, `safety_flags`, `reason_for_review`. No secrets.

## Checkpointing

- **Production path**: PostgreSQL-backed `PostgresSaver`
  (`langgraph-checkpoint-postgres`) against the same configured database —
  fits the existing PostgreSQL architecture without a new datastore.
- **Local/dev/test fallback**: `InMemorySaver`, selected via
  `AGENTS_CHECKPOINTER=memory` or automatic fallback if the Postgres
  checkpointer cannot be set up. The checkpointer instance is cached
  process-wide (resume requires the same checkpointer across calls).
- **Thread id**: `guidance:{assessment_id}`. This is acceptable ONLY in the
  current unauthenticated demo. When authentication/multi-user isolation
  arrives, thread ids MUST become user-scoped (e.g.
  `{user_id}:{assessment_id}`) and review decisions must become
  identity-bearing — tracked for the auth phase.
- No custom checkpoint database was invented.

## Failure handling & retries

- Retries (max 3 attempts, 1s linear backoff) ONLY for transient external
  failures: LLM network errors, retrieval network errors.
- Never retried: schema-validation failures, safety flags, invalid
  assessment IDs, configuration errors (fail fast with typed errors).
- Attempt counts are recorded in state `metadata` for observability.
- API error mapping: 404 unknown · 503 not configured · 502 provider
  failure · 202 review-pending · 200 completed guidance.

## API changes (backward compatible)

`POST /api/v1/assessments/{id}/guidance` keeps its contract
(`assessment`, `guidance`, `prompt_version`, `generated_at`, `citations`)
and now adds `workflow_status`, `review_required`, `safety_flags`. A
review-flagged case returns **202** with a structured detail body instead
of guidance. Internal graph state is never exposed.

## Optional LangSmith tracing

`LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` (+ optional
`LANGCHAIN_PROJECT`/`LANGCHAIN_ENDPOINT`) enable LangSmith tracing for
graph/LLM debugging. Unset (the default) → fully functional with no
tracing. MLflow remains the ML/GenAI experiment tracker; no duplication.

## Evaluation harness

`evals/agent_cases.json` — 8 synthetic trajectory cases (normal, high-risk
review, missing assessment, RAG unavailable, LLM malformed, LLM outage,
fabricated citations, empty knowledge base) asserting route, review
decision, workflow status, schema validity, retry counts. Runner:
`backend/tests/agents/test_eval_cases.py` (all externals stubbed; runs in
~2s).

## Security posture

The graph is read-only orchestration: no DB writes from nodes (assessment
loading is read-only; guidance is not persisted), no filesystem, no shell,
no arbitrary HTTP from the LLM, no credentials in state or prompts. The
LLM's only capability is one structured completion call through the
existing client.
