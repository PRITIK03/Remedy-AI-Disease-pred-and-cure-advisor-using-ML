"""Typed payload models for the read-only MCP tools (Phase 8).

These are the *structured output* schemas. They deliberately contain no
write-shaped models, no user identifiers, and no secrets: every field is a
read projection of data the calling user already owns.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssessmentSummary(BaseModel):
    """One assessment as exposed to MCP clients."""

    id: str = Field(description="Assessment UUID.")
    created_at: str
    model_version: str
    selected_model: str
    disease_probability: float = Field(
        ge=0.0, le=1.0, description="Model-estimated probability (NOT a diagnosis)."
    )
    predicted_disease: bool
    probability_label: Literal["model_estimated_probability"] = (
        "model_estimated_probability"
    )
    source: str = Field(default="manual", description="'manual' or 'report'.")
    report_id: str | None = None
    input_features: dict[str, float] = Field(
        description="The 13 model inputs used for this prediction."
    )


class AssessmentHistoryPage(BaseModel):
    """Paginated history."""

    items: list[AssessmentSummary]
    total: int
    limit: int
    offset: int


class ReportMetadata(BaseModel):
    """Uploaded report metadata + extraction provenance (no file, no storage key)."""

    id: str
    filename: str
    mime_type: str
    file_size_bytes: int
    status: str
    created_at: str
    extraction_model: str | None = None
    prompt_version: str | None = None
    extracted_field_count: int = Field(
        default=0, description="How many of the 13 metrics were extracted."
    )
    notes: str | None = None


class ModelInformation(BaseModel):
    """Safe ML metadata — no filesystem paths, no serialized estimators."""

    model_version: str
    selected_model: str
    feature_count: int
    features: list[str]
    target_definition: str = Field(
        description="What the positive class means (documented semantics)."
    )
    target_transformation: str | None = None
    positive_class: int
    probability_label: Literal["model_estimated_probability"] = (
        "model_estimated_probability"
    )
    dataset_name: str | None = None
    dataset_hash: str | None = None
    evaluation: dict[str, object] = Field(
        default_factory=dict,
        description="Evaluation metadata (metrics/versions) when available.",
    )
    disclaimer: str


class EvidenceItem(BaseModel):
    """One retrieved knowledge chunk — already verified against the source manifest."""

    title: str
    source: str
    url: str
    section: str
    content: str
    similarity: float


class ErrorPayload(BaseModel):
    """Uniform, non-sensitive error shape for tool failures."""

    error: Literal[
        "not_found",
        "forbidden",
        "unavailable",
        "invalid_input",
    ]
    message: str


__all__ = [
    "AssessmentSummary",
    "AssessmentHistoryPage",
    "ReportMetadata",
    "ModelInformation",
    "EvidenceItem",
    "ErrorPayload",
]
