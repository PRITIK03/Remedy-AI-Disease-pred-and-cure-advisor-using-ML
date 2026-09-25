"""Remedy-AI Flask application.

Phase 1 adds a model-provider abstraction on top of the Phase 0 fixes:

- ``MODEL_VERSION=v2`` (default): serve the modern, calibrated pipeline via
  ``ml.inference.predictor``. Public semantics are CORRECT:
  ``disease_probability > 0.5`` → high risk.
- ``MODEL_VERSION=v1``: serve the preserved legacy pickles with their
  documented inverted semantics (kept for regression comparison only).

The legacy pickles and their Phase 0 regression tests remain untouched.
"""

from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from flask import Flask, render_template, request
from werkzeug.exceptions import HTTPException

# --------------------------------------------------------------------------- #
# Configuration (env-overridable, no secrets required)
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent

# Which model generation to serve: v2 (modern, default) or v1 (legacy).
MODEL_VERSION = os.getenv("MODEL_VERSION", "v2")

# Legacy artifacts sit flat in the repository root. MODEL_DIR lets a future
# phase relocate them (e.g. models/) without code changes.
MODEL_DIR = Path(os.getenv("MODEL_DIR", str(BASE_DIR)))

# The legacy UI file lives at the repo root; Flask's default is <app>/templates.
TEMPLATE_FOLDER = Path(os.getenv("TEMPLATE_FOLDER", str(BASE_DIR)))

MODEL_FILES: dict[str, str] = {
    "logistic_regression": "logistic_regression_model.pkl",
    "random_forest": "random_forest_model.pkl",
    "voting_classifier": "voting_classifier_model.pkl",
    "scaler": "scaler.pkl",
}

# Raw feature order expected by the legacy artifacts (verified against
# scaler.feature_names_in_ — see docs/legacy-ml-baseline.md §3).
FEATURE_ORDER: tuple[str, ...] = (
    "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
    "thalach", "exang", "oldpeak", "slope", "ca", "thal",
)

# Casts applied to form values before scaling (legacy behavior preserved).
FEATURE_CASTS: dict[str, type] = {
    "age": int, "sex": int, "cp": int, "trestbps": int, "chol": int,
    "fbs": int, "restecg": int, "thalach": int, "exang": int,
    "oldpeak": float, "slope": int, "ca": int, "thal": int,
}

# Soft plausibility bounds (dataset-informed; rejections are 400s, not model
# behavior). Only used for validation — the model still sees the raw value.
FEATURE_RANGES: dict[str, tuple[float, float]] = {
    "age": (1, 120), "sex": (0, 1), "cp": (0, 3), "trestbps": (50, 250),
    "chol": (50, 700), "fbs": (0, 1), "restecg": (0, 2),
    "thalach": (40, 250), "exang": (0, 1), "oldpeak": (0.0, 10.0),
    "slope": (0, 2), "ca": (0, 4), "thal": (0, 3),
}

RISK_THRESHOLD = float(os.getenv("RISK_THRESHOLD", "0.5"))

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("remedy_ai")

# --------------------------------------------------------------------------- #
# Model loading
# --------------------------------------------------------------------------- #


def _load_pickle(name: str) -> Any:
    path = MODEL_DIR / MODEL_FILES[name]
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except FileNotFoundError as exc:
        logger.error("Model artifact not found: %s", path)
        raise RuntimeError(
            f"Model artifact '{name}' not found at {path}. "
            "Set MODEL_DIR or restore the .pkl files."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surfaced to caller
        logger.error("Failed to load model artifact %s: %s", path, exc)
        raise


def load_models() -> dict[str, Any]:
    """Load the legacy artifacts exactly once at startup."""
    return {name: _load_pickle(name) for name in MODEL_FILES}


# Legacy pickles are ALWAYS loaded: they back MODEL_VERSION=v1 mode and the
# internal regression path used by tests/test_legacy_model.py.
try:
    _models = load_models()
    logistic_regression_model = _models["logistic_regression"]
    random_forest_model = _models["random_forest"]
    voting_classifier_model = _models["voting_classifier"]
    scaler = _models["scaler"]
except RuntimeError:
    # Allow importing the module (e.g. for tooling) without artifacts present;
    # any request needing models will fail fast with a clear error.
    logistic_regression_model = random_forest_model = None
    voting_classifier_model = scaler = None

# Modern (v2) predictor — used by /predict unless MODEL_VERSION=v1.
modern_predictor = None
try:
    from ml.inference.predictor import load_predictor

    modern_predictor = load_predictor()
    logger.info(
        "Modern v2 pipeline loaded (version %s, selected model: %s)",
        modern_predictor.model_version,
        modern_predictor.metadata.get("selected_model"),
    )
except Exception as exc:  # noqa: BLE001 - app must still boot without artifact
    logger.warning(
        "Modern v2 pipeline not available (%s: %s); /predict will fall back to "
        "legacy v1 behavior. Run `python -m ml.training.train` to build it.",
        type(exc).__name__,
        exc,
    )


# --------------------------------------------------------------------------- #
# Flask app
# --------------------------------------------------------------------------- #

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_FOLDER),
)

# Suppress sklearn's InconsistentVersionWarning noise only for the documented
# 1.4.2-vs-1.3.2 case; a genuinely different artifact version stays visible.
try:
    import warnings

    from sklearn.exceptions import InconsistentVersionWarning

    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except ImportError:  # pragma: no cover
    pass


