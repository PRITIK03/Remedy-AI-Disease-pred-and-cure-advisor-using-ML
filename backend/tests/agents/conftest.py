"""Fixtures for agent workflow tests — everything stubbed, no network."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("AGENTS_CHECKPOINTER", "memory")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

EVIDENCE_URL = "https://www.nhs.uk/conditions/atherosclerosis/"

MODEL_RESULT = {
    "model_version": "2.0.0",
    "selected_model": "logistic_regression",
    "predicted_disease": False,
    "disease_probability": 0.3483,
}

HIGH_RISK_MODEL_RESULT = {
    **MODEL_RESULT,
    "predicted_disease": True,
    "disease_probability": 0.9123,
}

LLM_OUTPUT = {
    "summary": "The model estimated a low probability of disease.",
    "model_explanation": "Age and cholesterol influenced the estimate most.",
    "key_factors": ["age", "cholesterol"],
    "guidance": ["Regular aerobic activity supports heart health."],
    "when_to_seek_care": ["Persistent discomfort warrants medical review."],
    "limitations": "Educational prototype; small training dataset.",
    "citations": [
        {
            "title": "Atherosclerosis",
            "source": "UK National Health Service",
            "url": EVIDENCE_URL,
            "section": "Causes",
        }
    ],
}


class FakeSession:
    """Minimal DB-session stand-in: the stubbed retrieval/LLM never touch it."""


class FakeAssessmentRow:
    """Mimics the Assessment ORM row attributes used by the graph."""

    def __init__(self, model_result: dict) -> None:
        self.__dict__.update(
            {
                "age": 45.0, "sex": 1.0, "cp": 0.0, "trestbps": 120.0,
                "chol": 180.0, "fbs": 0.0, "restecg": 0.0, "thalach": 170.0,
                "exang": 0.0, "oldpeak": 0.5, "slope": 1.0, "ca": 0.0,
                "thal": 2.0,
            }
        )
        self.model_version = model_result["model_version"]
        self.selected_model = model_result["selected_model"]
        self.predicted_disease = model_result["predicted_disease"]
        self.disease_probability = model_result["disease_probability"]


class FakeLLM:
    """Satisfies LLMClient.generate_structured without any network."""

    def __init__(self, output: dict | None = None, fail: bool = False) -> None:
        self.output = output or LLM_OUTPUT
        self.fail = fail
        self.calls = 0

    def generate_structured(self, system: str, user: str, schema):
        self.calls += 1
        if self.fail:
            from backend.app.llm.client import LLMError

            raise LLMError("simulated provider outage")
        return schema.model_validate(self.output)

    def generate_structured_multimodal(
        self, system: str, user_prompt: str, images_base64: list, schema
    ):
        self.calls += 1
        if self.fail:
            from backend.app.llm.client import LLMError

            raise LLMError("simulated provider outage")
        return schema.model_validate(self.output)


class FakeMalformedLLM(FakeLLM):
    def generate_structured(self, system: str, user: str, schema):
        self.calls += 1
        return schema.model_validate({**self.output, "summary": 12345})

    def generate_structured_multimodal(
        self, system: str, user_prompt: str, images_base64: list, schema
    ):
        self.calls += 1
        return schema.model_validate({**self.output, "summary": 12345})


@pytest.fixture()
def patched_assessment(monkeypatch):
    """Patch assessment loading: existing low-risk row by default."""

    def _install(model_result: dict | None = MODEL_RESULT):
        from backend.app.agents import nodes as nodes_mod

        if model_result is None:
            monkeypatch.setattr(
                nodes_mod,
                "make_load_assessment_node",
                lambda db, assessment_id: lambda state: {
                    "errors": [f"assessment_not_found:{assessment_id}"],
                    "workflow_status": "failed",
                    "model_result": None,
                },
            )
        else:
            row = FakeAssessmentRow(model_result)

            def _loader(db, assessment_id):
                def _node(state):
                    return {
                        "assessment": {
                            col: float(row.__dict__[col])
                            for col in (
                                "age", "sex", "cp", "trestbps", "chol", "fbs",
                                "restecg", "thalach", "exang", "oldpeak",
                                "slope", "ca", "thal",
                            )
                        },
                        "model_result": {
                            "model_version": row.model_version,
                            "selected_model": row.selected_model,
                            "predicted_disease": bool(row.predicted_disease),
                            "disease_probability": round(
                                float(row.disease_probability), 5
                            ),
                        },
                    }

                return _node

            monkeypatch.setattr(nodes_mod, "make_load_assessment_node", _loader)

    return _install


@pytest.fixture()
def patched_rag(monkeypatch):
    """Patch RAG retrieval with fake evidence (or failures).

    The stub returns the same JSON-compatible dict form the real node
    produces (state carries dicts, not Pydantic objects).
    """
    evidence = [
        {
            "title": "Atherosclerosis",
            "source": "UK National Health Service",
            "url": EVIDENCE_URL,
            "section": "Causes",
            "content": "Plaque narrows the arteries over time.",
            "similarity": 0.86,
        }
    ]

    def _install(mode: str = "ok") -> None:
        from backend.app.agents import nodes as nodes_mod

        if mode == "ok":
            monkeypatch.setattr(
                nodes_mod,
                "make_retrieve_evidence_node",
                lambda db: lambda state: {
                    "evidence": evidence,
                    "evidence_available": True,
                },
            )
        elif mode == "unavailable":
            monkeypatch.setattr(
                nodes_mod,
                "make_retrieve_evidence_node",
                lambda db: lambda state: {
                    "evidence": [],
                    "evidence_available": False,
                    "rag_error": "embedding provider unreachable",
                    "metadata": {"rag_degraded": "transient_failure"},
                },
            )
        elif mode == "empty":
            monkeypatch.setattr(
                nodes_mod,
                "make_retrieve_evidence_node",
                lambda db: lambda state: {
                    "evidence": [],
                    "evidence_available": False,
                    "rag_error": "knowledge base is empty",
                    "metadata": {"rag_degraded": "empty_knowledge_base"},
                },
            )

    return _install


@pytest.fixture()
def invoke_graph():
    """Build + invoke the graph with stubbed nodes and a memory checkpointer."""

    def _run(
        llm: FakeLLM | None = None,
        assessment_id: str = "00000000-0000-0000-0000-000000000001",
    ):
        from backend.app.agents.graph import build_guidance_graph

        os.environ["AGENTS_CHECKPOINTER"] = "memory"
        graph = build_guidance_graph(
            FakeSession(), assessment_id, llm or FakeLLM()
        )
        config = {"configurable": {"thread_id": f"guidance:{assessment_id}"}}
        return graph, config

    return _run
