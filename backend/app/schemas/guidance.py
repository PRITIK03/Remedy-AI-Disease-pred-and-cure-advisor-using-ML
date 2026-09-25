"""Guidance API schemas — the response keeps MODEL OUTPUT and
AI-GENERATED EVIDENCE-GROUNDED GUIDANCE as clearly separated objects."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.rag.schemas import Citation


class AssessmentSnapshot(BaseModel):
    """Authoritative ML output — copied from the stored assessment, never
    generated or modifiable by the LLM."""

    assessment_id: str
    model_version: str
    selected_model: str
    predicted_disease: bool
    disease_probability: float = Field(ge=0.0, le=1.0)


class GuidanceDetail(BaseModel):
    summary: str
    model_explanation: str
    key_factors: list[str] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
    when_to_seek_care: list[str] = Field(default_factory=list)
    limitations: str
    citations: list[Citation] = Field(default_factory=list)
    evidence_count: int = Field(ge=0)


class GuidanceResponse(BaseModel):
    assessment: AssessmentSnapshot
    guidance: GuidanceDetail
    prompt_version: str = Field(description="Prompt version used (audit trail).")
    generated_at: datetime
    # --- Phase 5 workflow metadata (minimal; internal graph state never
    # exposed). Absent from Phase 4 responses, so old clients that ignore
    # unknown fields stay compatible.
    workflow_status: str = Field(
        default="completed",
        description='"completed" or "pending_review".',
    )
    review_required: bool = Field(
        default=False,
        description="True when the case was flagged for human review.",
    )
    safety_flags: list[str] = Field(
        default_factory=list,
        description="Safety flags raised during the workflow (if any).",
    )
