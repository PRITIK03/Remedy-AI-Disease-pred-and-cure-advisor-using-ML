"""Tests for the modern inference module (ml/inference/predictor.py)."""

from __future__ import annotations

import joblib
import pytest
from _modern_guard import require_modern_env

require_modern_env()

from ml.config import PIPELINE_PATH, POSITIVE_CLASS, RAW_FEATURE_ORDER  # noqa: E402
from ml.inference.predictor import (  # noqa: E402
    FeatureValidationError,
    Predictor,
    load_predictor,
)

VALID = dict(age=45, sex=1, cp=0, trestbps=120, chol=180, fbs=0, restecg=0,
             thalach=170, exang=0, oldpeak=0.5, slope=1, ca=0, thal=2)


@pytest.fixture(scope="module")
def predictor() -> Predictor:
    return load_predictor()


class TestLoading:
    def test_loads_versioned_artifact(self, predictor):
        assert predictor.model_version == "2.0.0"
        assert predictor.metadata["model_name"] == "cardiovascular-disease-risk"
        assert predictor.metadata["positive_class"] == POSITIVE_CLASS == 1

    def test_artifact_is_single_serialized_object(self):
        """The artifact must be ONE object: preprocessing + classifier +
        calibration in one pickle, not separate scaler/model files."""
        obj = joblib.load(PIPELINE_PATH)
        # CalibratedClassifierCV (contains full preprocessing pipelines) or a
        # Pipeline — either way it must not require external scaler.pkl.
        has_internal_preprocessing = hasattr(obj, "calibrated_classifiers_") or (
            hasattr(obj, "named_steps") and "preprocessor" in obj.named_steps
        )
        assert has_internal_preprocessing
        assert obj.classes_[1] == 1  # disease is the positive class position


class TestSchemaValidation:
    def test_missing_field_fails_clearly(self, predictor):
        incomplete = {k: v for k, v in VALID.items() if k != "chol"}
        with pytest.raises(FeatureValidationError, match="chol"):
            predictor.predict(incomplete)

    def test_wrong_type_fails_clearly(self, predictor):
        with pytest.raises(FeatureValidationError, match="not numeric"):
            predictor.predict({**VALID, "age": "fifty"})

    def test_out_of_range_fails_clearly(self, predictor):
        with pytest.raises(FeatureValidationError, match="between"):
            predictor.predict({**VALID, "trestbps": "999"})

    def test_extra_fields_are_ignored(self, predictor):
        result = predictor.predict({**VALID, "hacky_field": "x"})
        assert "disease_probability" in result

    def test_feature_order_preserved(self, predictor):
        values = predictor.validate_features(dict(reversed(list(VALID.items()))))
        assert tuple(values.keys()) == RAW_FEATURE_ORDER


class TestPredictionContract:
    def test_output_structure(self, predictor):
        r = predictor.predict(VALID)
        assert set(r) >= {
            "model_version", "predicted_disease", "disease_probability",
            "probability_label", "disclaimer",
        }
        assert isinstance(r["predicted_disease"], bool)
        assert 0.0 <= r["disease_probability"] <= 1.0

    def test_deterministic(self, predictor):
        r1 = predictor.predict(VALID)
        r2 = predictor.predict(VALID)
        assert r1["disease_probability"] == r2["disease_probability"]
        assert r1["predicted_disease"] == r2["predicted_disease"]

    def test_invalid_input_raises_not_crashes(self, predictor):
        with pytest.raises(FeatureValidationError):
            predictor.predict({"age": 45})  # only 1 of 13 fields


class TestExplainabilityHook:
    def test_explain_returns_contributions(self, predictor):
        e = predictor.explain(VALID)
        assert "method" in e and "contributions" in e
        assert len(e["contributions"]) > 0
        assert all("feature" in c and "shap_value" in c for c in e["contributions"])
        assert "not causal" in e["note"]

    def test_explain_top_contribution_is_meaningful(self, predictor):
        """For a severely sick profile, a known disease marker should rank high."""
        sick = dict(age=65, sex=1, cp=3, trestbps=160, chol=300, fbs=1, restecg=2,
                    thalach=100, exang=1, oldpeak=2.5, slope=2, ca=3, thal=3)
        e = predictor.explain(sick)
        top_names = [c["feature"] for c in e["contributions"][:5]]
        assert any(
            key in n for n in top_names for key in ("oldpeak", "cp", "ca", "thal", "thalach")
        ), f"unexpected top features: {top_names}"
