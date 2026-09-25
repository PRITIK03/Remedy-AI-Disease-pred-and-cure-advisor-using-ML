"""Guidance service — orchestrates the Phase 4 RAG + LLM flow.

    assessment (DB) → model result (authoritative) → retrieval query
    → pgvector evidence → LLM (structured) → citation verification
    → safety pass → response

The ML output is NEVER produced or altered by the LLM. If anything in the
chain fails, the endpoint degrades gracefully with a typed error.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.llm.client import LLMClient, LLMError, get_llm_client
from backend.app.llm.prompts import PROMPT_VERSION, build_user_prompt, SYSTEM_PROMPT_V1
from backend.app.rag.safety import detect_emergency
from backend.app.rag.schemas import (
    Citation,
    Evidence,
    HealthGuidanceResponse,
    verify_citations,
)

logger = get_logger("backend.rag.service")


class GuidanceError(RuntimeError):
    """Generic guidance failure (provider down, malformed output, ...)."""


class GuidanceUnavailableError(GuidanceError):
    """RAG/LLM providers not configured or knowledge base empty."""


def build_retrieval_query(assessment: Any) -> str:
    """Deterministic query from structured assessment values.

    Uses the stable categorical/numeric fields most relevant to
    cardiovascular evidence; excludes identifiers and improbable noise.
    """
    parts = [
        "heart disease risk",
        f"age {int(assessment.age)}",
        f"chest pain type {int(assessment.cp)}",
        f"blood pressure {int(assessment.trestbps)}",
        f"cholesterol {int(assessment.chol)}",
    ]
    if assessment.exang:
        parts.append("exercise-induced angina")
    if assessment.fbs:
        parts.append("high blood sugar diabetes risk")
    if assessment.restecg:
        parts.append("abnormal resting ECG")
    if float(assessment.oldpeak) > 0:
        parts.append("ST depression exercise")
    if assessment.thal:
        parts.append("thallium stress test abnormality")
    if int(assessment.ca) > 0:
        parts.append("coronary artery blockage")
    return ", ".join(parts)


def generate_guidance(
    db: Session,
    assessment: Any,
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    """Full flow: retrieve → LLM → validate → verify citations → safety.

    Returns a dict shaped like the API response's `guidance` field.
    Raises typed errors; the endpoint maps them to HTTP.
    """
    from backend.app.rag.retrieval import (
        KnowledgeBaseEmpty,
        RetrievalUnavailableError,
        retrieve_relevant_evidence,
    )

    settings = get_settings()

    # --- 0. Provider configuration ------------------------------------- #
    if not settings.llm_configured:
        raise GuidanceUnavailableError(
            "AI guidance is not configured on this server "
            "(LLM_API_KEY / LLM_MODEL missing)."
        )

    # --- 1. Build retrieval query from the stored assessment ----------- #
    query = build_retrieval_query(assessment)

    # --- 2. Retrieve evidence (short-circuit if none) ------------------- #
    try:
        evidence = retrieve_relevant_evidence(db, query)
    except KnowledgeBaseEmpty:
        raise GuidanceUnavailableError(
            "The knowledge base is empty. Ingest sources first."
        ) from None
    except RetrievalUnavailableError as exc:
        raise GuidanceError(str(exc)) from exc

    if not evidence:
        return {
            "summary": (
                "I don't have sufficient evidence in the current knowledge "
                "base to answer that safely."
            ),
            "model_explanation": (
                "The ML estimate shown above was produced by the predictive "
                "model and is independent of this guidance."
            ),
            "key_factors": [],
            "guidance": [],
            "when_to_seek_care": [],
            "limitations": "No relevant evidence was retrieved for this assessment.",
            "citations": [],
            "evidence_count": 0,
        }

    # --- 3. Call the LLM with structured inputs ------------------------- #
    model_result = {
        "model_version": assessment.model_version,
        "predicted_disease": bool(assessment.predicted_disease),
        "disease_probability": float(assessment.disease_probability),
        "selected_model": assessment.selected_model,
    }
    features = {
        col: float(assessment.__dict__[col])
        for col in (
            "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
            "thalach", "exang", "oldpeak", "slope", "ca", "thal",
        )
    }

    llm_client = llm or get_llm_client()
    user_prompt = build_user_prompt(features, model_result, evidence=[
        e.model_dump(mode="json") for e in evidence
    ])
    try:
        raw = llm_client.generate_structured(
            SYSTEM_PROMPT_V1, user_prompt, HealthGuidanceResponse
        )
    except LLMError as exc:
        raise GuidanceError(f"AI guidance generation failed: {exc}") from exc

    # --- 4. Verify citations against retrieved evidence ----------------- #
    verified = verify_citations(raw, evidence)

    # --- 5. Safety pass -------------------------------------------------- #
    summary = raw.summary
    verdict = detect_emergency(query)  # query is built from assessment only
    if verdict.escalate_emergency:
        from backend.app.rag.safety import EMERGENCY_NOTICE

        summary = f"{EMERGENCY_NOTICE}\n\n{summary}"

    return {
        "summary": summary,
        "model_explanation": raw.model_explanation,
        "key_factors": raw.key_factors,
        "guidance": raw.guidance,
        "when_to_seek_care": raw.when_to_seek_care,
        "limitations": raw.limitations,
        "citations": [c.model_dump(mode="json") for c in verified],
        "evidence_count": len(evidence),
    }
