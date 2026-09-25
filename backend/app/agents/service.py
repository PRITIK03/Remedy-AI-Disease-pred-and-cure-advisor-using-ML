"""Public agent service — the only interface the API layer talks to.

run_guidance_workflow(assessment_id)  → full workflow result
resume_review(assessment_id, decision, reviewer_note) → resume from the
human-review boundary (checkpointed graphs only).

The service converts internal graph state into the API contract and strips
anything internal (raw state, review payloads, metadata soup).
"""

from __future__ import annotations

from typing import Any

from backend.app.core.logging import get_logger

logger = get_logger("backend.agents.service")

# Thread id = assessment id for this unauthenticated demo. When
# authentication/multi-user isolation is introduced this MUST become
# f"{user_id}:{assessment_id}" (or similar) — see docs/langgraph-architecture.md.
def thread_id_for(assessment_id: str) -> str:
    return f"guidance:{assessment_id}"


class AssessmentNotFoundError(RuntimeError):
    """The requested assessment does not exist."""


class WorkflowFailedError(RuntimeError):
    """The workflow could not produce guidance (provider failure etc.)."""


class GuidanceNotConfiguredError(RuntimeError):
    """The guidance capability is not configured on this deployment
    (LLM/embedding provider credentials missing)."""


class ReviewPendingError(RuntimeError):
    """Guidance was generated but awaits human review (high-risk/flagged)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__("guidance pending human review")
        self.payload = payload


def run_guidance_workflow(db, assessment_id: str, llm_client=None) -> dict[str, Any]:
    """Execute the graph and return the API-shaped guidance payload.

    Raises:
        AssessmentNotFoundError: unknown assessment id.
        WorkflowFailedError: LLM/provider failure after retries.
        ReviewPendingError: flagged/high-risk case awaiting review.
    """
    from backend.app.agents.graph import build_guidance_graph

    graph = build_guidance_graph(db, assessment_id, llm_client)
    config = {"configurable": {"thread_id": thread_id_for(assessment_id)}}
    final: dict[str, Any] = graph.invoke(
        {"assessment_id": assessment_id}, config=config
    )

    if final.get("model_result") is None:
        raise AssessmentNotFoundError(assessment_id)

    metadata = final.get("metadata") or {}
    if final.get("llm_error"):
        if metadata.get("llm_unconfigured"):
            raise GuidanceNotConfiguredError(final["llm_error"])
        raise WorkflowFailedError(final["llm_error"])

    if final.get("review_required"):
        raise ReviewPendingError(
            {
                "assessment_id": assessment_id,
                "model_result": final.get("model_result"),
                "generated_guidance": final.get("guidance"),
                "safety_flags": final.get("safety_flags") or [],
                "reason_for_review": final.get("review_reason"),
            }
        )

    guidance = final.get("guidance")
    if guidance is None:
        raise WorkflowFailedError("workflow produced no guidance")

    return _to_response(final, guidance)


def resume_review(
    db, assessment_id: str, decision: str, reviewer_note: str = ""
) -> dict[str, Any]:
    """Resume the workflow from the human-review boundary.

    decision: "approve" (release generated guidance) or "reject" (discard).
    This is a workflow boundary only — no reviewer identity exists yet
    (unauthenticated demo), so nothing pretends a clinician approved.
    """
    from backend.app.agents.graph import build_guidance_graph

    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    graph = build_guidance_graph(db, assessment_id)
    config = {"configurable": {"thread_id": thread_id_for(assessment_id)}}
    snapshot = graph.get_state(config)
    if snapshot is None or not snapshot.values:
        raise AssessmentNotFoundError(assessment_id)

    state = dict(snapshot.values)
    if not state.get("review_required"):
        raise ValueError("this workflow is not awaiting review")

    state["review_status"] = "approved" if decision == "approve" else "rejected"
    state["workflow_status"] = (
        "finalized" if decision == "approve" else "failed"
    )
    # An approved review releases the held guidance; the response must no
    # longer present itself as pending (it is the resume outcome).
    state["review_required"] = False
    state["metadata"] = {
        **(state.get("metadata") or {}),
        "review_decision": decision,
        "reviewer_note_present": bool(reviewer_note),
    }

    graph.update_state(config, state, as_node="human_review")
    if decision == "reject":
        raise WorkflowFailedError("guidance rejected in review")

    guidance = state.get("guidance")
    if guidance is None:
        raise WorkflowFailedError("reviewed workflow contains no guidance")
    return _to_response(state, guidance)


def _to_response(state: dict[str, Any], guidance: Any) -> dict[str, Any]:
    """Map graph state → API contract (backward compatible with Phase 4).

    `guidance` arrives as the JSON-compatible dict stored in state; it is
    re-validated through the Phase 4 schema so nothing unvalidated can leak
    into the API response.
    """
    from datetime import UTC, datetime

    from backend.app.core.config import get_settings
    from backend.app.rag.schemas import (
        Citation,
        Evidence,
        HealthGuidanceResponse,
        verify_citations,
    )
    from backend.app.schemas.guidance import AssessmentSnapshot, GuidanceDetail

    validated = (
        guidance
        if isinstance(guidance, HealthGuidanceResponse)
        else HealthGuidanceResponse.model_validate(guidance)
    )
    evidence = [
        e if isinstance(e, Evidence) else Evidence.model_validate(e)
        for e in (state.get("evidence") or [])
    ]
    verified = verify_citations(validated, evidence)

    model_result = state["model_result"]
    snapshot = AssessmentSnapshot(
        assessment_id=state["assessment_id"],
        model_version=model_result["model_version"],
        selected_model=model_result["selected_model"],
        predicted_disease=bool(model_result["predicted_disease"]),
        disease_probability=float(model_result["disease_probability"]),
    )
    detail = GuidanceDetail(
        summary=validated.summary,
        model_explanation=validated.model_explanation,
        key_factors=validated.key_factors,
        guidance=validated.guidance,
        when_to_seek_care=validated.when_to_seek_care,
        limitations=validated.limitations,
        citations=[Citation(**c.model_dump(mode="json")) for c in verified],
        evidence_count=len(evidence),
    )
    return {
        "assessment": snapshot,
        "guidance": detail,
        "prompt_version": get_settings().llm_prompt_version,
        "generated_at": datetime.now(UTC),
        # Minimal workflow metadata (Phase 5 addition; internal graph state
        # is never exposed):
        "workflow_status": (
            "pending_review" if state.get("review_required") else "completed"
        ),
        "review_required": bool(state.get("review_required")),
        "safety_flags": state.get("safety_flags") or [],
    }
