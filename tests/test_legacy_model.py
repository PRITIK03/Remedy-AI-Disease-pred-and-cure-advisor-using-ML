"""Deterministic baseline tests for the legacy model artifacts.

These tests pin the exact legacy inference behavior verified in Phase 0 so
that any future artifact/preprocessing change is caught. Recorded values come
from executing the legacy path under sklearn 1.3.2 / numpy 1.26.2 (see
docs/legacy-ml-baseline.md §7).

The class-semantics inversion documented in docs/legacy-ml-baseline.md §6 is
asserted here on purpose: Phase 0 preserves legacy behavior, and these probes
make the inversion visible and deliberate rather than silent.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from app import FEATURE_ORDER, predict_risk_probability

MODELS_DIR = Path(__file__).resolve().parent.parent

# Deterministic probe inputs (schema order), chosen in Phase 0.
LOW_RISK_PROFILE = [45, 1, 0, 120, 180, 0, 0, 170, 0, 0.5, 1, 0, 2]
HIGH_RISK_PROFILE = [65, 1, 3, 160, 300, 1, 2, 100, 1, 2.5, 2, 3, 3]
MEDIAN_PROFILE = [54, 0, 1, 132, 246, 0, 1, 150, 0, 1.0, 2, 0, 2]

TOL = 1e-4


def _load(name: str):
    with open(MODELS_DIR / name, "rb") as f:
        return pickle.load(f)


@pytest.fixture(scope="module")
def scaler():
    return _load("scaler.pkl")


@pytest.fixture(scope="module")
def voting_classifier():
    return _load("voting_classifier_model.pkl")


@pytest.fixture(scope="module")
def logistic_regression():
    return _load("logistic_regression_model.pkl")


@pytest.fixture(scope="module")
def random_forest():
    return _load("random_forest_model.pkl")


def _dict_from_list(row: list) -> dict[str, float]:
    return dict(zip(FEATURE_ORDER, row, strict=True))


# --------------------------------------------------------------------------- #
# Artifact integrity
# --------------------------------------------------------------------------- #


def test_all_artifacts_load_and_have_expected_types(
    scaler, voting_classifier, logistic_regression, random_forest
):
    from sklearn.ensemble import RandomForestClassifier, VotingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    assert isinstance(scaler, StandardScaler)
    assert isinstance(voting_classifier, VotingClassifier)
    assert isinstance(logistic_regression, LogisticRegression)
    assert isinstance(random_forest, RandomForestClassifier)


def test_all_artifacts_expect_13_features(scaler, voting_classifier, logistic_regression, random_forest):
    for est in (scaler, voting_classifier, logistic_regression, random_forest):
        assert est.n_features_in_ == 13


def test_scaler_feature_order_matches_app_schema(scaler):
    assert list(scaler.feature_names_in_) == list(FEATURE_ORDER)


def test_voting_classifier_has_two_members_soft_voting(voting_classifier):
    names = [name for name, _ in voting_classifier.estimators]
    assert names == ["random_forest", "logistic_regression"]
    assert voting_classifier.voting == "soft"


# --------------------------------------------------------------------------- #
# Preprocessing
# --------------------------------------------------------------------------- #


def test_scaler_transform_matches_legacy_statistics(scaler):
    """Z-score with the recorded dataset means/stds (legacy full-data fit)."""
    row = np.array([LOW_RISK_PROFILE], dtype=float)
    scaled = scaler.transform(row)
    expected_first = (45.0 - 54.36633663) / 9.06710164
    assert scaled[0][0] == pytest.approx(expected_first, abs=1e-6)
    assert scaled.shape == (1, 13)


def test_feature_order_definition_is_exact():
    assert FEATURE_ORDER == (
        "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
        "thalach", "exang", "oldpeak", "slope", "ca", "thal",
    )


# --------------------------------------------------------------------------- #
# Legacy prediction path (deterministic values recorded in Phase 0)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("row", "expected_proba"),
    [
        (LOW_RISK_PROFILE, 0.664051),
        (HIGH_RISK_PROFILE, 0.189465),
        (MEDIAN_PROFILE, 0.945440),
    ],
)
def test_legacy_voting_classifier_probabilities(row, expected_proba):
    values = _dict_from_list(row)
    assert predict_risk_probability(values) == pytest.approx(expected_proba, abs=TOL)


def test_low_risk_profile_maps_to_high_risk_label_in_legacy_semantics():
    """Documents the inversion: a healthy profile yields class-1 proba > 0.5.

    In the legacy app this prints "High risk of heart disease: 66.41%".
    See docs/legacy-ml-baseline.md §6. When the inversion is deliberately
    fixed in a later phase, this test must be consciously updated.
    """
    proba = predict_risk_probability(_dict_from_list(LOW_RISK_PROFILE))
    assert proba > 0.5


def test_high_risk_profile_maps_to_low_risk_label_in_legacy_semantics():
    """Documents the inversion: a severe profile yields class-1 proba < 0.5."""
    proba = predict_risk_probability(_dict_from_list(HIGH_RISK_PROFILE))
    assert proba < 0.5


def test_voting_classifier_equals_mean_of_members(scaler, voting_classifier, logistic_regression, random_forest):
    """Soft voting with default weights = mean of member probabilities."""
    row = np.array([MEDIAN_PROFILE], dtype=float)
    scaled = scaler.transform(row)
    p_lr = logistic_regression.predict_proba(scaled)[:, 1][0]
    p_rf = random_forest.predict_proba(scaled)[:, 1][0]
    p_vc = voting_classifier.predict_proba(scaled)[:, 1][0]
    assert p_vc == pytest.approx((p_lr + p_rf) / 2, abs=1e-9)


def test_model_classes_are_binary(scaler, voting_classifier):
    assert list(voting_classifier.classes_) == [0, 1]
