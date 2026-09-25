"""Explainability for the selected v2 pipeline.

Produces:
- global feature importance (mean |SHAP| over the evaluation rows),
- local per-feature contributions for representative rows,
- permutation-importance fallback when SHAP cannot handle the estimator.

Wording policy (medical-safety): SHAP values are *model contributions*, not
causal or clinical explanations. Downstream code must present them as
"features influencing this prediction", never as "causes of disease".

Background data policy: LinearExplainer requires a background distribution.
The TRAIN-split transformed matrix is used (never the evaluation rows as
their own background, which would bias contributions toward zero).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ml.config import RANDOM_SEED


def _get_shap_values(
    classifier: Any,
    X_transformed: np.ndarray,
    background: np.ndarray | None,
) -> tuple[np.ndarray, str]:
    """SHAP values for the disease class; returns (values, method)."""
    import shap

    cls_name = type(classifier).__name__

    if cls_name in ("RandomForestClassifier", "HistGradientBoostingClassifier"):
        explainer = shap.TreeExplainer(classifier)
        values = explainer.shap_values(X_transformed, check_additivity=False)
        if isinstance(values, list):  # older API: list per class
            values = values[1]
        return np.asarray(values), f"shap.TreeExplainer ({cls_name})"

    if cls_name == "LogisticRegression":
        bg = X_transformed if background is None else background
        explainer = shap.LinearExplainer(classifier, bg)
        return np.asarray(explainer.shap_values(X_transformed)), "shap.LinearExplainer"

    raise ValueError(f"Unsupported classifier for SHAP: {cls_name}")


def _ranked(contributions: np.ndarray, feature_names: list[str]) -> list[dict[str, Any]]:
    return sorted(
        (
            {"feature": name, "value": float(v)}
            for name, v in zip(feature_names, contributions, strict=False)
        ),
        key=lambda d: abs(d["value"]),
        reverse=True,
    )


def global_importance_with_y(
    pipeline,
    X_transformed: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    background: np.ndarray | None = None,
    max_rows: int = 200,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Mean |SHAP| per feature, with permutation-importance fallback."""
    classifier = pipeline.named_steps["classifier"]
    try:
        shap_values, method = _get_shap_values(classifier, X_transformed, background)
        mean_abs = np.abs(shap_values).mean(axis=0)
        importance = [
            {"feature": d["feature"], "mean_abs_shap": d["value"]}
            for d in _ranked(mean_abs, feature_names)
        ]
        return {"method": method, "importance": importance}
    except Exception as exc:  # noqa: BLE001 - documented fallback path
        from sklearn.inspection import permutation_importance

        rng = np.random.RandomState(seed)
        idx = rng.choice(
            len(X_transformed), size=min(max_rows, len(X_transformed)), replace=False
        )
        result = permutation_importance(
            classifier, X_transformed[idx], y[idx], n_repeats=10, random_state=seed
        )
        importance = [
            {"feature": d["feature"], "mean_abs_shap": d["value"]}
            for d in _ranked(result.importances_mean, feature_names)
        ]
        return {
            "method": f"permutation_importance (SHAP fallback: {type(exc).__name__})",
            "importance": importance,
            "fallback_reason": str(exc)[:300],
        }


def local_explanations(
    pipeline,
    X_transformed: np.ndarray,
    feature_names: list[str],
    row_indices: list[int],
    row_descriptions: dict[int, str] | None = None,
    background: np.ndarray | None = None,
) -> dict[str, Any]:
    """Per-feature SHAP contributions for selected rows."""
    classifier = pipeline.named_steps["classifier"]
    try:
        shap_values, method = _get_shap_values(classifier, X_transformed, background)
        out: dict[str, Any] = {"method": method, "rows": {}}
        for i in row_indices:
            row_entry: dict[str, Any] = {
                "top_contributions": _ranked(shap_values[i], feature_names)[:8],
                "note": "model contributions (SHAP); not causal explanations",
            }
            if row_descriptions and i in row_descriptions:
                row_entry["description"] = row_descriptions[i]
            out["rows"][str(i)] = row_entry
        return out
    except Exception as exc:  # noqa: BLE001
        return {
            "method": "unavailable",
            "error": f"SHAP local explanation failed: {type(exc).__name__}: {str(exc)[:200]}",
            "rows": {},
        }
