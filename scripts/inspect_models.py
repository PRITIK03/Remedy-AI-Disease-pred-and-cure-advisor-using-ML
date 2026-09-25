"""Safe inspection of legacy ML artifacts.

Loads the repository's own pickle artifacts (trusted: they are part of this
legacy project) and reports their structure and metadata WITHOUT running any
inference or retraining. Read-only with respect to the artifacts.

Usage:
    python scripts/inspect_models.py
"""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

# Legacy artifacts live flat in the project root; MODEL_DIR env var overrides.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.getenv("MODEL_DIR", str(PROJECT_ROOT)))

ARTIFACTS = [
    "logistic_regression_model.pkl",
    "random_forest_model.pkl",
    "voting_classifier_model.pkl",
    "scaler.pkl",
]


def describe(obj: object, indent: str = "") -> list[str]:
    lines: list[str] = []
    cls = type(obj).__name__
    mod = type(obj).__module__
    lines.append(f"{indent}- class: {mod}.{cls}")

    if hasattr(obj, "get_params"):
        try:
            params = obj.get_params()
            shown = {k: v for k, v in params.items() if v is not None}
            lines.append(f"{indent}- get_params: {shown}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{indent}- get_params: <error: {exc}>")

    if hasattr(obj, "n_features_in_"):
        lines.append(f"{indent}- n_features_in_: {obj.n_features_in_}")

    if hasattr(obj, "feature_names_in_"):
        lines.append(f"{indent}- feature_names_in_: {list(obj.feature_names_in_)}")

    if hasattr(obj, "classes_"):
        lines.append(f"{indent}- classes_: {obj.classes_}")

    if hasattr(obj, "estimators_"):
        ests = obj.estimators_
        lines.append(f"{indent}- estimators_: {len(ests)} member(s)")
        for i, est in enumerate(ests[:5]):
            sub = type(est).__module__ + "." + type(est).__name__
            lines.append(f"{indent}  - [{i}] {sub}")

    if hasattr(obj, "estimators"):
        lines.append(f"{indent}- estimators param: {obj.estimators}")

    if hasattr(obj, "named_estimators_"):
        for name, est in obj.named_estimators_.items():
            sub = type(est).__module__ + "." + type(est).__name__
            lines.append(f"{indent}- named_estimators_['{name}']: {sub}")

    if hasattr(obj, "mean_") and hasattr(obj, "scale_"):
        lines.append(f"{indent}- scaler mean_: {obj.mean_}")
        lines.append(f"{indent}- scaler scale_: {obj.scale_}")
        lines.append(f"{indent}- scaler var_: {obj.var_}")

    if hasattr(obj, "voting"):
        lines.append(f"{indent}- voting: {obj.voting}")

    if hasattr(obj, "weights") and obj.weights is not None:
        lines.append(f"{indent}- weights: {obj.weights}")

    if hasattr(obj, "n_estimators"):
        lines.append(f"{indent}- n_estimators: {obj.n_estimators}")

    return lines


def main() -> int:
    if not MODELS_DIR.exists():
        print(f"ERROR: models directory not found: {MODELS_DIR}")
        return 1

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Models dir:   {MODELS_DIR}")
    print("=" * 70)

    for name in ARTIFACTS:
        path = MODELS_DIR / name
        print(f"\n### {name}")
        if not path.exists():
            print("  MISSING!")
            continue
        print(f"  size: {path.stat().st_size} bytes")
        try:
            with open(path, "rb") as f:
                obj = pickle.load(f)
        except Exception as exc:  # noqa: BLE001
            print(f"  LOAD FAILED: {type(exc).__name__}: {exc}")
            continue

        for line in describe(obj, indent="  "):
            print(line)

    print("\nPython:", sys.version)
    try:
        import sklearn

        print("scikit-learn:", sklearn.__version__)
    except ImportError:
        print("scikit-learn: NOT INSTALLED")
    import numpy

    print("numpy:", numpy.__version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
