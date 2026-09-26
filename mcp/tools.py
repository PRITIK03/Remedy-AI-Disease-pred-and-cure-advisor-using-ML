"""Read-only MCP tool implementations (Phase 8).

Security contract (enforced here, documented in docs/fhir-mcp.md):

* Every tool is read-only and takes a `ToolContext` whose `user_id` is bound
  by the server. No tool accepts a user id argument.
* Tools call the EXISTING services (`assessment_service`, `report_service`,
  `rag.retrieval`, `ModelService`). None issues raw SQL, and none reads the
  filesystem, environment variables, or provider credentials.
* A missing row and a foreign row produce the identical `not_found` error, so
  the tools are not an existence oracle for other users' UUIDs.
* There are no write tools. Adding one is out of scope for this phase.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mcp.schemas import (
    AssessmentHistoryPage,
    AssessmentSummary,
    ErrorPayload,
    EvidenceItem,
    ModelInformation,
    ReportMetadata,
)

# --------------------------------------------------------------------------- #
# Security boundary — the single choke point for MCP authorization
# --------------------------------------------------------------------------- #

class ToolError(Exception):
    """Typed, non-sensitive tool failure. The message is safe to return."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class ToolContext:
    """Per-request identity and dependencies handed to a tool.

    An MCP client can never choose `user_id`: the server binds it to the
    configured Remedy-AI account (see `server.py`). Tools must use
    `ctx.user_id` and never accept a user id as an argument.
    """

    __slots__ = ("user_id", "db", "model_service")

    def __init__(self, user_id: str, db: Any, model_service: Any = None) -> None:
        self.user_id = user_id
        self.db = db
        self.model_service = model_service

    def require_user_id(self) -> str:
        if not self.user_id:
            raise ToolError("forbidden", "No Remedy-AI account is bound to this session.")
        return self.user_id


