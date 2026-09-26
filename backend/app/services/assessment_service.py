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
    user_id: UUID | None = None,
    source: str = "manual",
    report_id: UUID | None = None,
) -> Assessment:
    """Run prediction via the model service and persist the result.

    Phase 6: new assessments are always stamped with the authenticated
    owner. user_id=None only occurs for legacy callers/tests.
    Phase 7: source ('manual' | 'report') and optional report_id tracking.
    """
    features = payload.model_dump()
    result = model_service.predict(features)

    assessment = Assessment(
        **{col: features[col] for col in FEATURE_COLUMNS},
        user_id=user_id,
        source=source,
        report_id=report_id,
        model_version=result["model_version"],
        predicted_disease=bool(result["predicted_disease"]),
        disease_probability=float(result["disease_probability"]),
        selected_model=result.get("selected_model", "unknown"),
    )
    db.add(assessment)
    db.flush()  # get PK before commit (session dependency commits on success)
    logger.info(
        "Assessment created: id=%s model_version=%s source=%s",
        assessment.id,
        assessment.model_version,
        assessment.source,
    )
    return assessment



def get_assessment(db: Session, assessment_id: UUID) -> Assessment | None:
    return db.get(Assessment, assessment_id)


def get_assessment_for_user(
    db: Session, assessment_id: UUID, user_id: UUID
) -> Assessment | None:
    """Ownership-scoped fetch: returns None when the row is missing OR owned
    by someone else. Callers answer 404 either way — no existence oracle."""
    row = db.get(Assessment, assessment_id)
    if row is None or row.user_id != user_id:
        return None
    return row


def list_assessments(
    db: Session,
    *,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Assessment], int]:
    """Paginated listing of ONE user's assessments (newest first)."""
    base = select(func.count()).select_from(Assessment).where(
        Assessment.user_id == user_id
    )
    total = db.scalar(base) or 0
    stmt = (
        select(Assessment)
        .where(Assessment.user_id == user_id)
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
        "source": getattr(assessment, "source", "manual") or "manual",
        "report_id": str(assessment.report_id) if getattr(assessment, "report_id", None) else None,
    }

