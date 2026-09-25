"""End-to-end tests exercising the Flask app's actual behavior.

Phase 1 update: /predict serves the modern v2 model by default (correct
disease semantics), while MODEL_VERSION=v1 preserves the exact legacy
behavior — including its documented inverted labels — for regression
comparison. The Phase 0 assertions are preserved verbatim in the v1 class
below; the v2 class pins the corrected public behavior.
"""

from __future__ import annotations

import importlib
import threading
import time
import urllib.request

import pytest

FORM_DATA = {
    "age": "45", "sex": "1", "cp": "0", "trestbps": "120", "chol": "180",
    "fbs": "0", "restecg": "0", "thalach": "170", "exang": "0",
    "oldpeak": "0.5", "slope": "1", "ca": "0", "thal": "2",
}


@pytest.fixture()
def client():
    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


def _require_v2_predictor() -> None:
    """Skip v2-mode tests when the modern artifact can't load in this env
    (e.g. legacy system interpreter with older sklearn — see _modern_guard)."""
    import app as app_module

    if app_module.modern_predictor is None:
        pytest.skip(
            "v2 predictor unavailable under this interpreter; run tests in .venv",
            allow_module_level=False,
        )


@pytest.fixture()
def v1_client(monkeypatch):
    """App reloaded with MODEL_VERSION=v1 (legacy semantics)."""
    monkeypatch.setenv("MODEL_VERSION", "v1")
    import app as app_module

    reloaded = importlib.reload(app_module)
    assert reloaded.MODEL_VERSION == "v1"
    reloaded.app.config["TESTING"] = True
    with reloaded.app.test_client() as client:
        yield client
    # Restore default-mode module state for subsequent tests.
    monkeypatch.delenv("MODEL_VERSION")
    importlib.reload(app_module)


class TestApplicationStartup:
    def test_models_loaded_at_import(self, client):
        import app as app_module

        # Legacy pickles always load (v1 regression path must stay available).
        assert app_module.voting_classifier_model is not None
        assert app_module.scaler is not None

    def test_modern_pipeline_loaded_by_default(self, client):
        _require_v2_predictor()
        import app as app_module

        assert app_module.modern_predictor is not None
        assert app_module.MODEL_VERSION == "v2"

    def test_home_page_returns_200_and_form(self, client):

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Heart Disease Risk Assessment" in resp.data
        assert b'name="trestbps"' in resp.data

    def test_real_server_boots_and_serves(self):
        """Prove the actual WSGI server starts and serves (not just test client)."""
        import app as app_module

        config = {"host": "127.0.0.1", "port": 5599, "debug": False}

        def run():
            app_module.app.run(**config, use_reloader=False)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        deadline = time.time() + 10
        last_err = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:5599/", timeout=2) as r:
                    assert r.status == 200
                    return
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                time.sleep(0.2)
        pytest.fail(f"Real server did not come up: {last_err}")


class TestValidPredictionV2ModernDefault:
    """Public behavior with MODEL_VERSION=v2 (default): correct semantics.

    Skipped entirely under interpreters that cannot load the v2 artifact
    (the legacy environment runs only the v1 regression tests).
    """

    @pytest.fixture(autouse=True)
    def _skip_if_no_v2(self):
        _require_v2_predictor()

    def test_predict_returns_200_and_result(self, client):
        resp = client.post("/predict", data=FORM_DATA)
        assert resp.status_code == 200
        assert b"risk of heart disease" in resp.data
        assert b"Home Remedies" in resp.data

    def test_prediction_is_deterministic(self, client):
        r1 = client.post("/predict", data=FORM_DATA).data
        r2 = client.post("/predict", data=FORM_DATA).data
        assert r1 == r2

    def test_healthy_profile_labeled_low_risk(self, client):
        """CORRECTED semantics: clinically healthy profile → LOW risk.

        (The legacy v1 app showed 'High risk: 66.41%' for this same input —
        see TestLegacyModeV1 below and docs/legacy-ml-baseline.md §6.)
        """
        resp = client.post("/predict", data=FORM_DATA)
        assert b"Low risk of heart disease" in resp.data
        # The v2 model's calibrated probability for this profile is 34.83%.
        assert b"34.83%" in resp.data

    def test_sick_profile_labeled_high_risk(self, client):
        sick = {**FORM_DATA, "age": "65", "cp": "3", "trestbps": "160",
                "chol": "300", "fbs": "1", "restecg": "2", "thalach": "100",
                "exang": "1", "oldpeak": "2.5", "slope": "2", "ca": "3", "thal": "3"}
        resp = client.post("/predict", data=sick)
        assert b"High risk of heart disease" in resp.data


class TestValidPredictionLegacyModeV1:
    """MODEL_VERSION=v1: every Phase 0 assertion, preserved verbatim."""

    def test_legacy_route_reproduces_phase0_baseline(self, v1_client):
        resp = v1_client.post("/predict", data=FORM_DATA)
        assert resp.status_code == 200
        assert b"risk of heart disease" in resp.data
        assert b"Home Remedies" in resp.data
        assert b"150 minutes of moderate-intensity" in resp.data
        # Phase 0 pinned value: legacy (inverted) labeling.
        assert b"High risk of heart disease: 66.41%" in resp.data

    def test_legacy_urgent_advice_fires_above_threshold(self, v1_client):
        resp = v1_client.post("/predict", data=FORM_DATA)
        assert b"Consult a healthcare professional immediately" in resp.data

    def test_legacy_recommendations_for_risky_features(self, v1_client):
        data = {**FORM_DATA, "age": "60", "chol": "300", "trestbps": "140",
                "thalach": "110", "oldpeak": "2.0"}
        resp = v1_client.post("/predict", data=data)
        assert b"Schedule regular check-ups" in resp.data
        assert b"heart-healthy diet" in resp.data
        assert b"Monitor your blood pressure" in resp.data
        assert b"aerobic exercise" in resp.data
        assert b"cardiac rehabilitation" in resp.data


class TestMalformedInput:
    def test_non_numeric_chol_returns_message_not_500(self, client):
        resp = client.post("/predict", data={**FORM_DATA, "chol": "abc"})
        assert resp.status_code == 200
        assert b"Invalid input" in resp.data
        assert b"not a valid" in resp.data

    def test_out_of_range_returns_message(self, client):
        resp = client.post("/predict", data={**FORM_DATA, "trestbps": "999"})
        assert resp.status_code == 200
        assert b"must be between" in resp.data

    def test_missing_field_returns_message(self, client):
        data = dict(FORM_DATA)
        del data["thalach"]
        resp = client.post("/predict", data=data)
        assert resp.status_code == 200
        assert b"required" in resp.data


class TestRecommendationGenerationV2:
    def test_generic_advice_still_rendered(self, client):
        """The legacy rule engine stays for v2 (per Phase 1 instructions)."""
        resp = client.post("/predict", data=FORM_DATA)
        assert b"Home Remedies" in resp.data
        assert b"150 minutes of moderate-intensity" in resp.data
