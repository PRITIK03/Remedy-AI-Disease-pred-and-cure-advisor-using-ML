# FHIR Interoperability + Read-Only MCP (Phase 8 — as implemented)

Two **read-only** interoperability surfaces over data Remedy-AI already
stores. Neither adds a write path, and neither invents clinical information.

```text
Authenticated User
       ↓
   Remedy-AI
 ┌─────┴────────┐
 │              │
FHIR          MCP
 │              │
Healthcare     AI clients
systems        / agents
```

| Module | Path |
|---|---|
| FHIR resource schemas | `backend/app/fhir/schemas.py` |
| FHIR vocabulary/codings | `backend/app/fhir/resources.py` |
| FHIR mapping | `backend/app/fhir/mapper.py` |
| FHIR API | `backend/app/api/v1/fhir.py` |
| MCP server (stdio) | `mcp/server.py` |
| MCP tools | `mcp/tools.py` |
| MCP payload schemas | `mcp/schemas.py` |
| Synthetic fixture | `backend/tests/fixtures/synthetic_fhir.json` |
| Tests | `backend/tests/test_fhir_mcp.py` |

---

## 1. FHIR resources supported

FHIR **R4** shapes only — and only the fields this application actually
populates. This is deliberately *not* a FHIR server: no terminology server,
no `$validate` endpoint, no CapabilityStatement.

| Resource | Emitted for | Notes |
|---|---|---|
| `Patient` | every bundle | account holder only: display name + active flag. No email, no role, no invented birthDate/gender. |
| `Observation` | 13 model inputs + 1 model output | one per feature, plus the disease-probability output |
| `DiagnosticReport` | one per assessment, one per uploaded report | links the Observations via `result[]` |
| `Bundle` (`type=collection`) | wraps each response | one provenance statement for the whole payload |

### Mapping strategy

- **Inputs only.** The mapper reads service-level response dicts
  (`assessment_service.to_response`, `report_service.to_report_response`) and
  `User.to_public()`. ORM internals — password hashes, storage keys, SHA-256
  hashes, raw extraction evidence text — cannot reach a FHIR payload.
- **One Observation per feature**, in canonical ML order, with LOINC codes and
  UCUM units where a real unit exists: `age` (LOINC `424619002`, `a`),
  `trestbps` (`8480-6`, `mm[Hg]`), `chol` (`2093-3`, `mg/dL`), `thalach`
  (`8867-4`, `/min`), `oldpeak` (`59868-9`, `mm`). The remaining eight
  features are model encodings and carry no unit (see `resources.py`).
- **Categorical encodings are labelled as encodings**, emitted as
  `valueString`, e.g. `"Typical angina (model category 0)"`, so a downstream
  system is never misled into treating them as a clinical vocabulary.
- **Nothing is invented.** A value the application does not have becomes
  `dataAbsentReason` (`not-performed`) — never a default, zero, or guess.
- **The model output is not a measurement.** The probability is emitted as an
  Observation coded `model-estimated-disease-probability` with a note stating
  it is not a diagnosis and not a clinically validated risk score.
- **Unconfirmed extractions are `preliminary`.** Observations built from a
  Phase 7 upload carry `status="preliminary"` and a confidence note, because a
  human has not confirmed them.
- **Provenance is always present.** Every resource carries
  `meta.source = urn:remedy-ai:remedy-ai` plus a `generated` tag whose display
  text says the output comes from this application and is not a diagnosis.

## 2. FHIR API

