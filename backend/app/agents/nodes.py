"""Graph nodes — each does exactly ONE job, reusing existing services.

No node talks to a vendor SDK directly: RAG goes through
backend.app.rag.retrieval, LLM through backend.app.llm.client, safety
through backend.app.rag.safety. The model result is read from the stored
assessment — never recalculated, never taken from LLM output.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from backend.app.agents.state import GuidanceGraphState
from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger("backend.agents.nodes")

T = TypeVar("T")

# Transient-failure retry policy: small and only for network-type failures.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0


def with_retries(
    fn: Callable[[], T],
    *,
    transient: tuple[type[Exception], ...],
    what: str,
    on_exhausted: Callable[[Exception], T] | None = None,
) -> tuple[T, int]:
    """Run fn with up to MAX_ATTEMPTS tries, retrying ONLY transient errors.

    Non-transient errors (validation, safety, not-found, configuration) are
    raised immediately — retrying them would be wrong, not just wasteful.
    Returns (result, attempts). On exhausted transient retries the
    on_exhausted callback supplies the degraded result (attempts then equals
    MAX_ATTEMPTS); if on_exhausted re-raises, the final error propagates and
    the caller must treat attempts as MAX_ATTEMPTS.
    """
    last: Exception | None = None
    attempts = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        try:
            return fn(), attempts
        except transient as exc:  # transient only
            last = exc
            if attempt < MAX_ATTEMPTS:
                logger.warning(
                    "%s transient failure (attempt %d/%d): %s",
                    what, attempt, MAX_ATTEMPTS, exc,
                )
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        except Exception:
            # Anything else: do not retry.
            raise
    assert last is not None
    if on_exhausted is None:
        # Attach the attempt count so callers can record it in state.
        last.attempts = attempts  # type: ignore[attr-defined]
        raise last
    return on_exhausted(last), attempts


# --------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------- #


def make_load_assessment_node(db, assessment_id: str):
    """Build the load_assessment node bound to this run's inputs.

    The assessment row (including the authoritative model result) is loaded
    ONCE. If it does not exist, the node records a terminal error instead of
    raising — the router sends missing assessments to the error path.
    """

    def _node(state: GuidanceGraphState) -> dict[str, Any]:
        from backend.app.services.assessment_service import get_assessment
        from backend.app.services import assessment_service

        row = get_assessment(db, __import__("uuid").UUID(assessment_id))
        if row is None:
            return {
                "errors": [f"assessment_not_found:{assessment_id}"],
                "workflow_status": "failed",
                "model_result": None,
            }
        return {
            "assessment": {
                col: float(row.__dict__[col])
                for col in assessment_service.FEATURE_COLUMNS
            },
            "model_result": {
                "model_version": row.model_version,
                "selected_model": row.selected_model,
                "predicted_disease": bool(row.predicted_disease),
                "disease_probability": round(float(row.disease_probability), 5),
            },
            "metadata": {"loaded_at": time.time()},
        }

    return _node


def make_retrieve_evidence_node(db):
    """retrieve_evidence — calls the EXISTING RAG retrieval service.

    Transient embedding/retrieval failures are retried a couple of times;
    exhausted/unavailable RAG degrades to a constrained no-evidence run
    (routing decision, not a crash). Configuration errors also degrade but
    are flagged in metadata so operators can see why.
    """

    def _node(state: GuidanceGraphState) -> dict[str, Any]:
        from backend.app.rag.retrieval import (
            KnowledgeBaseEmptyError,
            RetrievalUnavailableError,
            retrieve_relevant_evidence,
        )
        from backend.app.rag.service import build_retrieval_query

        settings = get_settings()
        if not settings.rag_configured:
            logger.warning("RAG not configured; running without evidence")
            return {
                "evidence": [],
                "evidence_available": False,
                "rag_error": "embedding provider not configured",
                "metadata": {"rag_degraded": "not_configured"},
            }

        query = build_retrieval_query_values(state)

        def _on_exhausted(exc: Exception) -> dict[str, Any]:
            return {
                "evidence": [],
                "evidence_available": False,
                "rag_error": str(exc),
                "metadata": {"rag_degraded": "transient_failure"},
            }

        try:
            evidence_models, rag_attempts = with_retries(
                lambda: retrieve_relevant_evidence(db, query),
                transient=(RetrievalUnavailableError,),
                on_exhausted=lambda exc: [],
                what="retrieve_evidence",
            )
        except KnowledgeBaseEmptyError:  # noqa: FURB110 - distinct degradation
            return {
                "evidence": [],
                "evidence_available": False,
                "rag_error": "knowledge base is empty",
                "metadata": {"rag_degraded": "empty_knowledge_base"},
            }

        # On transient exhaustion the on_exhausted hook returns [] with the
        # error captured in rag_error below; distinguish via rag_error field.
        rag_error = None
        if not evidence_models:
            rag_error = "retrieval failed after retries"

        # Store as JSON-compatible dicts (checkpoint-serializable state).
        return {
            "evidence": [
                e.model_dump(mode="json") if hasattr(e, "model_dump") else e
                for e in evidence_models
            ],
            "evidence_available": bool(evidence_models),
            "rag_error": rag_error,
            "metadata": {"attempts:retrieve_evidence": rag_attempts},
        }

    return _node


def make_generate_guidance_node(db, llm_client=None):
    """generate_guidance — calls the EXISTING LLM abstraction.

    Never calls OpenRouter directly. Transient LLM network failures are
    retried; schema-validation failures are NOT (they'd fail again).
    """

    def _node(state: GuidanceGraphState) -> dict[str, Any]:
        from backend.app.llm.client import LLMError, get_llm_client
        from backend.app.llm.prompts import SYSTEM_PROMPT_V1, build_user_prompt
        from backend.app.rag.schemas import HealthGuidanceResponse

        if not state.get("evidence_available"):
            # No evidence → deterministic constrained response (no LLM call).
            fallback = HealthGuidanceResponse(
                summary=(
                    "I don't have sufficient evidence in the current "
                    "knowledge base to answer that safely."
                ),
                model_explanation=(
                    "The ML estimate shown above was produced by the "
                    "predictive model and is independent of this guidance."
                ),
                limitations=(
                    "No relevant evidence was retrieved for this assessment."
                ),
                citations=[],
            )
            return {
                "guidance": fallback.model_dump(mode="json"),
                "metadata": {"guidance_source": "constrained_fallback"},
            }

        model_result = state["model_result"]
        evidence = state.get("evidence") or []
        features = state.get("assessment") or {}

        client = llm_client or get_llm_client()
        user_prompt = build_user_prompt(
            features,
            model_result,
            [
                e if isinstance(e, dict) else e.model_dump(mode="json")
                for e in evidence
            ],
        )

        from pydantic import ValidationError

        llm_attempts = 0  # bound even when on_exhausted raises

        def _call() -> Any:
            return client.generate_structured(
                SYSTEM_PROMPT_V1, user_prompt, HealthGuidanceResponse
            )

        def _on_exhausted(exc: Exception) -> None:
            raise exc  # surfaced below as a terminal LLM error

        try:
            raw, llm_attempts = with_retries(
                _call,
                transient=(LLMError,),
                what="generate_guidance",
            )
        except LLMError as exc:
            # Exhausted transient retries carry their attempt count on the
            # exception; other paths never entered the retry loop.
            attempts = getattr(exc, "attempts", MAX_ATTEMPTS)
            return {
                "llm_error": str(exc),
                "errors": [f"llm_error:{exc}"],
                "workflow_status": "failed",
                "metadata": {"attempts:generate_guidance": attempts},
            }
        except ValidationError as exc:
            # Schema violations are terminal: the provider answered, the
            # answer is unusable — retrying would fail identically.
            return {
                "llm_error": f"schema validation failed: {exc.errors()[:2]}",
                "errors": ["llm_schema_validation_failed"],
                "workflow_status": "failed",
            }

        # State stores JSON-compatible dicts (checkpoint-serializable);
        # validation already happened inside generate_structured.
        return {
            "guidance": raw.model_dump(mode="json"),
            "metadata": {
                "guidance_source": "llm",
                "attempts:generate_guidance": llm_attempts,
            },
        }

    return _node


def make_safety_check_node(db):
    """safety_check — REUSES Phase 4 safety + citation verification.

    Operates on the dict form of guidance/evidence from state, re-validating
    through the Phase 4 Pydantic schemas (state is data, not objects).
    """

    def _node(state: GuidanceGraphState) -> dict[str, Any]:
        from backend.app.rag.schemas import (
            Evidence,
            HealthGuidanceResponse,
            verify_citations,
        )
        from backend.app.rag.safety import detect_emergency
        import re

        raw_guidance = state.get("guidance")
        if raw_guidance is None:
            return {}  # nothing to check; router handles the failure path

        guidance = HealthGuidanceResponse.model_validate(raw_guidance)
        evidence = [
            Evidence.model_validate(e) for e in (state.get("evidence") or [])
        ]

        flags: list[str] = []
        # 1. Citation verification (drops fabricated citations; flags if any
        #    were dropped — a signal worth a human look).
        verified = verify_citations(guidance, evidence)
        dropped = len(guidance.citations) - len(verified)
        if dropped > 0:
            flags.append(f"unverified_citations_dropped:{dropped}")

        # 2. Conservative content scan of generated text for emergency
        #    language the LLM may have produced (belt-and-braces: the prompt
        #    forbids it, but generation is probabilistic).
        blob = " ".join([guidance.summary, *guidance.when_to_seek_care])
        emergency_verdict = detect_emergency(blob)
        if emergency_verdict.escalate_emergency:
            # Not a block: appropriate escalation language in care advice is
            # expected; flag for review rather than delete it.
            flags.append("emergency_language_in_output")

        # 3. Guard against the LLM asserting diagnostic certainty.
        import re

        if re.search(
            r"\byou (have|definitely have|do not have)\b", blob, re.IGNORECASE
        ):
            flags.append("diagnostic_certainty_language")

        return {
            "safety_flags": flags,
            "metadata": {"citations_verified": len(verified)},
        }

    return _node


def build_retrieval_query_values(state: GuidanceGraphState) -> str:
    """Build the retrieval query from raw state values via the Phase 4
    query builder (kept free of emergency vocabulary there)."""
    from types import SimpleNamespace

    from backend.app.rag.service import build_retrieval_query

    features = state.get("assessment") or {}
    row = SimpleNamespace(
        **{k: features.get(k, 0) for k in (
            "age", "cp", "trestbps", "chol", "fbs", "restecg",
            "oldpeak", "thal", "ca", "exang",
        )}
    )
    return build_retrieval_query(row)
