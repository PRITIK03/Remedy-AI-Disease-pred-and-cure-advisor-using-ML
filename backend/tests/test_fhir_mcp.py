"""Phase 8 targeted tests — FHIR mapping/validation/ownership + MCP surface.

Deliberately narrow, as the phase spec requires:
  * FHIR mapping correctness (no invented data, provenance, subject refs)
  * FHIR lightweight schema validation
  * FHIR ownership enforcement (404 indistinguishability, 401 anonymous)
  * MCP tool registration, read-only annotations, read-only surface guard
  * MCP ownership enforcement (tool level, with mocked services)

No real LLM calls, no RAG ingestion, no ML retraining, no network.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.tests.conftest import (  # noqa: E402
    CSRF_COOKIE,
    bootstrap_csrf,
    register_and_login,
    requires_pg,
)


def _create_assessment(client) -> str:
    """Create an assessment for the logged-in user (CSRF header required)."""
    resp = client.post(
        "/api/v1/assessments",
        json=VALID_FEATURES,
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]

FIXTURE = json.loads(
    (PROJECT_ROOT / "backend" / "tests" / "fixtures" / "synthetic_fhir.json").read_text(
        encoding="utf-8"
    )
)
SYNTHETIC_USER_ID = FIXTURE["patient"]["id"]


@pytest.fixture()
def assessment_payload() -> dict:
    return dict(FIXTURE["assessment_source"])


@pytest.fixture()
def report_payload() -> dict:
    return dict(FIXTURE["report_source"])


# --------------------------------------------------------------------------- #
# FHIR: mapping
# --------------------------------------------------------------------------- #

class TestFhirMapping:
    def test_patient_exposes_no_email_or_role(self):
        from backend.app.fhir import mapper

        patient = mapper.map_patient(
            {
                "id": SYNTHETIC_USER_ID,
                "email": "should-never-appear@example.com",
                "display_name": "Synthetic Demo Subject",
                "role": "admin",
                "is_active": True,
            }
        )
        dumped = patient.model_dump(exclude_none=True)
        assert dumped["resourceType"] == "Patient"
        assert dumped["id"] == SYNTHETIC_USER_ID
        assert "should-never-appear@example.com" not in json.dumps(dumped)
        assert "role" not in dumped

    def test_all_thirteen_features_become_observations(self, assessment_payload):
        from backend.app.fhir import mapper

        observations = mapper.map_feature_observations(
            assessment_payload, SYNTHETIC_USER_ID
        )
        assert len(observations) == 13
        assert {o.code.coding[0].code for o in observations} >= {"2093-3", "8480-6"}

    def test_observation_subject_points_at_the_patient(self, assessment_payload):
        from backend.app.fhir import mapper

        observations = mapper.map_feature_observations(
            assessment_payload, SYNTHETIC_USER_ID
        )
        for obs in observations:
            assert obs.subject.reference == f"Patient/{SYNTHETIC_USER_ID}"

    def test_numeric_uses_quantity_and_categorical_uses_string(self, assessment_payload):
        from backend.app.fhir import mapper

        observations = mapper.map_feature_observations(
            assessment_payload, SYNTHETIC_USER_ID
        )
        by_feature = {o.id.rsplit("-", 1)[1]: o for o in observations}
        # index 3 = trestbps (numeric), index 1 = sex (categorical)
        assert by_feature["3"].valueQuantity is not None
        assert by_feature["3"].valueQuantity.code == "mm[Hg]"
        assert by_feature["1"].valueString is not None
        assert by_feature["1"].valueQuantity is None

    def test_missing_value_becomes_data_absent_not_a_guess(self, report_payload):
        from backend.app.fhir import mapper

        observations = mapper.map_report_observations(report_payload, SYNTHETIC_USER_ID)
        by_feature = {o.id.rsplit("-", 1)[1]: o for o in observations}
        # `ca` is null in the fixture: absent, never imputed to 0.
        assert by_feature["11"].valueQuantity is None
        assert by_feature["11"].valueString is None
        assert by_feature["11"].dataAbsentReason is not None
        assert by_feature["11"].dataAbsentReason.coding[0].code == "not-performed"

    def test_extracted_report_observations_are_preliminary(self, report_payload):
        from backend.app.fhir import mapper

        observations = mapper.map_report_observations(report_payload, SYNTHETIC_USER_ID)
        assert all(o.status == "preliminary" for o in observations)

    def test_probability_observation_is_labelled_not_a_diagnosis(
        self, assessment_payload
    ):
        from backend.app.fhir import mapper

        obs = mapper.map_probability_observation(assessment_payload, SYNTHETIC_USER_ID)
        assert obs.code.coding[0].code == "model-estimated-disease-probability"
        assert obs.valueQuantity.value == pytest.approx(0.3483)
        note = " ".join(n["text"] for n in obs.note)
        assert "not a diagnosis" in note.lower()

    def test_report_never_leaks_storage_key_or_hash(self, report_payload):
        from backend.app.fhir import mapper

        report = mapper.map_uploaded_report_diagnostic_report(
            report_payload, SYNTHETIC_USER_ID
        )
        blob = json.dumps(report.model_dump(exclude_none=True))
        assert report_payload["file_hash"] not in blob
        assert "storage_key" not in blob

    def test_resources_are_marked_as_generated(self, assessment_payload):
        from backend.app.fhir import mapper

        report = mapper.map_assessment_diagnostic_report(
            assessment_payload, SYNTHETIC_USER_ID
        )
        assert any(t["code"] == "generated" for t in report.meta["tag"])
        assert report.meta["source"].startswith("urn:remedy-ai:")

    def test_diagnostic_report_results_reference_real_observations(
        self, assessment_payload
    ):
        from backend.app.fhir import mapper

        observations = mapper.map_feature_observations(
            assessment_payload, SYNTHETIC_USER_ID
        ) + [mapper.map_probability_observation(assessment_payload, SYNTHETIC_USER_ID)]
        report = mapper.map_assessment_diagnostic_report(
            assessment_payload, SYNTHETIC_USER_ID
        )
        known = {f"Observation/{o.id}" for o in observations}
        assert {r.reference for r in report.result} == known


# --------------------------------------------------------------------------- #
# FHIR: lightweight schema validation
# --------------------------------------------------------------------------- #

class TestFhirValidation:
    def test_bundle_shape(self, assessment_payload):
        from backend.app.fhir import mapper
        from backend.app.fhir.schemas import FhirBundle

        patient = mapper.map_patient({"id": SYNTHETIC_USER_ID, "is_active": True})
        report = mapper.map_assessment_diagnostic_report(
            assessment_payload, SYNTHETIC_USER_ID
        )
        bundle = FhirBundle(
            timestamp=datetime.now(UTC).isoformat(),
            entry=[
                {"resource": patient.model_dump(exclude_none=True)},
                {"resource": report.model_dump(exclude_none=True)},
            ],
        )
        assert bundle.resourceType == "Bundle"
        assert bundle.type == "collection"
        for entry in bundle.entry:
            resource = entry["resource"]
            assert resource["resourceType"] in {
                "Patient", "Observation", "DiagnosticReport",
            }
            assert resource["id"]

    def test_observation_rejects_unknown_field(self):
        from pydantic import ValidationError

        from backend.app.fhir.schemas import FhirObservation

        with pytest.raises(ValidationError):
            FhirObservation.model_validate(
                {
                    "resourceType": "Observation",
                    "id": "x",
                    "status": "final",
                    "code": {"coding": []},
                    "subject": {"reference": "Patient/x"},
                    "effectiveDateTime": "2026-01-01T00:00:00Z",
                    "totallyMadeUpField": 1,
                }
            )

    def test_observation_requires_a_subject_reference(self):
        from pydantic import ValidationError

        from backend.app.fhir.schemas import FhirObservation

        with pytest.raises(ValidationError):
            FhirObservation.model_validate(
                {
                    "resourceType": "Observation",
                    "id": "x",
                    "status": "final",
                    "code": {"coding": []},
                    "effectiveDateTime": "2026-01-01T00:00:00Z",
                }
            )

    def test_patient_rejects_invalid_status_field(self):
        from pydantic import ValidationError

        from backend.app.fhir.schemas import FhirPatient

        with pytest.raises(ValidationError):
            FhirPatient.model_validate(
                {"resourceType": "Patient", "id": "x", "status": "bogus"}
            )


# --------------------------------------------------------------------------- #
# MCP: registration + read-only contract
# --------------------------------------------------------------------------- #

class TestMcpToolSurface:
    def test_exactly_the_five_agreed_tools_are_registered(self):
        import asyncio

        import mcp.remedy_server as server_mod

        tools = asyncio.run(server_mod.build_server().list_tools())
        assert {t.name for t in tools} == {
            "get_assessment",
            "get_assessment_history",
            "get_report_metadata",
            "get_model_information",
            "search_health_evidence",
        }

    def test_every_tool_is_annotated_read_only(self):
        import asyncio

        import mcp.remedy_server as server_mod

        tools = asyncio.run(server_mod.build_server().list_tools())
        for tool in tools:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.open_world_hint is False

    def test_no_write_capable_tools_exist(self):
        from mcp.tools import FORBIDDEN_TOOL_PATTERNS, TOOLS, assert_read_only_tool_surface

        assert_read_only_tool_surface()  # raises if a write-shaped name appears
        for name in TOOLS:
            for pattern in FORBIDDEN_TOOL_PATTERNS:
                assert pattern not in name.lower()

    def test_tool_surface_is_exactly_the_allowlist(self):
        from mcp.tools import TOOLS

        assert set(TOOLS) == {
            "get_assessment",
            "get_assessment_history",
            "get_report_metadata",
            "get_model_information",
            "search_health_evidence",
        }

    def test_no_tool_accepts_a_user_id_argument(self):
        import inspect

        from mcp.tools import TOOLS

        for name, fn in TOOLS.items():
            params = list(inspect.signature(fn).parameters)
            assert "user_id" not in params, name
            assert params[0] == "ctx", name

    def test_server_refuses_to_start_without_a_bound_user(self, monkeypatch):
        import mcp.remedy_server as server_mod

        monkeypatch.delenv("MCP_USER_ID", raising=False)
        with pytest.raises(server_mod.McpConfigurationError):
            server_mod._require_bound_user_id()

    def test_server_uses_a_bound_user_when_configured(self, monkeypatch):
        import mcp.remedy_server as server_mod

        monkeypatch.setenv("MCP_USER_ID", SYNTHETIC_USER_ID)
        assert server_mod._require_bound_user_id() == SYNTHETIC_USER_ID

    def test_instructions_state_the_read_only_scope(self):
        import mcp.remedy_server as server_mod

        text = server_mod.INSTRUCTIONS.lower()
        assert "read-only" in text
        assert "not a diagnosis" in text


# --------------------------------------------------------------------------- #
# MCP: ownership enforcement (services mocked — no DB, no network)
# --------------------------------------------------------------------------- #

class TestMcpOwnership:
    def _ctx(self, user_id: str):
        from mcp.tools import ToolContext

        return ToolContext(user_id=user_id, db=object(), model_service=None)

    def test_get_assessment_passes_the_bound_user_id(self, monkeypatch):
        from backend.app.services import assessment_service
        from mcp import tools

        seen: dict = {}

        def _fake_get(db, assessment_id, user_id):
            seen["assessment_id"] = assessment_id
            seen["user_id"] = user_id
            return None

        monkeypatch.setattr(assessment_service, "get_assessment_for_user", _fake_get)
        with pytest.raises(tools.ToolError) as exc:
            tools.get_assessment(self._ctx(SYNTHETIC_USER_ID), str(uuid4()))
        # The service is asked about the BOUND user only.
        assert str(seen["user_id"]) == SYNTHETIC_USER_ID
        assert exc.value.kind == "not_found"

    def test_foreign_and_missing_are_indistinguishable(self, monkeypatch):
        from backend.app.services import assessment_service
        from mcp import tools

        # The service itself returns None for a foreign row, exactly as for a
        # missing one, so the tool cannot tell them apart.
        monkeypatch.setattr(
            assessment_service, "get_assessment_for_user", lambda *a, **k: None
        )
        ctx = self._ctx(SYNTHETIC_USER_ID)
        outcomes = set()
        for assessment_id in (str(uuid4()), str(uuid4())):
            with pytest.raises(tools.ToolError) as exc:
                tools.get_assessment(ctx, assessment_id)
            outcomes.add((exc.value.kind, exc.value.message))
        assert len(outcomes) == 1

    def test_history_passes_the_bound_user_id(self, monkeypatch):
        from backend.app.services import assessment_service
        from mcp import tools

        seen: dict = {}

        def _fake_list(db, *, user_id, limit, offset):
            seen.update(user_id=user_id, limit=limit, offset=offset)
            return [], 0

        monkeypatch.setattr(assessment_service, "list_assessments", _fake_list)
        result = tools.get_assessment_history(self._ctx(SYNTHETIC_USER_ID), 5, 10)
        assert str(seen["user_id"]) == SYNTHETIC_USER_ID
        assert result == {"items": [], "total": 0, "limit": 5, "offset": 10}

    def test_history_clamps_limit_to_a_safe_maximum(self, monkeypatch):
        from backend.app.services import assessment_service
        from mcp import tools

        captured: dict = {}

        def _fake_list(db, *, user_id, limit, offset):
            captured["limit"] = limit
            return [], 0

        monkeypatch.setattr(assessment_service, "list_assessments", _fake_list)
        tools.get_assessment_history(self._ctx(SYNTHETIC_USER_ID), 9999, 0)
        assert captured["limit"] == 100

    def test_report_metadata_passes_the_bound_user_id(self, monkeypatch):
        from backend.app.reports import service as report_service
        from mcp import tools

        seen: dict = {}

        def _fake_get(db, user_id, report_id):
            seen["user_id"] = user_id
            return None

        monkeypatch.setattr(report_service, "get_user_report_by_id", _fake_get)
        with pytest.raises(tools.ToolError) as exc:
            tools.get_report_metadata(self._ctx(SYNTHETIC_USER_ID), str(uuid4()))
        assert str(seen["user_id"]) == SYNTHETIC_USER_ID
        assert exc.value.kind == "not_found"

    def test_tool_rejects_malformed_ids_without_touching_services(self, monkeypatch):
        from backend.app.services import assessment_service
        from mcp import tools

        def _boom(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("service must not be reached")

        monkeypatch.setattr(assessment_service, "get_assessment_for_user", _boom)
        with pytest.raises(tools.ToolError) as exc:
            tools.get_assessment(self._ctx(SYNTHETIC_USER_ID), "not-a-uuid")
        assert exc.value.kind == "invalid_input"

    def test_empty_user_id_is_refused(self):
        from mcp import tools

        ctx = tools.ToolContext(user_id="", db=object())
        with pytest.raises(tools.ToolError) as exc:
            ctx.require_user_id()
        assert exc.value.kind == "forbidden"


# --------------------------------------------------------------------------- #
# FHIR API: authentication + ownership (real disposable PostgreSQL)
# --------------------------------------------------------------------------- #

VALID_FEATURES = {
    "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180, "fbs": 0,
    "restecg": 0, "thalach": 170, "exang": 0, "oldpeak": 0.5, "slope": 1,
    "ca": 0, "thal": 2,
}
USER_A = "fhir-a@example.com"
USER_B = "fhir-b@example.com"
PASSWORD = "Fhir-Interop-123"
@requires_pg
class TestFhirApiAuth:
    def test_anonymous_requests_are_rejected(self, client):
        bootstrap_csrf(client)
        assert client.get(f"/api/v1/fhir/assessments/{uuid4()}").status_code == 401
        assert client.get(f"/api/v1/fhir/reports/{uuid4()}").status_code == 401

    def test_owner_receives_a_fhir_bundle(self, client):
        register_and_login(client, USER_A, PASSWORD)
        assessment_id = _create_assessment(client)

        resp = client.get(f"/api/v1/fhir/assessments/{assessment_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resourceType"] == "Bundle"
        types = {e["resource"]["resourceType"] for e in body["entry"]}
        assert {"Patient", "Observation", "DiagnosticReport"} <= types

    def test_cross_user_fhir_view_is_404(self, client):
        register_and_login(client, USER_A, PASSWORD)
        assessment_id = _create_assessment(client)
        client.cookies.clear()

        register_and_login(client, USER_B, PASSWORD)
        resp = client.get(f"/api/v1/fhir/assessments/{assessment_id}")
        assert resp.status_code == 404

    def test_missing_and_foreign_fhir_responses_are_identical(self, client):
        register_and_login(client, USER_A, PASSWORD)
        foreign = _create_assessment(client)
        client.cookies.clear()

        register_and_login(client, USER_B, PASSWORD)
        ghost = client.get(f"/api/v1/fhir/assessments/{uuid4()}")
        other = client.get(f"/api/v1/fhir/assessments/{foreign}")
        assert ghost.status_code == other.status_code == 404
        assert ghost.json() == other.json()

    def test_fhir_payload_hides_internal_columns(self, client):
        register_and_login(client, USER_A, PASSWORD)
        assessment_id = _create_assessment(client)
        blob = client.get(f"/api/v1/fhir/assessments/{assessment_id}").text
        # No session/credential material and no raw storage internals.
        assert "password" not in blob.lower()
        assert "session" not in blob.lower()
        assert "storage_key" not in blob


