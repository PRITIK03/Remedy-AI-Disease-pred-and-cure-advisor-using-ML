"""API-facing guidance service — glues assessment storage to the RAG/LLM
flow and maps typed errors onto HTTP semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.schemas.guidance import AssessmentSnapshot, GuidanceDetail
from backend.app.services import assessment_service

logger = get_logger("backend.guidance_service")


def run_guidance(db: Session, assessment_id: UUID) -> dict:
    """Load the assessment, run RAG+LLM, return the response payload."""
    from backend.app.rag.service import (
        GuidanceError,
        GuidanceUnavailableError,
        generate_guidance,
    )

    row = assessment_service.get_assessment(db, assessment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )

    settings = get_settings()
    try:
        guidance = generate_guidance(db, row)
    except GuidanceUnavailableError as exc:
        # 503: the capability exists but this deployment can't serve it now.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except GuidanceError as exc:
        logger.error("Guidance generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI guidance is temporarily unavailable. Please try again later.",
        ) from exc

    snapshot = AssessmentSnapshot(
        assessment_id=str(row.id),
        model_version=row.model_version,
        selected_model=row.selected_model,
        predicted_disease=bool(row.predicted_disease),
        disease_probability=round(float(row.disease_probability), 5),
    )
    detail = GuidanceDetail(**guidance)
    return {
        "assessment": snapshot,
        "guidance": detail,
        "prompt_version": settings.llm_prompt_version,
        "generated_at": datetime.now(UTC),
    }
