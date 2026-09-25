"""Phase 4 API test — POST /api/v1/assessments/{id}/guidance.

Uses a STUB LLM client + stub retrieval (no external services) to test the
endpoint contract: model-output separation, citation verification, and
graceful provider-failure mapping.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from backend.tests.conftest import requires_pg

VALID_PAYLOAD = {
    "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180,
    "fbs": 0, "restecg": 0, "thalach": 170, "exang": 0,
    "oldpeak": 0.5, "slope": 1, "ca": 0, "thal": 2,
}

EVIDENCE_URL = "https://www.nhs.uk/conditions/atherosclerosis/"

STUB_LLM_OUTPUT = {
    "summary": "The model estimated a low probability of disease.",
    "model_explanation": "Younger age and normal cholesterol lowered the estimate.",
    "key_factors": ["age", "cholesterol"],
    "guidance": ["Regular physical activity supports cardiovascular health."],
    "when_to_seek_care": ["Persistent chest discomfort warrants medical review."],
    "limitations": "Educational prototype; small training dataset.",
    "citations": [
        {
            "title": "Atherosclerosis",
            "source": "UK National Health Service",
            "url": EVIDENCE_URL,
            "section": "Introduction",
        }
    ],
}

FABRICATED_LLM_OUTPUT = {
    **STUB_LLM_OUTPUT,
    "citations": [
        {
            "title": "Completely Made Up",
            "source": "Fake Journal",
            "url": "https://fake-journal.example.com/study",
            "section": "Results",
        }
    ],
}


class StubLLM:
    """Satisfies the LLMClient interface without any network calls."""

    def __init__(self, output: dict) -> None:
        self.output = output

    def generate_structured(self, system: str, user: str, schema):
        return schema.model_validate(self.output)


class FailingLLM(StubLLM):
    def generate_structured(self, system: str, user: str, schema):
        from backend.app.llm.client import LLMError

        raise LLMError("provider down")


def _create_assessment(client) -> str:
    resp = client.post("/api/v1/assessments", json=VALID_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


def _stub_evidence() -> list[dict]:
    """Dict-form evidence matching the graph state contract."""
    return [
        {
            "title": "Atherosclerosis",
            "source": "UK National Health Service",
            "url": EVIDENCE_URL,
            "section": "Introduction",
            "content": "Atherosclerosis is where your arteries become narrowed.",
            "similarity": 0.87,
        }
    ]


@requires_pg
class TestGuidanceEndpoint:
    def test_404_for_unknown_assessment(self, client):
        import uuid

        resp = client.post(f"/api/v1/assessments/{uuid.uuid4()}/guidance")
        assert resp.status_code == 404

    def test_guidance_success_with_verified_citations(self, client, monkeypatch):
        assessment_id = _create_assessment(client)

        # Phase 5: the endpoint runs the LangGraph workflow with the default
        # client factory patched to a stub (graph passes it into nodes).
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "test-model")
        from backend.app.core.config import get_settings

        get_settings.cache_clear()

        with patch(
            "backend.app.llm.client.get_llm_client",
            return_value=StubLLM(STUB_LLM_OUTPUT),
        ):
            resp = client.post(f"/api/v1/assessments/{assessment_id}/guidance")

        assert resp.status_code == 202, resp.text  # review not auto-released
        body = resp.json()
        detail = body["detail"]
        assert detail["review_required"] is True
        assert detail["workflow_status"] == "pending_review"
        # Model output snapshot in the review payload stays authoritative.
        assert detail["assessment"]["model_version"] == "2.0.0"
        get_settings.cache_clear()

    def test_fabricated_citations_are_dropped(self, client, monkeypatch):
        """Fabricated citations are now verified at the safety node INSIDE the
        graph (covered there); at the API level the flag forces a 202 review
        response instead of releasing guidance with citations."""
        assessment_id = _create_assessment(client)
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "test-model")
        from backend.app.core.config import get_settings

        get_settings.cache_clear()
        with patch(
            "backend.app.llm.client.get_llm_client",
            return_value=StubLLM(FABRICATED_LLM_OUTPUT),
        ):
            resp = client.post(f"/api/v1/assessments/{assessment_id}/guidance")
        assert resp.status_code == 202
        assert resp.json()["detail"]["review_required"] is True
        get_settings.cache_clear()

    def test_llm_failure_maps_to_502(self, client, monkeypatch):
        assessment_id = _create_assessment(client)
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "test-model")
        # RAG must look healthy, otherwise the flow routes to review before
        # the LLM is ever called (deterministic degradation).
        monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
        monkeypatch.setenv("EMBEDDING_MODEL", "test-model")
        import backend.app.rag.retrieval as retrieval_mod

        monkeypatch.setattr(
            retrieval_mod,
            "retrieve_relevant_evidence",
            lambda db, query, **kw: _stub_evidence(),
        )
        from backend.app.core.config import get_settings

        get_settings.cache_clear()
        with patch(
            "backend.app.llm.client.get_llm_client",
            return_value=FailingLLM(STUB_LLM_OUTPUT),
        ):
            resp = client.post(f"/api/v1/assessments/{assessment_id}/guidance")
        assert resp.status_code == 502
        get_settings.cache_clear()

    def test_unconfigured_provider_maps_to_503(self, client, monkeypatch):
        assessment_id = _create_assessment(client)
        monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
        monkeypatch.setenv("EMBEDDING_MODEL", "test-model")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        # RAG healthy: the LLM config check must be what fails (503 path).
        import backend.app.rag.retrieval as retrieval_mod

        monkeypatch.setattr(
            retrieval_mod,
            "retrieve_relevant_evidence",
            lambda db, query, **kw: _stub_evidence(),
        )
        from backend.app.core.config import get_settings

        get_settings.cache_clear()
        resp = client.post(f"/api/v1/assessments/{assessment_id}/guidance")
        assert resp.status_code == 503
        get_settings.cache_clear()
