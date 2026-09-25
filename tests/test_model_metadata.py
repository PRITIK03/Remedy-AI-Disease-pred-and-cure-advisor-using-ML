"""Tests for model version metadata (models/v2/metadata.json)."""

from __future__ import annotations

import json

import pytest
from _modern_guard import require_modern_env

require_modern_env()

from ml.config import METADATA_PATH, MODEL_VERSION  # noqa: E402

REQUIRED_KEYS = [
    "model_name", "model_version", "target", "positive_class", "dataset",
    "dataset_hash", "features", "preprocessing", "calibration",
    "training_seed", "python_version", "sklearn_version", "trained_at",
]


@pytest.fixture(scope="module")
def metadata():
    assert METADATA_PATH.exists(), (
        "metadata.json missing — run: .venv/Scripts/python -m ml.training.train"
    )
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def test_required_metadata_keys_present(metadata):
    missing = [k for k in REQUIRED_KEYS if k not in metadata]
    assert not missing, f"missing metadata keys: {missing}"


def test_version_consistency(metadata):
    assert metadata["model_version"] == MODEL_VERSION
    assert metadata["model_name"] == "cardiovascular-disease-risk"


def test_target_semantics_explicit(metadata):
    assert metadata["positive_class"] == 1
    assert metadata["target"] == "disease"
    assert "1 = disease" in metadata["target_semantics"]
    # The source semantics and the transformation must be documented.
    assert "source_target_semantics" in metadata
    assert "1 - " in metadata["target_transformation"]


def test_dataset_hash_is_sha256(metadata):
    h = metadata["dataset_hash"]
    assert len(h) == 64
    int(h, 16)  # must be valid hex


def test_features_match_config(metadata):
    from ml.config import RAW_FEATURE_ORDER

    assert metadata["features"] == list(RAW_FEATURE_ORDER)


def test_mlflow_info_present(metadata):
    assert "mlflow" in metadata
    info = metadata["mlflow"]
    if info.get("enabled"):
        assert "run_id" in info and "experiment_id" in info


def test_metadata_versions_match_runtime(metadata):
    """Metadata must reflect the environment that actually trained the model."""
    import sklearn

    assert metadata["sklearn_version"] == sklearn.__version__
