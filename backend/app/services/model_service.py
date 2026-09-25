"""Model service — thin orchestration over the Phase 1 ML predictor.

The ml package remains the single owner of feature processing, model
loading, prediction and metadata. This service only adapts it to the API
layer (startup loading, structured errors) and never duplicates ML logic.
"""

from __future__ import annotations

from typing import Any

from backend.app.core.logging import get_logger

logger = get_logger("backend.model_service")


class ModelUnavailableError(RuntimeError):
    """Raised when the ML artifact cannot be used (startup or runtime)."""


class ModelService:
    """Loads the modern predictor once and serves predictions from memory."""

    def __init__(self) -> None:
        self._predictor: Any = None
        self._metadata: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def load(self, models_dir: str | None = None) -> None:
        """Load the modern (v2) predictor. Called once from app lifespan."""
        try:
            from ml.inference.predictor import load_predictor

            self._predictor = load_predictor(models_dir or None)
            self._metadata = self._predictor.metadata
            logger.info(
                "ML predictor loaded: model_version=%s selected_model=%s",
                self._metadata.get("model_version"),
                self._metadata.get("selected_model"),
            )
        except Exception as exc:  # noqa: BLE001 - converted to app error
            self._predictor = None
            logger.error("Failed to load ML predictor: %s", exc)
            raise ModelUnavailableError(str(exc)) from exc

    @property
    def is_ready(self) -> bool:
        return self._predictor is not None

    @property
    def model_version(self) -> str:
        return str(self._metadata.get("model_version", "unknown"))

    @property
    def selected_model(self) -> str:
        return str(self._metadata.get("selected_model", "unknown"))

    # ------------------------------------------------------------------ #
    # Prediction
    # ------------------------------------------------------------------ #

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        if not self.is_ready:
            raise ModelUnavailableError("ML model not loaded")
        return self._predictor.predict(features)

    def explain(self, features: dict[str, Any], top_k: int = 8) -> dict[str, Any]:
        if not self.is_ready:
            raise ModelUnavailableError("ML model not loaded")
        return self._predictor.explain(features, top_k=top_k)
