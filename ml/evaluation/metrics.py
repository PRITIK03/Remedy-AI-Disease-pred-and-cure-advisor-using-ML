"""Evaluation helpers: full metric suite, subgroup evaluation, curves."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    auc,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
    roc_curve,
)


def classification_metrics(
    y_true: np.ndarray,
    proba: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Complete metric suite for one probability vector (disease=1)."""
    y_pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    metrics: dict[str, Any] = {
        "accuracy": float((y_pred == y_true).mean()),
        "precision": float(precision),
        "recall_sensitivity": float(recall),
        "specificity": float(specificity),
        "f1": float(f1),
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(auc(
            *precision_recall_curve(y_true, proba)[:2][::-1]
        )),
        "brier_score": float(brier_score_loss(y_true, proba)),
        "confusion_matrix": {
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)
        },
        "threshold": threshold,
    }
    return metrics


def pr_auc_score(y_true: np.ndarray, proba: np.ndarray) -> float:
    """PR-AUC (average precision) computed directly."""
    from sklearn.metrics import average_precision_score

    return float(average_precision_score(y_true, proba))


def subgroup_metrics(
    X_raw,
    y_true: np.ndarray,
    proba: np.ndarray,
    feature_names: list[str] | None = None,
) -> dict[str, Any]:
    """Descriptive subgroup evaluation (sex; age bands).

    Uses the RAW (untransformed) feature matrix: one-hot/z-scored columns
    must not be thresholded as if they were raw values. Deliberately
    descriptive: with n=303, no fairness claims are made. Where a subgroup
    is too small the entry records that explicitly.
    """
    results: dict[str, Any] = {}

    def evaluate(mask: np.ndarray, label: str) -> dict[str, Any]:
        n = int(mask.sum())
        if n < 10:
            return {"n": n, "note": "Insufficient sample size for reliable subgroup conclusions."}
        sub_y = y_true[mask]
        sub_p = proba[mask]
        entry: dict[str, Any] = {"n": n}
        # Sensitivity/specificity at 0.5 (descriptive only).
        y_pred = (sub_p >= 0.5).astype(int)
        tn, fp, fn, tp = confusion_matrix(sub_y, y_pred, labels=[0, 1]).ravel()
        entry["sensitivity"] = float(tp / (tp + fn)) if (tp + fn) else None
        entry["specificity"] = float(tn / (tn + fp)) if (tn + fp) else None
        # ROC-AUC only if both classes present.
        if len(np.unique(sub_y)) == 2:
            entry["roc_auc"] = float(roc_auc_score(sub_y, sub_p))
            entry["roc_auc_note"] = "descriptive; wide confidence interval at this n"
        else:
            entry["roc_auc"] = None
            entry["roc_auc_note"] = "single class present; not computed"
        # Brier as simple calibration indicator.
        entry["brier_score"] = float(brier_score_loss(sub_y, sub_p))
        return entry

    # Sex subgroups (raw binary column).
    if "sex" in X_raw.columns:
        sex_values = X_raw["sex"].to_numpy()
        results["sex_female_0"] = evaluate(sex_values == 0, "female")
        results["sex_male_1"] = evaluate(sex_values == 1, "male")

    # Age bands (raw numeric column).
    if "age" in X_raw.columns:
        ages = X_raw["age"].to_numpy()
        bands = [
            ("age_under_50", ages < 50),
            ("age_50_to_59", (ages >= 50) & (ages < 60)),
            ("age_60_plus", ages >= 60),
        ]
        for label, mask in bands:
            results[label] = evaluate(mask.astype(bool), label)

    return results


def curve_data(y_true: np.ndarray, proba: np.ndarray) -> dict[str, Any]:
    """Curve points for ROC / PR / calibration (for JSON artifacts)."""
    fpr, tpr, _ = roc_curve(y_true, proba)
    prec, rec, _ = precision_recall_curve(y_true, proba)
    from sklearn.calibration import calibration_curve

    frac_pos, mean_pred = calibration_curve(y_true, proba, n_bins=5, strategy="quantile")
    return {
        "roc": {"fpr": fpr.round(6).tolist(), "tpr": tpr.round(6).tolist()},
        "pr": {"recall": rec.round(6).tolist(), "precision": prec.round(6).tolist()},
        "calibration": {
            "mean_predicted": mean_pred.round(6).tolist(),
            "fraction_positive": frac_pos.round(6).tolist(),
            "bins": 5,
        },
    }
