"""Assessment API endpoints (/api/v1/assessments)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.app.dependencies import DbSessionDep, ModelServiceDep
from backend.app.schemas.assessment import (
    AssessmentCreate,
    AssessmentListResponse,
    AssessmentResponse,
)
from backend.app.schemas.guidance import GuidanceResponse
from backend.app.services import assessment_service
from backend.app.services.guidance_service import run_guidance

router = APIRouter(prefix="/assessments", tags=["assessments"])


class FeatureContribution(BaseModel):
    feature: str = Field(description="Transformed feature name.")
    shap_value: float = Field(
        description=(
            "Model contribution (SHAP) toward the disease class. Positive "
            "pushes the estimate up, negative down. NOT a causal effect."
        )
    )


class ExplanationResponse(BaseModel):
    assessment_id: str
    model_version: str
    method: str = Field(description="Explanation method used.")
    contributions: list[FeatureContribution]
    note: str = Field(description="Interpretation guidance for this output.")


@router.post(
    "",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cardiovascular risk assessment",
    description=(
        "Runs the ML model (v2) on the 13 input features and persists the "
        "result. The output is a model-estimated probability of the disease "
        "class from an educational prototype — **not a medical diagnosis**."
    ),
)
def create_assessment(
    payload: AssessmentCreate,
    model_service: ModelServiceDep,
    db: DbSessionDep,
) -> AssessmentResponse:
    row = assessment_service.create_assessment(db, model_service, payload)
    return AssessmentResponse(**assessment_service.to_response(row))


@router.get(
    "",
    response_model=AssessmentListResponse,
    summary="List assessments (paginated, newest first)",
)
def list_assessments(
    db: DbSessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AssessmentListResponse:
    items, total = assessment_service.list_assessments(db, limit=limit, offset=offset)
    return AssessmentListResponse(
        items=[AssessmentResponse(**assessment_service.to_response(a)) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{assessment_id}",
    response_model=AssessmentResponse,
    summary="Retrieve one assessment by id",
    responses={404: {"description": "Assessment not found"}},
)
def get_assessment(assessment_id: UUID, db: DbSessionDep) -> AssessmentResponse:
    row = assessment_service.get_assessment(db, assessment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    return AssessmentResponse(**assessment_service.to_response(row))


@router.get(
    "/{assessment_id}/explanation",
    response_model=ExplanationResponse,
    summary="Model feature contributions for one assessment",
    description=(
        "Returns per-feature model contributions (SHAP) for a stored "
        "assessment. These are model contributions — **not** causal or "
        "clinical explanations."
    ),
    responses={404: {"description": "Assessment not found"}},
)
def get_assessment_explanation(
    assessment_id: UUID,
    model_service: ModelServiceDep,
    db: DbSessionDep,
) -> ExplanationResponse:
    row = assessment_service.get_assessment(db, assessment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    features: dict[str, Any] = {
        col: float(row.__dict__[col]) for col in assessment_service.FEATURE_COLUMNS
    }
    explanation = model_service.explain(features, top_k=8)
    return ExplanationResponse(
        assessment_id=str(row.id),
        model_version=row.model_version,
        method=explanation.get("method", "unavailable"),
        contributions=[
            FeatureContribution(feature=c["feature"], shap_value=c["shap_value"])
            for c in explanation.get("contributions", [])
        ],
        note=explanation.get(
            "note", "Model contributions; not causal explanations."
        ),
    )


@router.post(
    "/{assessment_id}/guidance",
    response_model=GuidanceResponse,
    summary="AI-generated, evidence-grounded guidance for one assessment",
    description=(
        "Retrieves trusted medical evidence (pgvector similarity search) and "
        "generates structured AI guidance with verified citations. **This is "
        "not a diagnosis and not medical advice.** The ML prediction in the "
        "response is the authoritative model output; the LLM cannot alter it. "
        "Only runs when explicitly requested; providers must be configured."
    ),
    responses={
        404: {"description": "Assessment not found"},
        502: {"description": "Guidance generation failed (provider error)"},
        503: {"description": "Guidance not configured / knowledge base empty"},
    },
)
def get_assessment_guidance(
    assessment_id: UUID,
    db: DbSessionDep,
) -> GuidanceResponse:
    return GuidanceResponse(**run_guidance(db, assessment_id))
