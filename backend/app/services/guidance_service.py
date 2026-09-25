"""API-facing guidance service — glues assessment storage to the LangGraph
workflow (Phase 5) and maps typed errors onto HTTP semantics.

Phase 5 change: the flow inside is now the LangGraph guidance graph
(backend/app/agents/); the API contract is unchanged apart from the added
workflow metadata fields (workflow_status, review_required, safety_flags).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.logging import get_logger

logger = get_logger("backend.guidance_service")


def run_guidance(db: Session, assessment_id: UUID) -> dict:
    """Run the LangGraph guidance workflow for one assessment.

    The graph reuses the existing services (assessment storage, RAG
    retrieval, LLM abstraction, safety/citation validation) behind a
    deterministic orchestration. Review-pending is surfaced as 202 so the
    frontend can distinguish it from a normal response.
    """
    from backend.app.agents import service as agent_service

    try:
        return agent_service.run_guidance_workflow(db, str(assessment_id))
    except agent_service.AssessmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        ) from exc
    except agent_service.GuidanceNotConfiguredError as exc:
        # Capability exists in code but this deployment lacks credentials.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI guidance is not configured on this server. "
                "Set LLM_API_KEY / LLM_MODEL (see .env.example)."
            ),
        ) from exc
    except agent_service.ReviewPendingError as exc:
        # Flagged/high-risk case: do NOT release generated guidance. Tell
        # the client review is pending (202 Accepted, not completed).
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={
                "message": "This assessment has been flagged for additional review.",
                "review_required": True,
                "workflow_status": "pending_review",
                "assessment": exc.payload.get("model_result"),
            },
        ) from exc
    except agent_service.WorkflowFailedError as exc:
        logger.error("Guidance workflow failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI guidance is temporarily unavailable. Please try again later.",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - operational safety net
        logger.exception("Guidance workflow crashed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI guidance is not available on this deployment. "
                "Providers may not be configured."
            ),
        ) from exc
