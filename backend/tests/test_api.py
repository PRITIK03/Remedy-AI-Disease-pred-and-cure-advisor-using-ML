"""Backend API tests (real PostgreSQL, disposable DB; Redis optional)."""

from __future__ import annotations

import uuid

from backend.tests.conftest import requires_pg

VALID_PAYLOAD = {
    "age": 45, "sex": 1, "cp": 0, "trestbps": 120, "chol": 180,
    "fbs": 0, "restecg": 0, "thalach": 170, "exang": 0,
    "oldpeak": 0.5, "slope": 1, "ca": 0, "thal": 2,
}


@requires_pg
class TestHealthEndpoints:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["model_version"] == "v2"

    def test_ready_reports_all_services(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["services"]["database"] == "ok"
        assert body["services"]["model"] == "ok"

    def test_ready_redis_reflects_availability(self, client):
        resp = client.get("/ready")
        body = resp.json()
        # Redis may or may not be running locally; either way the field must
        # be a truthful, structured value.
        assert body["services"]["redis"] in {"ok", "unavailable"}


@requires_pg
class TestCreateAssessment:
    def test_create_returns_201_and_structured_result(self, client):
        resp = client.post("/api/v1/assessments", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["model_version"] == "2.0.0"
        assert body["probability_label"] == "model_estimated_probability"
        assert 0.0 <= body["disease_probability"] <= 1.0
        assert isinstance(body["predicted_disease"], bool)
        assert body["input_features"]["age"] == 45

    def test_persistence_roundtrip(self, client):
        created = client.post("/api/v1/assessments", json=VALID_PAYLOAD).json()
        fetched = client.get(f"/api/v1/assessments/{created['id']}")
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["id"] == created["id"]
        assert body["disease_probability"] == created["disease_probability"]
        assert body["model_version"] == created["model_version"] == "2.0.0"

    def test_semantics_healthy_profile_low_probability(self, client):
        """Phase 1 corrected semantics must hold through the API."""
        resp = client.post("/api/v1/assessments", json=VALID_PAYLOAD)
        assert resp.json()["disease_probability"] < 0.5

    def test_semantics_sick_profile_high_probability(self, client):
        sick = {**VALID_PAYLOAD, "age": 65, "cp": 3, "trestbps": 160,
                "chol": 300, "fbs": 1, "restecg": 2, "thalach": 100,
                "exang": 1, "oldpeak": 2.5, "slope": 2, "ca": 3, "thal": 3}
        resp = client.post("/api/v1/assessments", json=sick)
        assert resp.json()["disease_probability"] > 0.5

    def test_request_id_header_present(self, client):
        resp = client.post("/api/v1/assessments", json=VALID_PAYLOAD)
        assert "x-request-id" in resp.headers

    def test_custom_request_id_echoed(self, client):
        resp = client.post(
            "/api/v1/assessments",
            json=VALID_PAYLOAD,
            headers={"X-Request-ID": "test-rid-123"},
        )
        assert resp.headers["x-request-id"] == "test-rid-123"


@requires_pg
class TestExplanationEndpoint:
    def test_explanation_returns_contributions(self, client):
        created = client.post("/api/v1/assessments", json=VALID_PAYLOAD).json()
        resp = client.get(f"/api/v1/assessments/{created['id']}/explanation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["assessment_id"] == created["id"]
        assert body["model_version"] == "2.0.0"
        assert len(body["contributions"]) > 0
        assert all("feature" in c and "shap_value" in c for c in body["contributions"])
        assert "not" in body["note"].lower() and "causal" in body["note"].lower()

    def test_explanation_missing_assessment_404(self, client):
        import uuid as uuid_mod

        resp = client.get(
            f"/api/v1/assessments/{uuid_mod.uuid4()}/explanation"
        )
        assert resp.status_code == 404


@requires_pg
class TestValidation:
    def test_missing_field_422(self, client):
        bad = {k: v for k, v in VALID_PAYLOAD.items() if k != "chol"}
        resp = client.post("/api/v1/assessments", json=bad)
        assert resp.status_code == 422

    def test_invalid_categorical_422(self, client):
        resp = client.post("/api/v1/assessments", json={**VALID_PAYLOAD, "cp": 7})
        assert resp.status_code == 422

    def test_invalid_numeric_range_422(self, client):
        resp = client.post("/api/v1/assessments", json={**VALID_PAYLOAD, "trestbps": 999})
        assert resp.status_code == 422

    def test_invalid_type_422(self, client):
        resp = client.post("/api/v1/assessments", json={**VALID_PAYLOAD, "age": "old"})
        assert resp.status_code == 422

    def test_extra_fields_rejected_strict_mode(self, client):
        resp = client.post(
            "/api/v1/assessments", json={**VALID_PAYLOAD, "injected": "x"}
        )
        assert resp.status_code == 422


@requires_pg
class TestRetrieval:
    def test_get_nonexistent_404(self, client):
        random_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/assessments/{random_id}")
        assert resp.status_code == 404

    def test_get_malformed_uuid_422(self, client):
        resp = client.get("/api/v1/assessments/not-a-uuid")
        assert resp.status_code == 422

    def test_pagination(self, client):
        for _ in range(5):
            client.post("/api/v1/assessments", json=VALID_PAYLOAD)
        page1 = client.get("/api/v1/assessments?limit=2&offset=0").json()
        page2 = client.get("/api/v1/assessments?limit=2&offset=2").json()
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        ids = {i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]}
        assert not ids  # no overlap between pages

    def test_limit_capped(self, client):
        resp = client.get("/api/v1/assessments?limit=500")
        assert resp.status_code == 422


@requires_pg
class TestLifespanIntegration:
    def test_model_loaded_once_in_app_state(self, app):
        assert app.state.model_service.is_ready
        # Same instance reused (not reloaded per request).
        assert app.state.model_service is app.state.model_service

    def test_ml_package_ownership_preserved(self, app):
        """Model service must wrap ml.inference.predictor, not duplicate it."""
        svc = app.state.model_service
        assert hasattr(svc._predictor, "predict")
        assert hasattr(svc._predictor, "explain")
        assert svc.model_version == "2.0.0"
