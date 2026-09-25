"""Candidate model definitions for the v2 pipeline comparison.

Centralized so every experiment logs the same candidate set. Hyperparameters
are intentionally modest: the dataset is 303 rows and heavy tuning would
overfit the evaluation itself. random_state is fixed for reproducibility.

HistGradientBoostingClassifier is chosen over XGBoost for the boosted-tree
candidate: it is first-party sklearn (no extra dependency), handles small
datasets fine, and keeps the artifact loadable with sklearn alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ml.config import RANDOM_SEED, RAW_FEATURE_ORDER
from ml.preprocessing.pipeline import build_preprocessor


@dataclass(frozen=True)
class Candidate:
    name: str
    estimator: object
    description: str


def _pipeline(estimator: object) -> Pipeline:
    """Wrap estimator with the shared preprocessing (leakage-free CV)."""
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("classifier", estimator),
        ]
    )


def get_candidates() -> list[Candidate]:
    return [
        Candidate(
            name="logistic_regression",
            estimator=_pipeline(
                LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
            ),
            description="Linear baseline; interpretable coefficients.",
        ),
        Candidate(
            name="random_forest",
            estimator=_pipeline(
                RandomForestClassifier(
                    n_estimators=300,
                    min_samples_leaf=3,
                    random_state=RANDOM_SEED,
                    n_jobs=-1,
                )
            ),
            description="Bagged trees; robust non-linear baseline.",
        ),
        Candidate(
            name="hist_gradient_boosting",
            estimator=_pipeline(
                HistGradientBoostingClassifier(
                    max_depth=3,
                    max_iter=200,
                    learning_rate=0.08,
                    random_state=RANDOM_SEED,
                )
            ),
            description="Boosted trees (sklearn-native, XGBoost-class).",
        ),
    ]


FEATURE_ORDER = RAW_FEATURE_ORDER
