"""Phase 4 tests — safety layer, source manifest, LLM/embedding clients.

Targeted only: no network, no DB. The LLM/embedding tests exercise the
validation logic with fake HTTP errors, never real providers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.rag.safety import (  # noqa: E402
    EMERGENCY_NOTICE,
    detect_emergency,
    screen_request,
)
from backend.app.rag.sources import ManifestError, load_manifest  # noqa: E402

# --------------------------------------------------------------------- #
# Safety screening
# --------------------------------------------------------------------- #


class TestSafetyScreening:
    def test_diagnosis_request_blocked(self):
        v = screen_request("Can you confirm that I have heart disease?")
        assert v.blocked and "cannot" in v.reason.lower()

    def test_prescription_request_blocked(self):
        v = screen_request("What dosage of aspirin should I take?")
        assert v.blocked

    def test_clinician_replacement_blocked(self):
        v = screen_request("I don't need a doctor, right?")
        assert v.blocked

    def test_fabrication_blocked(self):
        v = screen_request("Fabricate medical evidence supporting my claim.")
        assert v.blocked

    def test_benign_request_passes(self):
        v = screen_request("What does a high model probability mean generally?")
        assert not v.blocked

    def test_emergency_detection(self):
        v = detect_emergency("crushing chest pain and cold sweat right now")
        assert v.escalate_emergency
        assert "IMMEDIATELY" in EMERGENCY_NOTICE

    def test_non_emergency_ignored(self):
        v = detect_emergency("mild fatigue sometimes in the afternoon")
        assert not v.escalate_emergency


# --------------------------------------------------------------------- #
# Source manifest (fail-closed trust model)
# --------------------------------------------------------------------- #


class TestSourceManifest:
    def test_repo_manifest_loads(self):
        records = load_manifest()
        assert len(records) >= 5
        domains = {r.url.split("/")[2] for r in records}
        allowed = (
            "nhlbi.nih.gov", "medlineplus.gov", "who.int",
            "nhs.uk", "my.clevelandclinic.org",
        )
        for d in domains:
            assert any(d == a or d.endswith("." + a) for a in allowed), d

    def test_disallowed_publisher_rejected(self, tmp_path):
        manifest = tmp_path / "sources.yaml"
        manifest.write_text(
            "sources:\n"
            "  - title: Blog\n"
            "    url: https://random-blog.io/heart\n"
            "    publisher: Random\n"
            "    document_type: blog\n",
            encoding="utf-8",
        )
        with pytest.raises(ManifestError):
            load_manifest(manifest)

    def test_duplicate_url_rejected(self, tmp_path):
        url = "https://www.nhs.uk/conditions/atherosclerosis/"
        manifest = tmp_path / "sources.yaml"
        manifest.write_text(
            "sources:\n"
            f"  - {{title: A, url: {url}, publisher: NHS, document_type: x}}\n"
            f"  - {{title: B, url: {url}, publisher: NHS, document_type: x}}\n",
            encoding="utf-8",
        )
        with pytest.raises(ManifestError):
            load_manifest(manifest)

    def test_missing_fields_rejected(self, tmp_path):
        manifest = tmp_path / "sources.yaml"
        manifest.write_text(
            "sources:\n  - title: Only a title\n", encoding="utf-8"
        )
        with pytest.raises(ManifestError):
            load_manifest(manifest)


# --------------------------------------------------------------------- #
# LLM client — structured-output validation with a stubbed transport
# --------------------------------------------------------------------- #


class TestLLMClientValidation:
    def _client(self):
        from backend.app.llm.client import OpenAICompatibleLLM

        return OpenAICompatibleLLM(
            api_base="https://fake.local/v1",
            api_key="test-key",
            model="fake-model",
            temperature=0.0,
        )

    def _validate_via(self, content: str):
        from backend.app.rag.schemas import HealthGuidanceResponse

        client = self._client()
        return client._validate(content, HealthGuidanceResponse)

    def test_plain_json_accepted(self):
        import json

        payload = {
            "summary": "s", "model_explanation": "m", "key_factors": [],
            "guidance": [], "when_to_seek_care": [],
            "limitations": "l", "citations": [],
        }
        out = self._validate_via(json.dumps(payload))
        assert out.summary == "s"

    def test_fenced_json_accepted(self):
        import json

        payload = {
            "summary": "s", "model_explanation": "m", "key_factors": [],
            "guidance": [], "when_to_seek_care": [],
            "limitations": "l", "citations": [],
        }
        text = "```json\n" + json.dumps(payload) + "\n```"
        out = self._validate_via(text)
        assert out.summary == "s"

    def test_prose_rejected(self):
        import pytest as _pytest

        from backend.app.llm.client import LLMError

        with _pytest.raises(LLMError):
            self._validate_via("Here is what I think, in prose form...")

    def test_schema_violation_rejected(self):
        from backend.app.llm.client import LLMError

        with pytest.raises(LLMError):
            self._validate_via('{"summary": 12345, "wrong": "shape"}')


# --------------------------------------------------------------------- #
# Embedding client — dimension/count validation (offline)
# --------------------------------------------------------------------- #


class TestEmbeddingValidation:
    def test_dimension_mismatch_detected(self, monkeypatch):
        from backend.app.rag.embeddings import OpenAICompatibleEmbeddings

        _ = OpenAICompatibleEmbeddings  # import sanity

        emb = OpenAICompatibleEmbeddings(
            api_base="https://fake.local/v1", api_key="k", model="m", timeout=5
        )
        monkeypatch.setattr(emb, "dimension", 4)
        with pytest.raises(Exception, match="dimension mismatch"):
            emb._validate([[0.1, 0.2, 0.3]], ["only-one-input"])

    def test_count_mismatch_detected(self, monkeypatch):
        from backend.app.rag.embeddings import OpenAICompatibleEmbeddings

        emb = OpenAICompatibleEmbeddings(
            api_base="https://fake.local/v1", api_key="k", model="m", timeout=5
        )
        monkeypatch.setattr(emb, "dimension", 1)
        with pytest.raises(Exception, match="vectors"):
            emb._validate([[0.1], [0.2]], ["a", "b", "c"])

    def test_unconfigured_provider_raises(self):
        from backend.app.rag.embeddings import (
            EmbeddingError,
            OpenAICompatibleEmbeddings,
        )

        emb = OpenAICompatibleEmbeddings(
            api_base="https://fake.local/v1", api_key="", model="", timeout=5
        )
        with pytest.raises(EmbeddingError):
            emb.embed(["hello"])
