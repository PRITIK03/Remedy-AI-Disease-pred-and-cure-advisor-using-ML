"""Phase 4 unit tests — chunking, schemas, safety, source manifest.

Targeted only (per phase plan): no DB, no network, no LLM required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.rag.chunking import chunk_sections  # noqa: E402
from backend.app.rag.schemas import (  # noqa: E402
    Citation,
    Evidence,
    HealthGuidanceResponse,
    verify_citations,
)

# --------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------- #


class TestChunking:
    def test_respects_word_budget(self):
        big = "word " * 600  # 600 words, one paragraph
        chunks = chunk_sections([("S", big.strip())])
        assert chunks, "must produce chunks"
        for c in chunks:
            assert len(c.content.split()) <= 240

    def test_never_spans_sections(self):
        sections = [
            ("Causes", "Plaque builds up in arteries. " * 20),
            ("Symptoms", "Chest pain is common. " * 20),
        ]
        chunks = chunk_sections(sections)
        assert chunks
        for c in chunks:
            assert c.section in {"Causes", "Symptoms"}

    def test_chunk_indices_sequential(self):
        sections = [("A", "alpha " * 60), ("B", "beta " * 60), ("C", "gamma " * 60)]
        chunks = chunk_sections(sections)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_empty_input(self):
        assert chunk_sections([]) == []

    def test_short_section_preserved(self):
        chunks = chunk_sections([("Intro", "Short but meaningful text here.")])
        assert len(chunks) == 1
        assert "meaningful" in chunks[0].content


# --------------------------------------------------------------------- #
# Guidance schema validation (LLM output contract)
# --------------------------------------------------------------------- #

VALID_GUIDANCE = {
    "summary": "The model estimated a moderate probability.",
    "model_explanation": "Age and cholesterol pushed the estimate up.",
    "key_factors": ["age", "cholesterol"],
    "guidance": ["Regular aerobic activity supports heart health."],
    "when_to_seek_care": ["Chest pain warrants prompt medical attention."],
    "limitations": "Small dataset; estimates carry uncertainty.",
    "citations": [
        {
            "title": "Atherosclerosis",
            "source": "UK National Health Service",
            "url": "https://www.nhs.uk/conditions/atherosclerosis/",
            "section": "Causes",
        }
    ],
}


class TestGuidanceSchema:
    def test_valid_payload_accepts(self):
        out = HealthGuidanceResponse.model_validate(VALID_GUIDANCE)
        assert out.summary.startswith("The model")

    def test_missing_field_rejected(self):
        bad = {k: v for k, v in VALID_GUIDANCE.items() if k != "summary"}
        with pytest.raises(ValidationError):
            HealthGuidanceResponse.model_validate(bad)

    def test_invalid_url_rejected(self):
        bad = dict(VALID_GUIDANCE)
        bad["citations"] = [
            {"title": "t", "source": "s", "url": "not-a-url", "section": "x"}
        ]
        with pytest.raises(ValidationError):
            HealthGuidanceResponse.model_validate(bad)

    def test_extra_fields_rejected(self):
        bad = {**VALID_GUIDANCE, "hallucination": True}
        with pytest.raises(ValidationError):
            HealthGuidanceResponse.model_validate(bad)


# --------------------------------------------------------------------- #
# Citation verification (no hallucinated citations survive)
# --------------------------------------------------------------------- #


def _evidence(url: str, section: str) -> Evidence:
    return Evidence(
        title="Atherosclerosis",
        source="UK National Health Service",
        url=url,
        section=section,
        content="Plaque narrows arteries.",
        similarity=0.83,
    )


class TestCitationVerification:
    def test_real_citation_kept(self):
        ev = [_evidence("https://www.nhs.uk/conditions/atherosclerosis/", "Causes")]
        g = HealthGuidanceResponse.model_validate(VALID_GUIDANCE)
        assert len(verify_citations(g, ev)) == 1

    def test_fabricated_citation_dropped(self):
        ev = [_evidence("https://www.nhs.uk/conditions/atherosclerosis/", "Causes")]
        g = HealthGuidanceResponse.model_validate(VALID_GUIDANCE)
        g.citations = [
            Citation(
                title="Made Up",
                source="Not Real",
                url="https://example.com/fake",
                section="Nothing",
            )
        ]
        assert verify_citations(g, ev) == []