Read-only, authenticated, and user-scoped. Registered in the same `/api/v1`
router as everything else, with the same CSRF dependency.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/v1/fhir/assessments/{id}` | Bundle: Patient + 13 Observations + probability Observation + DiagnosticReport |
| `GET` | `/api/v1/fhir/reports/{id}` | Bundle: Patient + 13 extracted Observations (preliminary) + DiagnosticReport |

Security behaviour is inherited from the Phase 6 pattern:

- anonymous → **401**;
- another user's id → **404**, byte-identical to a missing id (no existence
  oracle);
- every read goes through the existing ownership-scoped services
  (`get_assessment_for_user`, `get_user_report_by_id`).

## 3. FHIR validation

Lightweight, in-process, and schema-level only — **no external FHIR
validation server**. `backend/app/fhir/schemas.py` uses Pydantic models with
`extra="forbid"`, so the mapper physically cannot emit an undeclared field.
Checked on every response:

- `resourceType` is one of the supported types (`Bundle` at the root);
- `id` is present on every resource;
- `subject.reference` is present on `Observation` and `DiagnosticReport`;
- Observation values: `valueQuantity` **or** `valueString` **or**
  `dataAbsentReason`, never an empty Observation;
- `effectiveDateTime` / `issued` are ISO-8601 UTC strings wherever a timestamp
  exists.

## 4. Synthetic demo data

`backend/tests/fixtures/synthetic_fhir.json` is a tiny, obviously fake fixture
(reserved `00000000-0000-4000-8000-…` UUIDs, "Synthetic Demo Subject") used by
the tests and available for local inspection. It contains **no real patient
data** and no large dataset. All FHIR output is derived from the
application's own rows; nothing is loaded from this fixture at runtime.

---

## 5. MCP server

Built on the **official MCP Python SDK v2** (`mcp>=2.0`, `MCPServer`).

| Tool | Answers | Reuses |
|---|---|---|
| `get_assessment` | one assessment + its 13 inputs | `assessment_service.get_assessment_for_user` + `to_response` |
| `get_assessment_history` | the account's assessments (newest first, limit ≤ 100) | `assessment_service.list_assessments` |
| `get_report_metadata` | report metadata + extraction provenance (never the file, path, or hash) | `report_service.get_user_report_by_id` + `to_report_response` |
| `get_model_information` | model version, selected model, feature count/names, target definition, evaluation metadata | `ModelService` metadata + `ml/artifacts/evaluation.json` (scalars only) |
| `search_health_evidence` | title, publisher, section, URL, passage | `rag.retrieval.retrieve_relevant_evidence` |

No tool issues raw SQL, and none reads the filesystem for models,
environment variables, or credentials. `search_health_evidence` calls the same
retrieval the guidance flow uses; it does **not** fetch arbitrary URLs — only
chunks already ingested from the verified source manifest.

### Model information tool

Returns metadata only: `model_version`, `selected_model`, `feature_count`,
`features`, `target_definition` ("1 = disease, 0 = no disease"),
`target_transformation`, `positive_class`, dataset name/hash, headline
evaluation metrics, and a disclaimer. Filesystem paths, artifact locations,
credentials, and serialized estimators are filtered out
(`FORBIDDEN_MODEL_KEYS`).

## 6. MCP security model

An MCP server has no browser session, so identity comes from configuration:

- **`MCP_USER_ID`** — the single Remedy-AI account UUID this server may read.
  **Startup fails without it** (`McpConfigurationError`), so the server can
  never run unscoped.
- **`DATABASE_URL`** — one short-lived session per tool call, closed
  immediately afterwards.

Consequences, all covered by tests:

- No tool accepts a `user_id` argument; the context is server-bound.
- Missing and foreign ids produce the identical `not_found` error.
- Tool errors are typed and non-sensitive (`not_found`, `forbidden`,
  `unavailable`, `invalid_input`) — never a stack trace or SQL text.
- Every tool is annotated `readOnlyHint=True`, `destructiveHint=False`,
  `openWorldHint=False`; `assert_read_only_tool_surface()` raises at startup if
  a write-shaped name is ever added.
- The server instructions restate the read-only and "not a diagnosis"
  boundaries for the calling model.

**Explicitly never exposed:** all users, all assessments, raw database
queries, filesystem access, shell execution, environment variables, API keys,
passwords, or session ids. There are no `delete_*`, `modify_*`, `approve_*`,
`upload_*` or `execute_*` tools.

## 7. Transport

**stdio** is the default (`mcp/server.py` → `build_server().run("stdio")`),
which is the development-friendly transport: an MCP client launches the
process and talks over stdin/stdout.

The wiring is transport-agnostic on purpose, so Streamable HTTP can be added
later:

```python
server = build_server()
server.run("streamable-http")   # only behind an authenticated proxy
```

No unauthenticated public MCP HTTP server is started by this phase.

### Naming note

The phase spec requires the files `mcp/server.py`, `mcp/tools.py`, and
`mcp/schemas.py`, while the official SDK is also imported as `mcp`. To let
both coexist, `mcp/__init__.py` puts the SDK directory first on `__path__`
(so `mcp.server` and `mcp.types` are the official subpackages, while
`mcp.tools` / `mcp.schemas` are ours) and additionally publishes our
`server.py` under the explicit name `mcp.remedy_server`. No SDK code is
vendored or modified.

### Running it

```bash
# 1. bind it to an account (read the UUID from GET /api/v1/auth/me)
export MCP_USER_ID=<your-account-uuid>

# 2. run over stdio
.venv/Scripts/python -m mcp.remedy_server
```

## 8. Frontend

Deliberately minimal, and only where it adds real value: the results page
gained a single "Export as FHIR R4" link pointing at the new read-only
endpoint, and the dashboard shows a static interoperability note. **No MCP
client in the browser** — the MCP server is a developer/agent integration,
not a UI surface.

## 9. SMART-on-FHIR (planned — not implemented)

Not part of this phase. A future increment could add OAuth2/OIDC against
SMART-on-FHIR backends, `launch` / `launch-context` authorization-code flow,
`.well-known/smart-configuration` discovery, read-only `Patient/$everything`
style reads, and sandbox-EHR writes of `Observation` / `DiagnosticReport`.
Until then Remedy-AI exposes plain authenticated FHIR JSON and nothing else.

## 10. Testing

Targeted only, as the phase spec requires (no external LLMs, no RAG
ingestion, no ML retraining):

```bash
.venv/Scripts/python -m pytest backend/tests/test_fhir_mcp.py
```

34 tests covering: FHIR mapping (no invented data, subject references,
quantity vs. string, data-absent, provenance tags, report-result links, no
storage-key/hash leakage), lightweight schema validation, FHIR API
authentication and ownership (401 / cross-user 404 / indistinguishable 404s),
MCP tool registration and read-only annotations, the read-only surface guard,
no-`user_id` tool arguments, refusal to start unbound, and tool-level
ownership enforcement with mocked services.

## 11. Limits / honest scope

- The output is a **serialization of an educational prototype's data**, not an
  EHR export. Consumers must treat the `generated` tag and the "not a
  diagnosis" notes as binding.
- The `Patient` resource is intentionally thin: Remedy-AI stores an account,
  not a clinical patient record, so demographics are minimal by design.
- No terminology server, no profile validation, and no terminology-level
  conformance claim.
- MCP is stdio-only and single-account in this phase; multi-user MCP and
  Streamable HTTP are **planned**, not implemented.
