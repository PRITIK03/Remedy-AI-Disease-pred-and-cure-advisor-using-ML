"""Optional LangSmith tracing for graph/LLM debugging.

Never mandatory: when LANGCHAIN_* env vars are absent (the default), nothing
is configured and the application runs identically. MLflow remains the
experiment-tracking system; LangSmith is only a debugging aid for the graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.logging import get_logger

logger = get_logger("backend.agents.tracing")


@dataclass(frozen=True)
class TracingConfig:
    enabled: bool
    project: str | None = None
    endpoint: str | None = None


def get_tracing_config() -> TracingConfig:
    """Read LangSmith settings from the environment (never secrets into
    state or logs — the API key stays in os.environ for the SDK to pick up)."""
    import os

    enabled = os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
    project = os.environ.get("LANGCHAIN_PROJECT") or None
    endpoint = os.environ.get("LANGCHAIN_ENDPOINT") or None
    return TracingConfig(
        enabled=enabled,
        project=project if enabled else None,
        endpoint=endpoint if enabled else None,
    )


def log_tracing_status() -> None:
    cfg = get_tracing_config()
    if cfg.enabled:
        logger.info(
            "LangSmith tracing enabled (project=%s endpoint=%s)",
            cfg.project or "default",
            cfg.endpoint or "https://api.smith.langchain.com",
        )
    else:
        logger.info("LangSmith tracing disabled (no LANGCHAIN_TRACING_V2)")
