"""Pydantic schemas for medical report extraction and endpoints (Phase 7).

Ensures strict typing, field-level confidence ratings, textual evidence,
and human review capabilities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ExtractedField(BaseModel):
    """Extraction representation for a single metric with confidence and evidence."""

    value: float | int | None = Field(
        default=None,
        description="Parsed numerical value or categorical code, or null if not detected.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    evidence: str = Field(
        default="",
        description="Exact quote or phrase from document supporting this value.",
    )


class CardiovascularReportExtraction(BaseModel):
    """Raw structured extraction from LLM multimodal parser.

    Represents all 13 cardiovascular metrics with evidence.
    """

    age: ExtractedField = Field(default_factory=ExtractedField)
    sex: ExtractedField = Field(default_factory=ExtractedField)
    cp: ExtractedField = Field(default_factory=ExtractedField)
    trestbps: ExtractedField = Field(default_factory=ExtractedField)
    chol: ExtractedField = Field(default_factory=ExtractedField)
    fbs: ExtractedField = Field(default_factory=ExtractedField)
    restecg: ExtractedField = Field(default_factory=ExtractedField)
    thalach: ExtractedField = Field(default_factory=ExtractedField)
    exang: ExtractedField = Field(default_factory=ExtractedField)
    oldpeak: ExtractedField = Field(default_factory=ExtractedField)
    slope: ExtractedField = Field(default_factory=ExtractedField)
    ca: ExtractedField = Field(default_factory=ExtractedField)
    thal: ExtractedField = Field(default_factory=ExtractedField)

    notes: str = Field(
        default="",
        description="General observations or warnings about the report quality or content.",
    )


class ExtractionSummaryItem(BaseModel):
    field_name: str
    label: str
    value: float | int | None
    confidence: float
    evidence: str


class ReportExtractionResponse(BaseModel):
    """Returned when report is extracted and ready for user review."""

    id: UUID
    report_id: UUID
    extraction_model: str
    prompt_version: str
    extracted_features: dict[str, float | int | None]
    confidences: dict[str, float]
    evidence: dict[str, str]
    notes: str | None = None
    created_at: datetime


class MedicalReportResponse(BaseModel):
    """Detailed response for an uploaded report."""

    id: UUID
    filename: str
    mime_type: str
    file_size_bytes: int
    file_hash: str
    status: str
    error_message: str | None = None
    created_at: datetime
    latest_extraction: ReportExtractionResponse | None = None


class MedicalReportListResponse(BaseModel):
    items: list[MedicalReportResponse]
    total: int


class ConfirmReportAssessmentRequest(BaseModel):
    """Payload sent by user when confirming/editing extracted values to create assessment.

    Inherits/re-validates all 13 strict fields required by the ML model.
    """

    age: int = Field(ge=25, le=100)
    sex: Literal[0, 1]
    cp: Literal[0, 1, 2, 3]
    trestbps: int = Field(ge=80, le=220)
    chol: int = Field(ge=100, le=600)
    fbs: Literal[0, 1]
    restecg: Literal[0, 1, 2]
    thalach: int = Field(ge=60, le=220)
    exang: Literal[0, 1]
    oldpeak: float = Field(ge=0.0, le=10.0)
    slope: Literal[0, 1, 2]
    ca: Literal[0, 1, 2, 3, 4]
    thal: Literal[0, 1, 2, 3]

    @field_validator("oldpeak")
    @classmethod
    def _round_oldpeak(cls, v: float) -> float:
        return round(float(v), 2)
