"""Feature preprocessing for the modern (v2) pipeline.

Design (documented in docs/model-card.md):

- numeric features (age, trestbps, chol, thalach, oldpeak):
    median impute + StandardScaler (z-score) — continuous quantities.
- binary features (sex, fbs, exang):
    passthrough (already 0/1; scaling adds nothing and hurts interpretability).
- categorical features (cp, restecg, slope, ca, thal):
    one-hot encode. These are ordinal/categorical codes, NOT magnitudes;
    unlike the legacy pipeline, we do not feed raw codes into scaling/linear
    models as if distance between code 0 and 3 were meaningful.

The transformer is ALWAYS used inside an sklearn Pipeline so that
preprocessing is fit only on training folds (leakage-free by construction,
fixing the legacy full-dataset scaler fit).
"""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.config import (
    BINARY_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
)


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, list(NUMERIC_FEATURES)),
            ("binary", "passthrough", list(BINARY_FEATURES)),
            ("categorical", categorical_pipeline, list(CATEGORICAL_FEATURES)),
        ],
        remainder="drop",
        verbose_feature_names_out=True,
    )
