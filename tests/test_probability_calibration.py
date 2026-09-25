"""Tests for probability calibration in the v2 pipeline."""

from __future__ import annotations

import json

import pytest
from _modern_guard import require_modern_env
from sklearn.calibration import CalibratedClassifierCV

require_modern_env()

from sklearn.metrics import brier_score_loss  # noqa: E402

from ml.config import CALIBRATION_METHOD, METRICS_PATH  # noqa: E402
from ml.inference.predictor import load_predictor  # noqa: E402
from ml.training.train import load_test_split  # noqa: E402


@pytest.fixture(scope="module")
def split():
    return load_test_split()


@pytest.fixture(scope="module")
def predictor():
    return load_predictor()


def test_artifact_is_calibrated(predictor):
    assert isinstance(predictor.pipeline, CalibratedClassifierCV)
    assert predictor.pipeline.method == CALIBRATION_METHOD


def test_calibration_metadata_recorded(predictor):
    calib = predictor.metadata["calibration"]
    assert CALIBRATION_METHOD in calib
    assert "cv" in calib or "CalibratedClassifierCV" in calib


def test_brier_score_is_reasonable(predictor, split):
    """Brier on the locked test set must beat naive baselines."""
    X_test, y_test = split
    p = _predict_all(predictor, X_test)
    brier = brier_score_loss(y_test, p)
    prevalence = float(y_test.mean())
    # A no-skill model predicting the base rate achieves brier ~= p(1-p).
    naive = prevalence * (1 - prevalence)
    assert brier < naive


def test_metrics_file_reports_uncal_vs_cal():
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    assert "uncalibrated" in metrics["test"]
    assert "calibrated" in metrics["test"]
    assert "brier_score" in metrics["test"]["calibrated"]


def _predict_all(predictor, X):

    probs = []
    for _, row in X.iterrows():
        probs.append(predictor.predict(row.to_dict())["disease_probability"])
    return probs
