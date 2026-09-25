"""Assessment service — orchestrates ML prediction and persistence.

Flow for POST /api/v1/assessments:
    Pydantic validation (schema) → ML predictor → structured result
    → database persistence → response.

The saved row always records the model version actually used.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.logging import get_logger
from backend.app.db.models import Assessment
from backend.app.schemas.assessment import AssessmentCreate

logger = get_logger("backend.assessment_service")

FEATURE_COLUMNS = (
    "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
    "thalach", "exang", "oldpeak", "slope", "ca", "thal",
)


def create_assessment(
    db: Session,
    model_service: Any,
    payload: AssessmentCreate,
) -> Assessment:
    """Run prediction via the model service and persist the result."""
    features = payload.model_dump()
    result = model_service.predict(features)

    assessment = Assessment(
        **{col: features[col] for col in FEATURE_COLUMNS},
        model_version=result["model_version"],
        predicted_disease=bool(result["predicted_disease"]),
        disease_probability=float(result["disease_probability"]),
        selected_model=result.get("selected_model", "unknown"),
    )
    db.add(assessment)
    db.flush()  # get PK before commit (session dependency commits on success)
    logger.info(
        "Assessment created: id=%s model_version=%s",
        assessment.id,
        assessment.model_version,
    )
    return assessment


def get_assessment(db: Session, assessment_id: UUID) -> Assessment | None:
    return db.get(Assessment, assessment_id)


def list_assessments(
    db: Session,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Assessment], int]:
    """Paginated listing (newest first) with total count."""
    total = db.scalar(select(func.count()).select_from(Assessment)) or 0
    stmt = (
        select(Assessment)
        .order_by(Assessment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(stmt))
    return items, int(total)


def to_response(assessment: Assessment) -> dict[str, Any]:
    """Serialize an ORM row into the response schema shape."""
    return {
        "id": str(assessment.id),
        "model_version": assessment.model_version,
        "selected_model": assessment.selected_model,
        "predicted_disease": assessment.predicted_disease,
        # Round to the persisted precision (Numeric(6,5)) so a fetched row
        # is always exactly equal to the value returned at creation time.
        "disease_probability": round(float(assessment.disease_probability), 5),
        "probability_label": "model_estimated_probability",
        "created_at": assessment.created_at,
        "input_features": {col: float(assessment.__dict__[col]) for col in FEATURE_COLUMNS},
    }
