"""Phase 7 tests — report upload validation, extraction flow, ownership, confirm."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.tests.conftest import (  # noqa: E402
    CSRF_COOKIE,
    bootstrap_csrf,
    register_and_login,
    requires_pg,
)

VALID_FEATURES = {
    "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180, "fbs": 0,
    "restecg": 0, "thalach": 170, "exang": 0, "oldpeak": 0.5, "slope": 1,
    "ca": 0, "thal": 2,
}

USER_A = "report-a@example.com"
USER_B = "report-b@example.com"
PASSWORD = "Report-Pass-123"


def _png_bytes(color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, format="PNG")
    return buf.getvalue()


class StubReportLLM:
    """Records which generation path was used so tests can assert text vs vision."""

    def __init__(self) -> None:
        self.text_calls = 0
        self.vision_calls = 0

    def _payload(self) -> dict:
        fields: dict = {}
        for k, v in VALID_FEATURES.items():
            fields[k] = {"value": v, "confidence": 0.9, "evidence": f"{k}={v}"}
        fields["notes"] = "stubbed extraction"
        return fields

    def generate_structured(self, system: str, user: str, schema):
        self.text_calls += 1
        return schema.model_validate(self._payload())

    def generate_structured_multimodal(
        self, system: str, user_prompt: str, images_base64: list, schema
    ):
        self.vision_calls += 1
        return schema.model_validate(self._payload())


def _text_pdf(text: str) -> bytes:
    """Build a minimal single-page PDF containing real extractable text."""
    import pypdf
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 250 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


PDF_TEXT = (
    "Patient age 45 years, male. Resting blood pressure 120 mmHg, "
    "total cholesterol 180 mg/dL, resting ECG normal, maximum heart rate "
    "170 bpm, no exercise induced angina, ST depression 0.5 mm."
)



def _upload(client, filename: str, content: bytes, content_type: str):
    token = client.cookies.get(CSRF_COOKIE)
    return client.post(
        "/api/v1/reports",
        files={"file": (filename, content, content_type)},
        headers={"X-CSRF-Token": token} if token else {},
    )


def _confirm(client, report_id: str, payload: dict):
    return client.post(
        f"/api/v1/reports/{report_id}/confirm",
        json=payload,
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )


@requires_pg
class TestReportValidation:
    def test_rejects_non_document_bytes(self, client):
        register_and_login(client, USER_A, PASSWORD)
        resp = _upload(client, "evil.txt", b"not a document", "text/plain")
        assert resp.status_code == 422

    def test_rejects_spoofed_mime_with_bad_magic(self, client):
        register_and_login(client, USER_A, PASSWORD)
        resp = _upload(client, "fake.pdf", b"hello world", "application/pdf")
        assert resp.status_code == 422

    def test_upload_requires_auth(self, client):
        bootstrap_csrf(client)
        resp = _upload(client, "scan.png", _png_bytes(), "image/png")
        assert resp.status_code == 401


@requires_pg
class TestReportExtractionFlow:
    def test_png_upload_extracts_and_lists(self, client, monkeypatch):
        import backend.app.reports.service as report_service

        stub = StubReportLLM()
        monkeypatch.setattr(report_service, "get_llm_client", lambda: stub)
        register_and_login(client, USER_A, PASSWORD)
        resp = _upload(client, "scan.png", _png_bytes(), "image/png")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "completed"
        assert body["latest_extraction"] is not None
        assert body["latest_extraction"]["extracted_features"]["age"] == 45
        # An image must go through the VISION path, never the text path.
        assert (stub.vision_calls, stub.text_calls) == (1, 0)

        listed = client.get("/api/v1/reports")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

    def test_text_pdf_uses_deterministic_text_path(self, client, monkeypatch):
        import backend.app.reports.service as report_service

        stub = StubReportLLM()
        monkeypatch.setattr(report_service, "get_llm_client", lambda: stub)
        register_and_login(client, USER_A, PASSWORD)
        resp = _upload(client, "labs.pdf", _text_pdf(PDF_TEXT), "application/pdf")
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "completed"
        # A text PDF is parsed locally and sent as TEXT (no images rendered).
        assert (stub.text_calls, stub.vision_calls) == (1, 0)


@requires_pg
class TestReportOwnership:
    def test_cross_user_report_is_404(self, client, monkeypatch):
        import backend.app.reports.service as report_service

        monkeypatch.setattr(
            report_service, "get_llm_client", lambda: StubReportLLM()
        )
        register_and_login(client, USER_A, PASSWORD)
        created = _upload(client, "scan.png", _png_bytes(), "image/png").json()
        report_id = created["id"]
        client.cookies.clear()

        register_and_login(client, USER_B, PASSWORD)
        assert client.get("/api/v1/reports").json()["total"] == 0
        assert client.get(f"/api/v1/reports/{report_id}").status_code == 404


@requires_pg
class TestConfirmFlow:
    def test_confirm_creates_report_sourced_assessment(self, client, monkeypatch):
        import backend.app.reports.service as report_service

        monkeypatch.setattr(
            report_service, "get_llm_client", lambda: StubReportLLM()
        )
        register_and_login(client, USER_A, PASSWORD)
        created = _upload(client, "scan.png", _png_bytes(), "image/png").json()
        report_id = created["id"]

        resp = _confirm(client, report_id, VALID_FEATURES)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["source"] == "report"
        assert body["report_id"] == report_id

    def test_confirm_rejects_invalid_values(self, client, monkeypatch):
        import backend.app.reports.service as report_service

        monkeypatch.setattr(
            report_service, "get_llm_client", lambda: StubReportLLM()
        )
        register_and_login(client, USER_A, PASSWORD)
        created = _upload(client, "scan.png", _png_bytes(), "image/png").json()
        bad = dict(VALID_FEATURES)
        bad["age"] = 5
        resp = _confirm(client, created["id"], bad)
        assert resp.status_code == 422


class TestParserUnit:
    def test_inspect_rejects_unknown_magic(self):
        from backend.app.reports.parser import (
            DocumentParseError,
            inspect_and_validate_file,
        )

        with pytest.raises(DocumentParseError):
            inspect_and_validate_file(b"hello world", "x.bin")

    def test_parser_accepts_png(self):
        from backend.app.reports.parser import (
            inspect_and_validate_file,
            parse_document,
        )

        raw = _png_bytes()
        mime = inspect_and_validate_file(raw, "scan.png")
        assert mime == "image/png"
        parsed = parse_document(raw, mime)
        assert parsed.kind == "multimodal"
        assert parsed.images

    def test_text_pdf_parsed_deterministically(self):
        from backend.app.reports.parser import (
            inspect_and_validate_file,
            parse_document,
        )

        raw = _text_pdf(PDF_TEXT)
        mime = inspect_and_validate_file(raw, "labs.pdf")
        assert mime == "application/pdf"
        parsed = parse_document(raw, mime)
        assert parsed.kind == "text"
        assert parsed.images is None
        assert "cholesterol" in (parsed.text_content or "").lower()

    def test_image_upload_is_never_treated_as_text(self):
        from backend.app.reports.parser import inspect_and_validate_file, parse_document

        raw = _png_bytes()
        parsed = parse_document(raw, inspect_and_validate_file(raw, "scan.png"))
        assert parsed.kind == "multimodal"
        assert parsed.text_content is None
