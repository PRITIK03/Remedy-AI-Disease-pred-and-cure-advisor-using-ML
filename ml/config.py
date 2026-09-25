"""Centralized configuration for the modern (v2) ML pipeline.

All decisions that affect training or inference live here so that a single
file documents the pipeline contract:

- feature typing and order,
- target semantics (disease = 1 after the documented flip),
- split/CV/seeds,
- artifact locations and versions.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_PATH = PROJECT_ROOT / "ml" / "data" / "heart.csv"
DATASET_META_PATH = PROJECT_ROOT / "ml" / "data" / "dataset_meta.json"

MODELS_DIR = PROJECT_ROOT / "models" / "v2"
PIPELINE_PATH = MODELS_DIR / "cardio_risk_pipeline.joblib"
METADATA_PATH = MODELS_DIR / "metadata.json"
METRICS_PATH = MODELS_DIR / "metrics.json"

ARTIFACTS_DIR = PROJECT_ROOT / "ml" / "artifacts"
EVALUATION_PATH = ARTIFACTS_DIR / "evaluation.json"

# MLflow 3.x: local sqlite backend (the plain file store is deprecated).
MLFLOW_TRACKING_URI = f"sqlite:///{(PROJECT_ROOT / 'mlflow.db').as_posix()}"
MLFLOW_EXPERIMENT_NAME = "cardio-risk"

LEGACY_SCALER_PATH = PROJECT_ROOT / "scaler.pkl"

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

# Column order in the source dataset.
RAW_FEATURE_ORDER: tuple[str, ...] = (
    "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
    "thalach", "exang", "oldpeak", "slope", "ca", "thal",
)

# Feature typing (verified against the dataset in scripts/verify_dataset.py
# and documented in docs/model-card.md).
NUMERIC_FEATURES: tuple[str, ...] = ("age", "trestbps", "chol", "thalach", "oldpeak")
BINARY_FEATURES: tuple[str, ...] = ("sex", "fbs", "exang")
CATEGORICAL_FEATURES: tuple[str, ...] = ("cp", "restecg", "slope", "ca", "thal")

assert set(NUMERIC_FEATURES) | set(BINARY_FEATURES) | set(CATEGORICAL_FEATURES) == set(RAW_FEATURE_ORDER)

TARGET_COLUMN = "target"

# Soft plausibility bounds for raw inputs (validation only; same intent as
# the legacy app's ranges but aligned with the dataset encodings).
FEATURE_RANGES: dict[str, tuple[float, float]] = {
    "age": (25, 100), "sex": (0, 1), "cp": (0, 3), "trestbps": (80, 220),
    "chol": (100, 600), "fbs": (0, 1), "restecg": (0, 2), "thalach": (60, 220),
    "exang": (0, 1), "oldpeak": (0.0, 10.0), "slope": (0, 2), "ca": (0, 4),
    "thal": (0, 3),
}

# --------------------------------------------------------------------------- #
# Target semantics
# --------------------------------------------------------------------------- #
# Source dataset (Kaggle ronitf/heart-disease-uci mirror): target=1 means
# LESS chance of heart attack (no disease). Verified in Phase 0/1; see
# docs/legacy-ml-baseline.md §6 and ml/data/README.md.
#
# Modern convention (documented, tested):
#   1 = disease, 0 = no disease.
# The flip happens ONLY in training data loading (flip_target below), never
# implicitly anywhere else.

SOURCE_TARGET_SEMANTICS = "1 = no disease (healthy), 0 = disease (from source dataset)"
MODERN_TARGET_SEMANTICS = "1 = disease, 0 = no disease"


def flip_target(y_source: array-like) -> array-like:  # noqa: F821
    """Convert source target encoding to the modern disease=1 convention."""
    import numpy as np

    arr = np.asarray(y_source)
    return (1 - arr).astype(int)


POSITIVE_CLASS = 1  # disease, in the modern convention

# --------------------------------------------------------------------------- #
# Training configuration
# --------------------------------------------------------------------------- #

RANDOM_SEED = 42
TEST_SIZE = 0.2
CV_FOLDS = 5

MODEL_NAME = "cardiovascular-disease-risk"
MODEL_VERSION = "2.0.0"
CALIBRATION_METHOD = "sigmoid"  # Platt scaling; see docs/model-card.md

# --------------------------------------------------------------------------- #
# Inference output contract
# --------------------------------------------------------------------------- #

PROBABILITY_LABEL = "model_estimated_probability"
