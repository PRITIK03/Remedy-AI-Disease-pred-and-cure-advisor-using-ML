"""Trajectory evaluation — runs evals/agent_cases.json against the guidance
graph with stubbed externals. Deterministic, fast, no network.

The fixture (evals/agent_cases.json) stays human-editable; this runner maps
each case's `rag_mode`/`llm_mode`/`assessment_profile` onto graph stubs and
asserts the `expected` trajectory fields.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("AGENTS_CHECKPOINTER", "memory")

EVALS_PATH = PROJECT_ROOT / "evals" / "agent_cases.json"

HIGH_RISK = {
    "model_version": "2.0.0",
    "selected_model": "logistic_regression",
    "predicted_disease": True,
    "disease_probability": 0.9123,
}
LOW_RISK = {
    "model_version": "2.0.0",
    "selected_model": "logistic_regression",
    "predicted_disease": False,
    "disease_probability": 0.3483,
}

FABRICATED_OUTPUT = {
    "summary": "s", "model_explanation": "m", "key_factors": [],
    "guidance": [], "when_to_seek_care": [], "limitations": "l",
    "citations": [
        {"title": "Fake", "source": "Nowhere",
         "url": "https://fake.example.com/x", "section": "N"}
    ],
}

MALFORMED_OUTPUT = {
    "summary": 12345, "model_explanation": "m", "key_factors": [],
    "guidance": [], "when_to_seek_care": [], "limitations": "l",
    "citations": [],
}


def load_cases() -> list[dict]:
    data = json.loads(EVALS_PATH.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_agent_case(case, monkeypatch):
    from backend.app.agents.graph import build_guidance_graph
    from backend.app.agents import nodes as nodes_mod
    from backend.app.rag.schemas import HealthGuidanceResponse
    from backend.tests.agents.conftest import (
        FakeLLM,
        FakeMalformedLLM,
        LLM_OUTPUT,
    )

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    # --- stub assessment ------------------------------------------------ #
    profile = case.get("assessment_profile", "healthy")
    if profile == "missing":
        monkeypatch.setattr(
            nodes_mod, "make_load_assessment_node",
            lambda db, aid: lambda state: {
                "errors": [f"assessment_not_found:{aid}"],
                "workflow_status": "failed",
                "model_result": None,
            },
        )
    else:
        model_result = (
            HIGH_RISK if case.get("model_probability", 0) >= 0.75 else LOW_RISK
        )
        monkeypatch.setattr(
            nodes_mod, "make_load_assessment_node",
            lambda db, aid: lambda state: {
                "assessment": {"age": 45.0, "cp": 0, "trestbps": 120,
                               "chol": 180, "fbs": 0, "restecg": 0,
                               "oldpeak": 0, "thal": 0, "ca": 0, "exang": 0},
                "model_result": model_result,
            },
        )

    # --- stub RAG -------------------------------------------------------- #
    rag_mode = case.get("rag_mode", "ok")
    if rag_mode == "ok":
        monkeypatch.setattr(
            nodes_mod, "make_retrieve_evidence_node",
            lambda db: lambda state: {
                "evidence": [{
                    "title": "Atherosclerosis",
                    "source": "UK National Health Service",
                    "url": "https://www.nhs.uk/conditions/atherosclerosis/",
                    "section": "Causes",
                    "content": "Plaque narrows the arteries over time.",
                    "similarity": 0.86,
                }],
                "evidence_available": True,
            },
        )
    elif rag_mode == "unavailable":
        monkeypatch.setattr(
            nodes_mod, "make_retrieve_evidence_node",
            lambda db: lambda state: {
                "evidence": [], "evidence_available": False,
                "rag_error": "embedding provider unreachable",
                "metadata": {"rag_degraded": "transient_failure"},
            },
        )
    elif rag_mode == "empty":
        monkeypatch.setattr(
            nodes_mod, "make_retrieve_evidence_node",
            lambda db: lambda state: {
                "evidence": [], "evidence_available": False,
                "rag_error": "knowledge base is empty",
                "metadata": {"rag_degraded": "empty_knowledge_base"},
            },
        )

    # --- stub LLM --------------------------------------------------------- #
    llm_mode = case.get("llm_mode", "ok")
    monkeypatch.setattr(nodes_mod.time, "sleep", lambda s: None)
    llm: object
    if llm_mode == "outage":
        llm = FakeLLM(fail=True)
    elif llm_mode == "malformed":
        llm = FakeMalformedLLM(MALFORMED_OUTPUT)
    elif llm_mode == "fabricated_citations":
        llm = FakeLLM(FABRICATED_OUTPUT)
    else:
        llm = FakeLLM(dict(LLM_OUTPUT))

    graph = build_guidance_graph(object(), "eval", llm)
    config = {"configurable": {"thread_id": f"guidance:eval-{case['id']}"}}
    final = graph.invoke({"assessment_id": "eval"}, config)

    expected = case["expected"]

    # --- trajectory assertions -------------------------------------------- #
    if "review_required" in expected:
        assert final.get("review_required") is expected["review_required"], case["id"]
    if "workflow_status" in expected:
        assert final.get("workflow_status") == expected["workflow_status"], case["id"]
    if expected.get("guidance_valid"):
        assert HealthGuidanceResponse.model_validate(final["guidance"]), case["id"]
    if expected.get("constrained_fallback"):
        assert "sufficient evidence" in final["guidance"]["summary"], case["id"]
    if expected.get("llm_error"):
        assert final.get("llm_error"), case["id"]
    if expected.get("errors_contain"):
        assert any(
            expected["errors_contain"] in e for e in final.get("errors", [])
        ), case["id"]
    if expected.get("safety_flags_contain"):
        assert any(
            expected["safety_flags_contain"] in f
            for f in final.get("safety_flags", [])
        ), case["id"]
    if expected.get("review_reason_contains"):
        assert expected["review_reason_contains"] in (
            final.get("review_reason") or ""
        ), case["id"]
    if expected.get("max_attempts"):
        assert (
            (final.get("metadata") or {}).get("attempts:generate_guidance")
            == expected["max_attempts"]
        ), case["id"]
