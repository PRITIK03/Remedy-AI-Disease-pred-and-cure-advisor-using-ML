"""Deterministic routing for the guidance workflow.

Routing decisions are PURE FUNCTIONS of the state — the LLM never chooses
where the graph goes next. Review is forced by explicit, auditable
conditions only.
"""

from __future__ import annotations

from typing import Any

from backend.app.agents.state import GuidanceGraphState

# High-risk threshold for the model-estimated probability. Higher outputs
# are routed to human review — a conservative demo-policy choice.
HIGH_RISK_PROBABILITY = 0.75


def route_after_load(state: GuidanceGraphState) -> str:
    """Missing assessment → error path; otherwise continue."""
    if state.get("model_result") is None:
        return "error"
    return "retrieve_evidence"


def route_after_safety(state: GuidanceGraphState) -> str:
    """Deterministic review decision. NO LLM involvement, ever."""
    if state.get("workflow_status") == "failed":
        return "error"

    # 1. Safety flags always force review.
    if state.get("safety_flags"):
        return "human_review"

    # 2. High-risk model output forces review.
    model_result = state.get("model_result") or {}
    probability = float(model_result.get("disease_probability", 0.0))
    if probability >= HIGH_RISK_PROBABILITY:
        return "human_review"

    # 3. Degraded RAG (evidence missing when it should exist) forces review.
    if state.get("rag_error") and not state.get("evidence_available"):
        return "human_review"

    # 4. Normal successful output.
    return "finalize"


def review_required_for(state: GuidanceGraphState) -> bool:
    """Whether THIS state will be routed to review (mirror of the route
    decision, used by finalize to stamp an explicit value)."""
    return route_after_safety(state) == "human_review"


def review_reason(state: GuidanceGraphState) -> str | None:
    """Human-readable reason for review (first matching rule wins)."""
    flags = state.get("safety_flags") or []
    if flags:
        return f"safety_flags: {', '.join(flags)}"
    model_result = state.get("model_result") or {}
    if float(model_result.get("disease_probability", 0.0)) >= HIGH_RISK_PROBABILITY:
        return (
            f"high_risk_model_output: probability="
            f"{model_result.get('disease_probability')} >= "
            f"{HIGH_RISK_PROBABILITY}"
        )
    if state.get("rag_error"):
        return f"rag_degraded: {state.get('rag_error')}"
    return None


def build_review_payload(state: GuidanceGraphState) -> dict[str, Any]:
    """Payload for the human-review boundary. No secrets, no graph internals."""
    return {
        "assessment_id": state.get("assessment_id"),
        "model_result": state.get("model_result"),
        "generated_guidance": state.get("guidance"),
        "safety_flags": state.get("safety_flags") or [],
        "reason_for_review": review_reason(state),
    }
