"""Target-semantics tests: the modern pipeline must read 1 = disease.

These tests encode the single most important Phase 1 correction (Phase 0
documented the legacy inversion in docs/legacy-ml-baseline.md §6).
"""

from __future__ import annotations

import numpy as np
import pytest
from _modern_guard import require_modern_env

require_modern_env()

from ml.config import (  # noqa: E402
    MODERN_TARGET_SEMANTICS,
    SOURCE_TARGET_SEMANTICS,
    flip_target,
)  # noqa: E402
from ml.inference.predictor import load_predictor  # noqa: E402
from ml.training.train import load_data  # noqa: E402


def test_flip_target_converts_source_to_modern():
    source = np.array([1, 0, 1, 0])
    modern = flip_target(source)
    assert modern.tolist() == [0, 1, 0, 1]


def test_flip_target_is_involutive():
    y = np.array([0, 1, 1, 0, 1])
    assert flip_target(flip_target(y)).tolist() == y.tolist()


def test_config_semantics_strings_are_explicit():
    assert "disease" in MODERN_TARGET_SEMANTICS
    assert "1 = disease" in MODERN_TARGET_SEMANTICS
    assert SOURCE_TARGET_SEMANTICS  # documented non-empty


def test_loaded_dataset_uses_modern_semantics():
    X, y, _ = load_data()
    assert set(np.unique(y)) == {0, 1}
    # Source data has 165 healthy (target=1 source) / 138 disease (target=0).
    # After flip: disease=1 count must be 138.
    assert int((y == 1).sum()) == 138
    assert int((y == 0).sum()) == 165


@pytest.mark.parametrize(
    ("features", "expect_disease"),
    [
        # Clinically healthy profile
        (dict(age=45, sex=1, cp=0, trestbps=120, chol=180, fbs=0, restecg=0,
              thalach=170, exang=0, oldpeak=0.5, slope=1, ca=0, thal=2), False),
        # Clinically severe profile
        (dict(age=65, sex=1, cp=3, trestbps=160, chol=300, fbs=1, restecg=2,
              thalach=100, exang=1, oldpeak=2.5, slope=2, ca=3, thal=3), True),
    ],
)
def test_predictor_disease_probability_directionality(features, expect_disease):
    """Disease probability must be HIGH for the clinically sick profile and
    LOW for the healthy one — the exact inversion the legacy app had."""
    predictor = load_predictor()
    result = predictor.predict(features)
    assert result["predicted_disease"] is expect_disease
    if expect_disease:
        assert result["disease_probability"] > 0.5
    else:
        assert result["disease_probability"] < 0.5


def test_predictor_probability_label_is_not_risk_language():
    predictor = load_predictor()
    features = dict(age=50, sex=0, cp=1, trestbps=130, chol=240, fbs=0, restecg=1,
                    thalach=150, exang=0, oldpeak=1.0, slope=2, ca=0, thal=2)
    result = predictor.predict(features)
    assert result["probability_label"] == "model_estimated_probability"
    assert "not a clinically validated risk score" in result["disclaimer"]
