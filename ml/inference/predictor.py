"""Modern inference layer for the v2 model.

Loads ONE versioned artifact (preprocessing + classifier + calibration),
validates inputs against the pipeline contract, and returns a structured,
semantically unambiguous result:

    {
      "model_version": "2.0.0",
      "predicted_disease": true,          # 1 = disease class at 0.5
      "disease_probability": 0.73,        # P(disease), calibrated
      "probability_label": "model_estimated_probability",
      ...
    }

Wording policy: the probability is a *model-estimated probability of the
disease class* for an educational prototype — NOT a clinically validated
risk score.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml.config import (
    FEATURE_RANGES,
    METADATA_PATH,
    MODEL_VERSION,
    MODELS_DIR,
    PIPELINE_PATH,
    POSITIVE_CLASS,
    PROBABILITY_LABEL,
    RAW_FEATURE_ORDER,
)

BACKGROUND_SAMPLE_PATH = None  # set per-instance from models_dir


class ModelNotLoadedError(RuntimeError):
    """Raised when the modern artifact cannot be loaded."""


class FeatureValidationError(ValueError):
    """Raised when input features fail schema/range validation."""


class Predictor:
    """Inference wrapper around the versioned v2 pipeline artifact."""

    def __init__(self, pipeline: Any, metadata: dict[str, Any]):
        self.pipeline = pipeline
        self.metadata = metadata
        self.model_version: str = metadata.get("model_version", MODEL_VERSION)
        self.features: tuple[str, ...] = tuple(metadata.get("features", RAW_FEATURE_ORDER))
        self._expected_classes = self._classifier_classes()

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    @classmethod
    def load(
        cls,
        models_dir: Path | str | None = None,
    ) -> Predictor:
        base = Path(models_dir) if models_dir else MODELS_DIR
        pipeline_path = base / PIPELINE_PATH.name
        metadata_path = base / METADATA_PATH.name
        background_path = base / "background_sample.joblib"
        try:
            pipeline = joblib.load(pipeline_path)
        except FileNotFoundError as exc:
            raise ModelNotLoadedError(
                f"Modern pipeline artifact not found at {pipeline_path}. "
                "Run: .venv/Scripts/python -m ml.training.train"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - version mismatches etc.
            raise ModelNotLoadedError(
                f"Failed to load modern pipeline from {pipeline_path}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        try:
            metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            metadata = {"model_version": MODEL_VERSION, "warning": "metadata.json exclusively missing"}
        instance = cls(pipeline, metadata)
        try:
            instance._background = joblib.load(background_path)
        except FileNotFoundError:
            instance._background = None  # explain() will degrade gracefully
        return instance

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def validate_features(self, features: dict[str, Any]) -> dict[str, float]:
        """Validate names, presence, casts and ranges; return ordered values."""
        errors: list[str] = []
        values: dict[str, float] = {}
        for name in self.features:
            raw = features.get(name)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                errors.append(f"{name}: field is required")
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                errors.append(f"{name}: '{raw}' is not numeric")
                continue
            low, high = FEATURE_RANGES.get(name, (float("-inf"), float("inf")))
            if not (low <= v <= high):
                errors.append(f"{name}: must be between {low} and {high}")
                continue
            values[name] = v
        if errors:
            raise FeatureValidationError("; ".join(errors))
        return values

    # ------------------------------------------------------------------ #
    # Prediction
    # ------------------------------------------------------------------ #

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """Full structured prediction from a raw feature dict."""
        values = self.validate_features(features)
        X = pd.DataFrame(
            [[values[name] for name in self.features]],
            columns=list(self.features),
        )
        proba = float(self.pipeline.predict_proba(X)[0, self._positive_class_index()])
        predicted = proba >= 0.5
        return {
            "model_version": self.model_version,
            "predicted_disease": bool(predicted),
            "disease_probability": proba,
            "probability_label": PROBABILITY_LABEL,
            "model_name": self.metadata.get("model_name"),
            "selected_model": self.metadata.get("selected_model"),
            "calibration": self.metadata.get("calibration"),
            "features_used": values,
            "target_semantics": self.metadata.get(
                "target_semantics", "1 = disease, 0 = no disease"
            ),
            "disclaimer": (
                "Model-estimated probability from an educational prototype; "
                "not a clinically validated risk score."
            ),
        }

    def explain(self, features: dict[str, Any], top_k: int = 8) -> dict[str, Any]:
        """Local explanation for one input (model contributions, not causes).

        For a CalibratedClassifierCV artifact, SHAP contributions are computed
        per calibrated member (each member is a full fitted Pipeline) and
        averaged, mirroring how predict_proba averages members.
        """
        values = self.validate_features(features)
        X = pd.DataFrame(
            [[values[name] for name in self.features]],
            columns=list(self.features),
        )
        try:
            member_pipelines = self._member_pipelines()
            if getattr(self, "_background", None) is None:
                raise ModelNotLoadedError(
                    "background_sample.joblib missing; cannot compute SHAP"
                )
            # Members come from different CV folds; a fold whose training data
            # lacks a rare category produces fewer one-hot columns. Align by
            # each member's own transformed names into a union. The SHAP
            # background is a persisted TRAIN-split sample, transformed with
            # each member's own preprocessing.
            sums: dict[str, float] = {}
            for member in member_pipelines:
                pre = member.named_steps["preprocessor"]
                clf = member.named_steps["classifier"]
                X_t = pre.transform(X)
                bg_t = pre.transform(self._background)
                names_m = [str(n) for n in pre.get_feature_names_out()]
                sv_m = self._member_shap(clf, X_t, bg_t)[0]
                for n, v in zip(names_m, sv_m, strict=False):
                    sums[n] = sums.get(n, 0.0) + float(v)
            n_members = len(member_pipelines)
            mean_by_name = {n: s / n_members for n, s in sums.items()}
            contributions = sorted(
                (
                    {"feature": n, "shap_value": v}
                    for n, v in mean_by_name.items()
                ),
                key=lambda d: abs(d["shap_value"]),
                reverse=True,
            )
            method = (
                f"shap averaged over {n_members} calibrated member(s); "
                f"background={len(self._background)} train rows"
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "method": "unavailable",
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "contributions": [],
                "note": "model contributions; not causal explanations",
            }
        return {
            "method": method,
            "contributions": contributions[:top_k],
            "note": "model contributions; not causal explanations",
        }

    def _member_pipelines(self) -> list[Any]:
        """Return the fitted base Pipeline(s) inside the artifact."""
        if hasattr(self.pipeline, "named_steps"):
            return [self.pipeline]
        if hasattr(self.pipeline, "calibrated_classifiers_"):
            return [cc.estimator for cc in self.pipeline.calibrated_classifiers_]
        raise ValueError(
            f"Unsupported artifact structure: {type(self.pipeline).__name__}"
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _classifier_classes(self) -> np.ndarray:
        try:
            return np.asarray(self.pipeline.classes_)
        except AttributeError:
            # CalibratedClassifierCV delegates classes_
            clf = self.pipeline.named_steps.get("classifier")
            return np.asarray(getattr(clf, "classes_", [0, 1]))

    def _positive_class_index(self) -> int:
        classes = list(self._expected_classes)
        if POSITIVE_CLASS in classes:
            return classes.index(POSITIVE_CLASS)
        raise ModelNotLoadedError(
            f"Pipeline classes {classes} do not contain positive class {POSITIVE_CLASS}"
        )

    @staticmethod
    def _member_shap(member_clf, X_t, background_t) -> np.ndarray:
        import shap

        cls_name = type(member_clf).__name__
        if cls_name in ("RandomForestClassifier", "HistGradientBoostingClassifier"):
            explainer = shap.TreeExplainer(member_clf)
            sv = explainer.shap_values(X_t, check_additivity=False)
            if isinstance(sv, list):
                sv = sv[1]
            return np.asarray(sv)
        if cls_name == "LogisticRegression":
            explainer = shap.LinearExplainer(member_clf, background_t)
            return np.asarray(explainer.shap_values(X_t))
        raise ValueError(f"Unsupported classifier for SHAP: {cls_name}")


def load_predictor(models_dir: Path | str | None = None) -> Predictor:
    """Convenience loader used by the Flask app and tests."""
    return Predictor.load(models_dir)
