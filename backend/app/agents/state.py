"""Typed LangGraph state for the guidance workflow.

Design rules (per phase spec):
- Raw structured values only — no formatted prompt strings in state.
- No secrets, no personal data beyond the assessment's ML feature summary.
- `model_result` is AUTHORITATIVE: produced once by `load_assessment` from
  the stored row and never overwritten by any LLM-generated node.
- `metadata` merges via a reducer so no node can clobber another's entries.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

# NOTE: evidence/guidance are held as plain dicts/JSON-compatible values in
# state (LangGraph checkpointer serializes state via msgpack; Pydantic
# objects are converted at the boundaries by the nodes that produce them).


def merge_metadata(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    """Reducer: merge metadata dicts instead of replacing them."""
    merged: dict[str, Any] = {**(left or {})}
    merged.update(right or {})
    return merged


class GuidanceGraphState(TypedDict, total=False):
    # --- Inputs ------------------------------------------------------------ #
    assessment_id: str

    # --- Loaded assessment (authoritative model output lives in model_result)
    assessment: dict[str, Any] | None  # feature values + timestamps (raw row)

    # --- Authoritative ML output: set once in load_assessment; no node that
    # touches LLM output may write here. Locked in graph.py via a channel.
    model_result: dict[str, Any] | None

    # --- RAG ---------------------------------------------------------------- #
    evidence: list[dict[str, Any]]  # Evidence.model_dump() values
    evidence_available: bool
    rag_error: str | None

    # --- LLM ---------------------------------------------------------------- #
    guidance: dict[str, Any] | None  # validated HealthGuidanceResponse dump
    llm_error: str | None

    # --- Safety / routing ---------------------------------------------------- #
    safety_flags: list[str]
    review_required: bool
    review_reason: str | None
    review_status: str  # "not_required" | "pending" | "approved" | "rejected"

    # --- Control ------------------------------------------------------------- #
    errors: Annotated[list[str], operator.add]  # append-only error channel
    workflow_status: str  # "running" | "finalized" | "failed" | "pending_review"
    metadata: Annotated[dict[str, Any], merge_metadata]