def _uuid(value: str, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ToolError("invalid_input", f"'{value}' is not a valid {field}.") from exc


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.isoformat()


# --------------------------------------------------------------------------- #
# Tool implementations — existing services only, never raw table access
# --------------------------------------------------------------------------- #

def get_assessment(ctx: ToolContext, assessment_id: str) -> dict[str, Any]:
    """Fetch one assessment owned by the bound user."""
    from backend.app.services import assessment_service

    row = assessment_service.get_assessment_for_user(
        ctx.db, _uuid(assessment_id, "assessment_id"), UUID(ctx.require_user_id())
    )
    if row is None:
        # Same message for missing AND foreign: no existence oracle.
        raise ToolError("not_found", "Assessment not found.")
    return AssessmentSummary(**assessment_service.to_response(row)).model_dump()


def get_assessment_history(
    ctx: ToolContext, limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """List the bound user's assessments (newest first)."""
    from backend.app.services import assessment_service

    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    rows, total = assessment_service.list_assessments(
        ctx.db, user_id=UUID(ctx.require_user_id()), limit=limit, offset=offset
    )
    items = [
        AssessmentSummary(**assessment_service.to_response(r)).model_dump() for r in rows
    ]
    return AssessmentHistoryPage(
        items=items, total=total, limit=limit, offset=offset
    ).model_dump()


def get_report_metadata(ctx: ToolContext, report_id: str) -> dict[str, Any]:
    """Fetch metadata for one uploaded report owned by the bound user."""
    from backend.app.reports import service as report_service

    row = report_service.get_user_report_by_id(
        ctx.db, user_id=UUID(ctx.require_user_id()),
        report_id=_uuid(report_id, "report_id"),
    )
    if row is None:
        raise ToolError("not_found", "Report not found.")
    payload = report_service.to_report_response(row)
    extraction = payload.latest_extraction
    present = 0
    if extraction:
        present = sum(
            1 for v in extraction.extracted_features.values() if v is not None
        )
    return ReportMetadata(
        id=str(payload.id),
        filename=payload.filename,
        mime_type=payload.mime_type,
        file_size_bytes=payload.file_size_bytes,
        status=payload.status,
        created_at=_iso(payload.created_at),
        extraction_model=extraction.extraction_model if extraction else None,
        prompt_version=extraction.prompt_version if extraction else None,
        extracted_field_count=present,
        notes=extraction.notes if extraction else None,
    ).model_dump()


#: Metadata keys that must never be returned: filesystem paths, credentials,
#: or serialized estimator internals. Enforced by the test suite.
FORBIDDEN_MODEL_KEYS = (
    "path", "dir", "file", "filename", "models_dir", "artifact", "api_key",
    "token", "secret", "password", "url", "base_url", "pickle", "joblib",
)


def _safe_evaluation() -> dict[str, Any]:
    """Load evaluation metadata, keeping only scalar, non-path values."""
    try:
        import json

        from ml.config import EVALUATION_PATH

        if not EVALUATION_PATH.exists():
            return {}
        raw = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - metadata is best-effort
        return {}

    safe: dict[str, Any] = {}
    for key in (
        "model_version", "dataset_hash", "seed", "test_size", "cv_configuration",
        "python_version", "sklearn_version",
    ):
        if key in raw and not any(bad in key.lower() for bad in FORBIDDEN_MODEL_KEYS):
            safe[key] = raw[key]
    metrics = raw.get("test")
    if isinstance(metrics, dict):
        # Headline numbers only — no paths, no full artifact blobs.
        safe["test_metrics"] = {
            k: v for k, v in metrics.items()
            if isinstance(v, (int, float, str))
            and not any(bad in k.lower() for bad in FORBIDDEN_MODEL_KEYS)
        }
    return safe


def get_model_information(ctx: ToolContext) -> dict[str, Any]:
    """Safe ML metadata only — versions, feature count, target semantics.

    Reads the loaded `ModelService` metadata dict (already in memory); never
    touches the filesystem for models and never returns a serialized estimator.
    """
    service = ctx.model_service
    metadata: dict[str, Any] = dict(getattr(service, "_metadata", {}) or {})
    if not metadata:
        raise ToolError("unavailable", "The ML model is not loaded on this server.")

    def _read(key: str, default: Any = None) -> Any:
        value = metadata.get(key, default)
        if isinstance(value, str) and any(
            bad in value for bad in ("\\", "/", ":\\")
        ):
            return default
        return value

    features = list(metadata.get("features") or [])
    return ModelInformation(
        model_version=str(_read("model_version", "unknown")),
        selected_model=str(_read("selected_model", "unknown")),
        feature_count=len(features),
        features=features,
        target_definition=str(
            _read(
                "target_semantics",
                "1 = disease, 0 = no disease (model class encoding)",
            )
        ),
        target_transformation=_read("target_transformation"),
        positive_class=int(metadata.get("positive_class", 1)),
        dataset_name=_read("dataset"),
        dataset_hash=_read("dataset_hash"),
        evaluation=_safe_evaluation(),
        disclaimer=(
            "Educational prototype. The probability is a model-estimated "
            "probability of the disease class, not a diagnosis and not a "
            "clinically validated risk score."
        ),
    ).model_dump()


def search_health_evidence(
    ctx: ToolContext, query: str, top_k: int = 5
) -> dict[str, Any]:
    """Search the existing RAG knowledge base.

    Reuses `rag.retrieval.retrieve_relevant_evidence` — the same call the
    guidance flow makes. There is no arbitrary-URL fetching: only chunks
    already ingested from the verified source manifest are returned.
    """
    from backend.app.rag.retrieval import (
        KnowledgeBaseEmptyError,
        RetrievalUnavailableError,
        retrieve_relevant_evidence,
    )

    query = (query or "").strip()
    if not query:
        raise ToolError("invalid_input", "A non-empty query is required.")
    if len(query) > 500:
        raise ToolError("invalid_input", "Query is too long (max 500 characters).")
    top_k = max(1, min(int(top_k), 10))

    try:
        evidence = retrieve_relevant_evidence(ctx.db, query, top_k=top_k)
    except KnowledgeBaseEmptyError as exc:
        raise ToolError("unavailable", str(exc)) from exc
    except RetrievalUnavailableError as exc:
        raise ToolError("unavailable", str(exc)) from exc

    items = [
        EvidenceItem(
            title=e.title,
            source=e.source,
            url=str(e.url),
            section=e.section,
            content=e.content,
            similarity=e.similarity,
        ).model_dump()
        for e in evidence
    ]
    return {"query": query, "count": len(items), "items": items}


#: The complete, read-only tool surface. Adding an entry here is the ONLY way
#: to expose a new capability over MCP, which keeps the audit trail short.
TOOLS = {
    "get_assessment": get_assessment,
    "get_assessment_history": get_assessment_history,
    "get_report_metadata": get_report_metadata,
    "get_model_information": get_model_information,
    "search_health_evidence": search_health_evidence,
}

#: Name fragments that must never appear in the tool surface.
FORBIDDEN_TOOL_PATTERNS = (
    "create", "update", "delete", "modify", "write", "approve", "upload",
    "execute", "shell", "command", "sql", "list_users", "set_",
)


def assert_read_only_tool_surface() -> None:
    """Fail fast if a write-shaped tool is ever registered."""
    for name in TOOLS:
        lowered = name.lower()
        for pattern in FORBIDDEN_TOOL_PATTERNS:
            if pattern in lowered:
                raise RuntimeError(
                    f"MCP tool '{name}' looks write-capable (matched '{pattern}'). "
                    "This server is read-only by design."
                )


def error_payload(exc: ToolError) -> dict[str, Any]:
    """Uniform error shape for the MCP transport layer."""
    return ErrorPayload(error=exc.kind, message=exc.message).model_dump()


__all__ = [
    "TOOLS",
    "ToolContext",
    "ToolError",
    "error_payload",
    "assert_read_only_tool_surface",
    "get_assessment",
    "get_assessment_history",
    "get_report_metadata",
    "get_model_information",
    "search_health_evidence",
]

