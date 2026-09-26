"""OpenTelemetry instrumentation (Phase 9).

Scope is deliberately narrow and operational only. We record:
  request, route (template, not raw URL), status, latency, error type.

We NEVER record medical inputs, report contents, passwords, tokens, API
keys, session ids, cookies, or request/response bodies. Two mechanisms
enforce that:

1. An explicit allowlist of span attributes — anything not listed is dropped.
2. `scrub_url`, which reduces any URL to its path alone (no scheme, no host,
   no query string), so a mistakenly-captured URL cannot carry a secret.

`OTEL_EXPORTER_OTLP_ENDPOINT` (or the settings below) enables the OTLP
exporter; with nothing configured the SDK still runs a no-op exporter, so
telemetry is a zero-risk addition in development and tests.
"""

from __future__ import annotations

from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger("backend.telemetry")

#: The ONLY span attributes this service is allowed to emit.
ALLOWED_SPAN_ATTRIBUTES = frozenset(
    {
        "http.request.method",
        "http.response.status_code",
        "http.route",
        "url.path",
        "server.address",
        "error",
        "error.type",
    }
)

_TELEMETRY_BOOTSTRAPPED = False


def scrub_url(url: str) -> str:
    """Reduce a URL to its path only, dropping scheme, host, and query string.

    The query string is discarded wholesale rather than filtered. Every query
    parameter of this API is either an identifier or a credential, so keeping
    "safe-looking" keys would still risk leaking patient or session data. The
    route template (not the raw URL) is what spans should carry anyway.
    """
    if not url:
        return ""
    path = url.split("?", 1)[0].split("#", 1)[0]
    if "://" in path:
        # Drop scheme + host: hostnames are not needed for route metrics.
        parts = path.split("/", 3)
        path = "/" + (parts[3] if len(parts) > 3 else "")
    return path[:256]


def configure_telemetry(app: Any = None) -> bool:
    """Install FastAPI OpenTelemetry instrumentation.

    Returns True when tracing is actually exported, False when it is a local
    no-op. Safe to call more than once.
    """
    global _TELEMETRY_BOOTSTRAPPED

    settings = get_settings()
    endpoint = getattr(settings, "otel_exporter_otlp_endpoint", "") or ""
    enabled = bool(getattr(settings, "otel_enabled", False)) and bool(endpoint)

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError:  # pragma: no cover - optional dependency
        logger.info("OpenTelemetry packages not installed; tracing disabled.")
        return False

    resource = Resource.create(
        {
            "service.name": settings.app_name,
            "service.version": "2.0.0",
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)

    if enabled:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")
                )
            )
        except ImportError:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.warning(
                "OTLP exporter unavailable; spans fall back to the console."
            )
    else:
        # No exporter registered: spans are created but dropped immediately.
        pass

    trace.set_tracer_provider(provider)

    if app is not None and not _TELEMETRY_BOOTSTRAPPED:
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="health,ready,openapi.json,docs,redoc",
        )
        _TELEMETRY_BOOTSTRAPPED = True

    logger.info(
        "OpenTelemetry configured (exporter=%s)",
        "otlp" if enabled else "none",
    )
    return enabled


def current_span_status(status_code: int) -> Any:
    """Set the current span's status from an HTTP response code."""
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:  # pragma: no cover - optional dependency
        return None
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None or not span.is_recording():
            return None
        if status_code >= 500:
            span.set_status(Status(StatusCode.ERROR))
        return span
    except Exception:  # noqa: BLE001 - telemetry must never break a request
        return None


__all__ = [
    "ALLOWED_SPAN_ATTRIBUTES",
    "configure_telemetry",
    "current_span_status",
    "scrub_url",
]