# --------------------------------------------------------------------------- #
# Recommendation logic (legacy, unchanged)
# --------------------------------------------------------------------------- #


def get_remedies(features: dict[str, float], predicted_risk: float) -> list[str]:
    """Legacy rule-based recommendations. Kept byte-for-byte in behavior."""
    remedies: list[str] = []

    if predicted_risk > 0.5:  # High risk
        remedies.append(
            "Consult a healthcare professional immediately for a thorough evaluation."
        )

    if features["age"] > 50:
        remedies.append("Schedule regular check-ups with your doctor.")

    if features["chol"] > 200:
        remedies.append(
            "Adopt a heart-healthy diet low in saturated fats and high in fruits, "
            "vegetables, and whole grains."
        )

    if features["trestbps"] > 130:
        remedies.append(
            "Monitor your blood pressure regularly and consider lifestyle changes "
            "to lower it."
        )

    if features["thalach"] < 120:
        remedies.append(
            "Improve your cardiovascular fitness through regular aerobic exercise."
        )

    if features["oldpeak"] > 1:
        remedies.append(
            "Discuss stress test results with your doctor and consider cardiac "
            "rehabilitation if recommended."
        )

    remedies.append(
        "Maintain a healthy weight through a balanced diet and regular exercise."
    )
    remedies.append("If you smoke, quit smoking or seek support to help you quit.")
    remedies.append(
        "Limit alcohol consumption to no more than one drink per day for women "
        "and two for men."
    )
    remedies.append(
        "Aim for at least 150 minutes of moderate-intensity exercise per week."
    )
    remedies.append(
        "Manage stress through relaxation techniques like meditation or yoga."
    )
    remedies.append(
        "Ensure you're getting 7-9 hours of quality sleep each night."
    )

    return remedies


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@app.route("/")
def home() -> str:
    return render_template("index.html")


def parse_features(form: Any) -> dict[str, float]:
    """Parse and validate the 13 legacy form fields.

    Raises ValueError with a user-readable message on any problem.
    """
    values: dict[str, float] = {}
    errors: list[str] = []

    for name in FEATURE_ORDER:
        raw = form.get(name)
        if raw is None or str(raw).strip() == "":
            errors.append(f"{name}: field is required")
            continue
        cast = FEATURE_CASTS[name]
        try:
            value = cast(str(raw).strip())
        except (TypeError, ValueError):
            errors.append(f"{name}: '{raw}' is not a valid {cast.__name__}")
            continue
        low, high = FEATURE_RANGES[name]
        if not (low <= value <= high):
            errors.append(f"{name}: must be between {low} and {high}")
            continue
        values[name] = value

    if errors:
        raise ValueError("; ".join(errors))
    return values


def predict_risk_probability(values: dict[str, float]) -> float:
    """Run the legacy inference path: scale → voting classifier → proba[:,1].

    NOTE (documented legacy behavior): the artifacts were trained with
    class 1 = *no disease*; the returned probability therefore represents
    P(healthy) in the legacy semantic. Preserved as-is for Phase 0.
    """
    if voting_classifier_model is None or scaler is None:
        raise RuntimeError("Models are not loaded; cannot serve predictions.")

    input_data = np.array([[values[name] for name in FEATURE_ORDER]], dtype=float)
    input_data_scaled = scaler.transform(input_data)
    proba = voting_classifier_model.predict_proba(input_data_scaled)[:, 1][0]
    return float(proba)


@app.route("/predict", methods=["POST"])
def predict() -> str:
    """Serve a prediction from the configured model generation.

    - MODEL_VERSION=v2 (default): modern calibrated pipeline; the probability
      is P(disease) with CORRECT semantics.
    - MODEL_VERSION=v1: preserved legacy path with its documented inverted
      semantics (regression comparison only).
    """
    try:
        values = parse_features(request.form)
        if MODEL_VERSION != "v1" and modern_predictor is not None:
            result = modern_predictor.predict(values)
            prediction_prob = result["disease_probability"]
            logger.info(
                "v2 prediction: disease_probability=%.4f predicted_disease=%s",
                prediction_prob,
                result["predicted_disease"],
            )
        else:
            # Legacy path — probability is P(healthy) in the legacy semantic
            # (documented inversion, docs/legacy-ml-baseline.md §6).
            prediction_prob = predict_risk_probability(values)
    except ValueError as exc:
        logger.info("Rejected prediction request: %s", exc)
        return render_template("index.html", prediction_result=f"Invalid input: {exc}")
    except Exception:  # noqa: BLE001 - log full detail, show generic message
        logger.exception("Prediction failed")
        return render_template(
            "index.html",
            prediction_result="Something went wrong while computing the prediction. "
            "Please try again.",
        )

    predicted_risk = prediction_prob * 100
    features = {
        "age": values["age"],
        "trestbps": values["trestbps"],
        "chol": values["chol"],
        "thalach": values["thalach"],
        "oldpeak": values["oldpeak"],
    }
    remedies = get_remedies(features, prediction_prob)

    if prediction_prob > RISK_THRESHOLD:
        result_text = f"High risk of heart disease: {predicted_risk:.2f}%"
    else:
        result_text = f"Low risk of heart disease: {predicted_risk:.2f}%"

    return render_template(
        "index.html", prediction_result=result_text, remedies=remedies
    )


@app.errorhandler(HTTPException)
def handle_http_exception(exc: HTTPException):
    """Return a simple text error for non-page requests (API friendliness)."""
    if request.path.startswith("/predict"):
        return exc
    return exc


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=debug)
