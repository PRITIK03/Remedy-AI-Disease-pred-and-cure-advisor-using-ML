"""Assessment API endpoints (/api/v1/assessments) — Phase 6.

Every endpoint requires an authenticated user. All reads are scoped to the
owner; a foreign or missing id yields the SAME 404 (no existence oracle).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.app.db.models import User
from backend.app.dependencies import DbSessionDep, ModelServiceDep
from backend.app.dependencies_auth import CurrentUserDep, enforce_csrf
from backend.app.schemas.assessment import (
    AssessmentCreate,
    AssessmentListResponse,
    AssessmentResponse,
)
from backend.app.schemas.guidance import GuidanceResponse
from backend.app.services import assessment_service
from backend.app.services.guidance_service import run_guidance

router = APIRouter(
    prefix="/assessments",
    tags=["assessments"],
    dependencies=[Depends(enforce_csrf)],
)


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


def _get_owned_or_404(db, user: User, assessment_id: UUID):
    """Single choke point for ownership-scoped fetches."""
    row = assessment_service.get_assessment_for_user(db, assessment_id, user.id)
    if row is None:
        # Same 404 for missing AND foreign — no oracle for guessing ids.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    return row


@router.post(
    "",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a cardiovascular risk assessment",
    description=(
        "Runs the ML model (v2) on the 13 input features, persists the "
        "result owned by the authenticated user. The output is a "
        "model-estimated probability from an educational prototype — **not "
        "a medical diagnosis**."
    ),
)
def create_assessment(
    payload: AssessmentCreate,
    model_service: ModelServiceDep,
    db: DbSessionDep,
    user: CurrentUserDep,
) -> AssessmentResponse:
    row = assessment_service.create_assessment(db, model_service, payload, user.id)
    # NOTE: no logging of `payload` here (or anywhere) — the 13 inputs are
    # health data. Only the row id and model version are logged downstream.
    return AssessmentResponse(**assessment_service.to_response(row))


@router.get(
    "",
    response_model=AssessmentListResponse,
    summary="List YOUR assessments (paginated, newest first)",
)
def list_assessments(
    db: DbSessionDep,
    user: CurrentUserDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AssessmentListResponse:
    items, total = assessment_service.list_assessments(
        db, user_id=user.id, limit=limit, offset=offset
    )
    return AssessmentListResponse(
        items=[AssessmentResponse(**assessment_service.to_response(a)) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{assessment_id}",
    response_model=AssessmentResponse,
    summary="Retrieve one of YOUR assessments by id",
    responses={404: {"description": "Assessment not found"}},
)
def get_assessment(
    assessment_id: UUID, db: DbSessionDep, user: CurrentUserDep
) -> AssessmentResponse:
    row = _get_owned_or_404(db, user, assessment_id)
    return AssessmentResponse(**assessment_service.to_response(row))


@router.get(
    "/{assessment_id}/explanation",
    response_model=ExplanationResponse,
    summary="Model feature contributions for one of YOUR assessments",
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
    user: CurrentUserDep,
) -> ExplanationResponse:
    row = _get_owned_or_404(db, user, assessment_id)
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
    summary="AI-generated, evidence-grounded guidance for one of YOUR assessments",
    description=(
        "Retrieves trusted medical evidence (pgvector similarity search) and "
        "generates structured AI guidance with verified citations. **This is "
        "not a diagnosis and not medical advice.** The ML prediction in the "
        "response is the authoritative model output; the LLM cannot alter it. "
        "Only runs when explicitly requested; providers must be configured."
    ),
    responses={
        404: {"description": "Assessment not found"},
        202: {"description": "Flagged for human review; guidance not released"},
        502: {"description": "Guidance generation failed (provider error)"},
        503: {"description": "Guidance not configured / knowledge base empty"},
    },
)
def get_assessment_guidance(
    assessment_id: UUID,
    db: DbSessionDep,
    user: CurrentUserDep,
) -> GuidanceResponse:
    _get_owned_or_404(db, user, assessment_id)  # ownership before workflow
    return GuidanceResponse(**run_guidance(db, assessment_id, user_id=user.id))
