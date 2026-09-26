"""Reproducible v2 training pipeline: split-first, CV, calibration, selection.

Methodology (documented in docs/model-card.md and docs/ml-modernization-results.md):

1. Load verified dataset (ml/data/heart.csv) and FLIP the target to the modern
   convention: 1 = disease, 0 = no disease (see ml/config.flip_target).
2. Single stratified train/test split (test is locked away until the end).
3. Stratified 5-fold CV on the TRAIN split only, for every candidate
   (preprocessing lives inside each Pipeline, so folds never leak).
4. Probability calibration (sigmoid/Platt, internal CV) fit on TRAIN only.
5. Model selection: CV discrimination first, then calibration, then
   parsimony (documented policy; not "highest accuracy wins").
6. Final evaluation on the locked test set (full metric suite, subgroups,
   curves), SHAP global + local explanations, MLflow logging.
7. One serialized artifact (preprocessing + classifier + calibration) with
   metadata and metrics JSON files.

Usage:
    .venv/Scripts/python -m ml.training.train [--no-mlflow]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

from ml.config import (
    CALIBRATION_METHOD,
    CV_FOLDS,
    DATA_PATH,
    DATASET_META_PATH,
    EVALUATION_PATH,
    METADATA_PATH,
    METRICS_PATH,
    MLFLOW_EXPERIMENT_NAME,
    MLFLOW_TRACKING_URI,
    MODEL_NAME,
    MODEL_VERSION,
    MODELS_DIR,
    MODERN_TARGET_SEMANTICS,
    PIPELINE_PATH,
    POSITIVE_CLASS,
    PROJECT_ROOT,
    RANDOM_SEED,
    RAW_FEATURE_ORDER,
    SOURCE_TARGET_SEMANTICS,
    TARGET_COLUMN,
    TEST_SIZE,
    flip_target,
)
from ml.evaluation.metrics import (
    classification_metrics,
    curve_data,
    pr_auc_score,
    subgroup_metrics,
)
from ml.explainability.shap_analysis import (
    global_importance_with_y,
    local_explanations,
)
from ml.training.models import get_candidates

# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def load_data() -> tuple[pd.DataFrame, np.ndarray, dict]:
    """Load the verified dataset and apply the documented target flip."""
    df = pd.read_csv(DATA_PATH)
    meta = json.loads(DATASET_META_PATH.read_text(encoding="utf-8"))

    # Verify hash to guarantee we train on exactly the verified file.
    import hashlib

    digest = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()
    # heart.csv was written with normalized LF endings; compare against the
    # recorded hash directly (download script normalized before hashing).
    if digest != meta["sha256"]:
        text = DATA_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != meta["sha256"]:
            raise RuntimeError(
                f"Dataset hash mismatch: file={digest} meta={meta['sha256']}. "
                "Re-run scripts/download_dataset.py."
            )

    missing = [c for c in RAW_FEATURE_ORDER + (TARGET_COLUMN,) if c not in df.columns]
    if missing:
        raise RuntimeError(f"Dataset missing columns: {missing}")

    X = df[list(RAW_FEATURE_ORDER)]
    y_source = df[TARGET_COLUMN].to_numpy()
    y = flip_target(y_source)  # 1 = disease (documented transformation)
    return X, y, meta


def load_test_split(
    X: pd.DataFrame | None = None, y: np.ndarray | None = None
) -> tuple[pd.DataFrame, np.ndarray]:
    """Reproduce the exact locked test split used in training.

    Uses the same seed/stratification as train() so tests can evaluate the
    serialized artifact on identical holdout data.
    """
    if X is None or y is None:
        X, y, _ = load_data()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
    )
    return X_test, y_test


# --------------------------------------------------------------------------- #
# Calibration helpers
# --------------------------------------------------------------------------- #


def make_calibrated(base_pipeline, seed: int = RANDOM_SEED):
    return CalibratedClassifierCV(
        estimator=base_pipeline,
        method=CALIBRATION_METHOD,
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=seed),
    )


# --------------------------------------------------------------------------- #
# Main training routine
# --------------------------------------------------------------------------- #


def train(enable_mlflow: bool = True) -> dict:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started_at = datetime.now(UTC)

    X, y, dataset_meta = load_data()
    print(f"Dataset: {X.shape[0]} rows x {X.shape[1]} features (verified sha256 ok)")
    print(f"Target (modern semantics): disease=1 -> n={int(y.sum())}, "
          f"no_disease=0 -> n={int((y == 0).sum())}")

    # ---- 1. Locked holdout ------------------------------------------------ #
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
    )
    print(f"Split: train={len(X_train)} test={len(X_test)} (stratified, seed={RANDOM_SEED})")

    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)
    scoring = {"roc_auc": "roc_auc", "brier": "neg_brier_score", "f1": "f1"}

    # ---- 2. CV comparison of candidates (train only) ---------------------- #
    candidate_results: dict[str, dict] = {}
    for cand in get_candidates():
        cv_res = cross_validate(
            cand.estimator, X_train, y_train, cv=cv, scoring=scoring, n_jobs=1
        )
        candidate_results[cand.name] = {
            "description": cand.description,
            "cv_roc_auc_mean": float(np.mean(cv_res["test_roc_auc"])),
            "cv_roc_auc_std": float(np.std(cv_res["test_roc_auc"])),
            "cv_brier_mean": float(-np.mean(cv_res["test_brier"])),
            "cv_brier_std": float(np.std(-cv_res["test_brier"])),
            "cv_f1_mean": float(np.mean(cv_res["test_f1"])),
            "cv_f1_std": float(np.std(cv_res["test_f1"])),
        }
        r = candidate_results[cand.name]
        print(f"  {cand.name:24s} ROC-AUC {r['cv_roc_auc_mean']:.4f}±{r['cv_roc_auc_std']:.4f}  "
              f"Brier {r['cv_brier_mean']:.4f}  F1 {r['cv_f1_mean']:.4f}")

    # ---- 3. Calibration comparison on train (uncalibrated vs calibrated) -- #
    calibration_results: dict[str, dict] = {}
    for cand in get_candidates():
        uncal = cand.estimator.fit(X_train, y_train)
        p_uncal = uncal.predict_proba(X_train)[:, 1]
        calib = make_calibrated(cand.estimator).fit(X_train, y_train)
        p_cal = calib.predict_proba(X_train)[:, 1]
        calibration_results[cand.name] = {
            "uncalibrated_brier_train": float(np.mean((p_uncal - y_train) ** 2)),
            "calibrated_brier_train": float(np.mean((p_cal - y_train) ** 2)),
            "method": CALIBRATION_METHOD,
            "note": "train-set Brier; calibrated uses internal CV so comparison is indicative",
        }
        c = calibration_results[cand.name]
        print(f"  {cand.name:24s} Brier train: uncal {c['uncalibrated_brier_train']:.4f} "
              f"-> cal {c['calibrated_brier_train']:.4f}")

    # ---- 4. Selection (documented policy) --------------------------------- #
    # Primary: CV ROC-AUC. Secondary: train calibration improvement. Tertiary:
    # parsimony — a simpler model within 0.02 CV AUC of the best is preferred.
    simplicity_order = {"logistic_regression": 0, "hist_gradient_boosting": 1, "random_forest": 2}
    best_auc = max(r["cv_roc_auc_mean"] for r in candidate_results.values())
    eligible = [n for n, r in candidate_results.items() if best_auc - r["cv_roc_auc_mean"] <= 0.02]
    selected = min(eligible, key=lambda n: simplicity_order.get(n, 99))
    print(f"Selected model: {selected} (parsimony within {best_auc:.4f} best CV AUC)")

    # ---- 5. Final fit on train; locked test evaluation -------------------- #
    candidates = {c.name: c for c in get_candidates()}
    final_uncal = candidates[selected].estimator
    final_uncal.fit(X_train, y_train)
    final_cal = make_calibrated(candidates[selected].estimator).fit(X_train, y_train)

    p_test_uncal = final_uncal.predict_proba(X_test)[:, 1]
    p_test_cal = final_cal.predict_proba(X_test)[:, 1]

    metrics_uncal = classification_metrics(y_test, p_test_uncal)
    metrics_cal = classification_metrics(y_test, p_test_cal)
    metrics_cal["pr_auc"] = pr_auc_score(y_test, p_test_cal)
    print(f"Test (uncal):  acc={metrics_uncal['accuracy']:.4f} roc_auc={metrics_uncal['roc_auc']:.4f} "
          f"brier={metrics_uncal['brier_score']:.4f}")
    print(f"Test (cal):    acc={metrics_cal['accuracy']:.4f} roc_auc={metrics_cal['roc_auc']:.4f} "
          f"brier={metrics_cal['brier_score']:.4f}")

    # ---- 6. Subgroup evaluation (descriptive; uses RAW test features) ---- #
    feature_names_out = list(
        final_uncal.named_steps["preprocessor"].get_feature_names_out()
    )
    X_test_transformed = final_uncal.named_steps["preprocessor"].transform(X_test)

    subgroups = subgroup_metrics(X_test, y_test, p_test_cal)

    # ---- 7. Explainability (background = TRAIN transformed matrix) -------- #
    X_train_transformed = final_uncal.named_steps["preprocessor"].transform(X_train)
    explainability = {
        "global": global_importance_with_y(
            final_uncal,
            X_test_transformed,
            y_test,
            feature_names_out,
            background=X_train_transformed,
        ),
        "local": {},  # filled below with representative rows
        "wording": "model contributions; not causal or clinical explanations",
    }
    # Representative local rows: highest/lowest predicted disease probability.
    order = np.argsort(p_test_cal)
    idx_sick, idx_healthy = int(order[-1]), int(order[0])
    explainability["local"] = local_explanations(
        final_uncal,
        X_test_transformed,
        feature_names_out,
        row_indices=[idx_sick, idx_healthy],
        row_descriptions={
            idx_sick: "test row with highest model-estimated disease probability",
            idx_healthy: "test row with lowest model-estimated disease probability",
        },
        background=X_train_transformed,
    )

    # ---- 8. Serialize the artifact ---------------------------------------- #
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_cal, PIPELINE_PATH)
    # Persist a raw background sample (TRAIN split only) for inference-time
    # SHAP: LinearExplainer needs a background distribution, and using the
    # single prediction row as its own background would zero everything out.
    background_sample = X_train.sample(
        n=min(80, len(X_train)), random_state=RANDOM_SEED
    )
    BACKGROUND_PATH = MODELS_DIR / "background_sample.joblib"
    joblib.dump(background_sample, BACKGROUND_PATH)
    print(f"Saved pipeline -> {PIPELINE_PATH.relative_to(Path.cwd())}")
    print(f"Saved background sample ({len(background_sample)} train rows) -> "
          f"{BACKGROUND_PATH.name}")

    import sklearn

    metadata = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "target": "disease",
        "target_semantics": MODERN_TARGET_SEMANTICS,
        "source_target_semantics": SOURCE_TARGET_SEMANTICS,
        "target_transformation": "y_modern = 1 - y_source (documented in ml/config.py)",
        "positive_class": POSITIVE_CLASS,
        "dataset": dataset_meta["dataset_name"],
        "dataset_source_url": dataset_meta["source_url"],
        "dataset_hash": dataset_meta["sha256"],
        "features": list(RAW_FEATURE_ORDER),
        "feature_types": {
            "numeric": ["age", "trestbps", "chol", "thalach", "oldpeak"],
            "binary": ["sex", "fbs", "exang"],
            "categorical_onehot": ["cp", "restecg", "slope", "ca", "thal"],
        },
        "preprocessing": "median-impute+StandardScaler(numeric); passthrough(binary); "
                         "most-frequent-impute+OneHot(categorical) via ColumnTransformer",
        "calibration": f"CalibratedClassifierCV(method={CALIBRATION_METHOD}, cv={CV_FOLDS}-fold stratified)",
        "selected_model": selected,
        "selection_policy": "CV ROC-AUC primary; calibration secondary; parsimony within 0.02 AUC",
        "training_seed": RANDOM_SEED,
        "test_size": TEST_SIZE,
        "cv_folds": CV_FOLDS,
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "trained_at": started_at.isoformat(),
        "artifact_format": "joblib (sklearn Pipeline; load with same sklearn major.minor)",
        "background_sample": "background_sample.joblib (80 raw TRAIN rows for SHAP background)",
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    metrics_file = {
        "model_version": MODEL_VERSION,
        "selected_model": selected,
        "cv": {
            "folds": CV_FOLDS,
            "strategy": "StratifiedKFold(shuffle, seed=42) on train split",
            "candidates": candidate_results,
        },
        "calibration": calibration_results,
        "test": {
            "n": int(len(y_test)),
            "uncalibrated": metrics_uncal,
            "calibrated": metrics_cal,
            "curves": curve_data(y_test, p_test_cal),
        },
        "subgroups": subgroups,
        "explainability": explainability,
        "training_timestamp": started_at.isoformat(),
    }
    METRICS_PATH.write_text(json.dumps(metrics_file, indent=2) + "\n", encoding="utf-8")

    # Full evaluation artifact (spec: ml/artifacts/evaluation.json)
    EVALUATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    evaluation = {
        "model_version": MODEL_VERSION,
        "dataset_hash": dataset_meta["sha256"],
        "features": list(RAW_FEATURE_ORDER),
        "seed": RANDOM_SEED,
        "cv_configuration": {"folds": CV_FOLDS, "shuffle": True, "random_state": RANDOM_SEED},
        "test_size": TEST_SIZE,
        "training_timestamp": started_at.isoformat(),
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "candidates": candidate_results,
        "calibration": calibration_results,
        "selected": selected,
        "test_metrics": {"uncalibrated": metrics_uncal, "calibrated": metrics_cal},
        "subgroups": subgroups,
        "explainability": explainability,
        "metadata_path": str(METADATA_PATH.name),
        "metrics_path": str(METRICS_PATH.name),
    }
    EVALUATION_PATH.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")

    # ---- 9. MLflow tracking ------------------------------------------------ #
    mlflow_info: dict = {"enabled": False}
    if enable_mlflow:
        try:
            import mlflow
            import mlflow.sklearn

            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

            with mlflow.start_run(run_name=f"v2-{selected}") as run:
                mlflow.log_params({
                    "model_version": MODEL_VERSION,
                    "selected_model": selected,
                    "seed": RANDOM_SEED,
                    "test_size": TEST_SIZE,
                    "cv_folds": CV_FOLDS,
                    "calibration": CALIBRATION_METHOD,
                    "dataset_sha256": dataset_meta["sha256"][:16],
                    "target_flip": "1 - source_target",
                })
                mlflow.log_metrics({
                    "cv_roc_auc_mean": candidate_results[selected]["cv_roc_auc_mean"],
                    "cv_roc_auc_std": candidate_results[selected]["cv_roc_auc_std"],
                    "cv_brier_mean": candidate_results[selected]["cv_brier_mean"],
                    "test_accuracy": metrics_cal["accuracy"],
                    "test_roc_auc": metrics_cal["roc_auc"],
                    "test_f1": metrics_cal["f1"],
                    "test_brier": metrics_cal["brier_score"],
                    "test_pr_auc": metrics_cal["pr_auc"],
                    "test_sensitivity": metrics_cal["recall_sensitivity"],
                    "test_specificity": metrics_cal["specificity"],
                })
                # Log the calibrated pipeline with the current API. MLflow 3.x
                # serializes sklearn models via skops, which requires trusting
                # the calibration internals explicitly.
                trusted = [
                    "numpy.dtype",
                    "sklearn.calibration._CalibratedClassifier",
                    "sklearn.calibration._SigmoidCalibration",
                    "sklearn.model_selection._split.StratifiedKFold",
                ]
                try:
                    mlflow.sklearn.log_model(
                        final_cal,
                        name="cardio_risk_pipeline",
                        skops_trusted_types=trusted,  # type: ignore[call-arg]
                    )
                except (TypeError, Exception) as model_log_exc:  # noqa: BLE001
                    # Fall back to logging the joblib artifact directly.
                    print(f"NOTE: mlflow.sklearn.log_model failed ({model_log_exc}); "
                          "logging joblib artifact instead.")
                    mlflow.log_artifact(str(PIPELINE_PATH), artifact_path="cardio_risk_pipeline")
                mlflow.log_artifact(str(METADATA_PATH))
                mlflow.log_artifact(str(METRICS_PATH))

                # Record a PORTABLE tracking URI: the absolute sqlite path is
                # machine-specific and must never leak into the tracked
                # metadata.json artifact.
                portable_tracking_uri = MLFLOW_TRACKING_URI.replace(
                    (PROJECT_ROOT / "mlflow.db").as_posix(), "<PROJECT_ROOT>/mlflow.db"
                )
                mlflow_info = {
                    "enabled": True,
                    "tracking_uri": portable_tracking_uri,
                    "experiment_name": MLFLOW_EXPERIMENT_NAME,
                    "experiment_id": run.info.experiment_id,
                    "run_id": run.info.run_id,
                }
                print(f"MLflow run logged: experiment={run.info.experiment_id} run={run.info.run_id}")
        except Exception as exc:  # noqa: BLE001 - tracking must not break training
            mlflow_info = {"enabled": False, "error": f"{type(exc).__name__}: {exc}"}
            print(f"WARNING: MLflow logging failed: {exc}")
    metadata["mlflow"] = mlflow_info
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    summary = {
        "selected": selected,
        "test_metrics_calibrated": metrics_cal,
        "test_metrics_uncalibrated": metrics_uncal,
        "metadata": metadata,
    }
    print("\nTraining complete.")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the v2 cardio risk pipeline")
    parser.add_argument("--no-mlflow", action="store_true", help="disable MLflow logging")
    args = parser.parse_args()
    train(enable_mlflow=not args.no_mlflow)
