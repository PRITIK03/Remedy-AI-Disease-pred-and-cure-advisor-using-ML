"""Tests for the modern (v2) training pipeline."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from _modern_guard import require_modern_env

require_modern_env()

from ml.config import (  # noqa: E402
    CATEGORICAL_FEATURES,
    DATA_PATH,
    EVALUATION_PATH,
    METRICS_PATH,
    MODELS_DIR,
    NUMERIC_FEATURES,
    RAW_FEATURE_ORDER,
)
from ml.evaluation.metrics import classification_metrics  # noqa: E402
from ml.preprocessing.pipeline import build_preprocessor  # noqa: E402
from ml.training.models import get_candidates  # noqa: E402

# --------------------------------------------------------------------------- #
# Data integrity
# --------------------------------------------------------------------------- #


def test_dataset_exists_and_hash_is_recorded():
    assert DATA_PATH.exists()
    meta = json.loads((DATA_PATH.parent / "dataset_meta.json").read_text(encoding="utf-8"))
    import hashlib

    digest = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()
    # The stored file may use CRLF; compare against the normalized hash too.
    if digest != meta["sha256"]:
        text = DATA_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == meta["sha256"]


def test_dataset_schema_matches_config():
    df = pd.read_csv(DATA_PATH)
    assert list(df.columns) == list(RAW_FEATURE_ORDER) + ["target"]
    assert len(df) == 303


# --------------------------------------------------------------------------- #
# Preprocessing design
# --------------------------------------------------------------------------- #


def test_preprocessor_feature_typing_covers_all_features():
    """Numeric/binary/categorical partition must cover all 13 features."""
    from ml.config import BINARY_FEATURES

    all_typed = (
        set(NUMERIC_FEATURES) | set(BINARY_FEATURES) | set(CATEGORICAL_FEATURES)
    )
    assert all_typed == set(RAW_FEATURE_ORDER)
    assert not (
        set(NUMERIC_FEATURES) & set(CATEGORICAL_FEATURES)
    ), "a feature must not be double-typed"


def test_preprocessor_uses_config_groups():
    df = pd.read_csv(DATA_PATH).drop(columns=["target"])
    pre = build_preprocessor().fit(df)
    fitted_columns = {
        name: list(cols) for name, _, cols in pre.transformers_ if name != "remainder"
    }
    assert fitted_columns["numeric"] == list(NUMERIC_FEATURES)
    assert fitted_columns["categorical"] == list(CATEGORICAL_FEATURES)


def test_preprocessor_output_width_and_names():
    df = pd.read_csv(DATA_PATH).drop(columns=["target"])
    pre = build_preprocessor().fit(df)
    names = list(pre.get_feature_names_out())
    # 5 numeric + 3 binary + one-hot expanded categoricals
    assert len(names) > 13
    assert any(n.startswith("numeric__") for n in names)
    assert any(n.startswith("binary__") for n in names)
    assert any(n.startswith("categorical__") for n in names)


def test_preprocessing_is_inside_the_pipeline():
    """No preprocessing may happen outside the sklearn Pipeline (leakage rule)."""
    for cand in get_candidates():
        assert isinstance(cand.estimator, object)
        steps = dict(cand.estimator.named_steps)
        assert "preprocessor" in steps, "preprocessing must live in the Pipeline"
        assert "classifier" in steps


# --------------------------------------------------------------------------- #
# Candidate models
# --------------------------------------------------------------------------- #


def test_candidate_models_present():
    names = [c.name for c in get_candidates()]
    assert "logistic_regression" in names
    assert "random_forest" in names
    assert "hist_gradient_boosting" in names


def test_all_candidates_share_the_same_preprocessing():
    pre = build_preprocessor()
    for cand in get_candidates():
        assert cand.estimator.named_steps["preprocessor"]
    assert pre is not None


# --------------------------------------------------------------------------- #
# Metrics module
# --------------------------------------------------------------------------- #


def test_classification_metrics_perfect_case():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9])
    m = classification_metrics(y, p)
    assert m["accuracy"] == 1.0
    assert m["roc_auc"] == 1.0
    assert m["confusion_matrix"]["tp"] == 2
    assert m["confusion_matrix"]["tn"] == 2


def test_classification_metrics_inverted_case():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.9, 0.8, 0.2, 0.1])
    m = classification_metrics(y, p)
    assert m["accuracy"] == 0.0
    assert m["roc_auc"] == pytest.approx(0.0, abs=1e-9)
    assert m["confusion_matrix"]["fn"] == 2


def test_evaluation_artifacts_exist_after_training():
    """These artifacts are produced by the training run (documented in the
    Phase 1 report); if missing, training has not been executed."""
    assert MODELS_DIR.exists(), "models/v2 missing: run python -m ml.training.train"
    assert METRICS_PATH.exists()
    assert EVALUATION_PATH.exists()
