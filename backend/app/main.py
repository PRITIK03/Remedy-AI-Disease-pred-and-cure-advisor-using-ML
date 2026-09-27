"""Remedy-AI FastAPI application (Phase 2 backend).

Architecture:
    FastAPI → API v1 routers → Pydantic schemas → services
            → ml.inference.predictor (Phase 1 artifact, loaded once)
            → SQLAlchemy 2.0 → PostgreSQL
            → Redis (health + short-lived metadata cache)

The old Flask app (app.py) remains functional for regression compatibility;
this API is the future primary backend. No ML behavior is changed here.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.router import api_v1_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.schemas.common import ErrorResponse
from backend.app.services.model_service import ModelService
from backend.app.services.redis_service import RedisService

logger = get_logger("backend.main")

DESCRIPTION = """
Educational **cardiovascular risk assessment API** built around a calibrated
scikit-learn pipeline (Phase 1 `ml` package).

⚠ **The outputs are model estimates from an educational prototype — not
medical diagnoses and not clinically validated risk scores.**
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load shared resources once; close them on shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting Remedy-AI API (env=%s)", settings.app_env)

    # --- ML predictor (loaded ONCE, reused across requests) ----------------- #
    app.state.model_service = ModelService()
    try:
        app.state.model_service.load(settings.models_dir or None)
    except Exception as exc:  # noqa: BLE001 - API must boot to report readiness
        logger.error("Model failed to load at startup: %s", exc)

    # --- Redis --------------------------------------------------------------- #
    app.state.redis_service = RedisService(settings.redis_url)
    try:
        await app.state.redis_service.connect()
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis failed to connect at startup: %s", exc)

    # --- Database ------------------------------------------------------------ #
    app.state.db_engine = None
    app.state.session_factory = None
    try:
        from backend.app.db.session import create_db_engine, create_session_factory

        app.state.db_engine = create_db_engine()
        app.state.session_factory = create_session_factory(app.state.db_engine)
        logger.info("Database engine created")
    except Exception as exc:  # noqa: BLE001
        logger.error("Database engine creation failed: %s", exc)

    yield

    # --- Shutdown ------------------------------------------------------------ #
    if app.state.redis_service is not None:
        await app.state.redis_service.close()
    if app.state.db_engine is not None:
        app.state.db_engine.dispose()
    from backend.app.agents.graph import close_checkpointer

    close_checkpointer()
    logger.info("Remedy-AI API shut down cleanly")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # --- CORS (configuration-driven; wildcard refused in production) -------- #
    # Credentials are required for cookie auth: explicit origins only, and
    # enough methods/headers for the authenticated API (incl. CSRF header).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", settings.csrf_header_name],
        expose_headers=["X-Request-ID"],
    )

    # --- Request ID + access logging middleware ------------------------------ #
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        import time

        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        model_service = getattr(request.app.state, "model_service", None)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "model_version": (
                    model_service.model_version
                    if model_service and model_service.is_ready
                    else None
                ),
            },
        )
        response.headers["X-Request-ID"] = request_id

        # --- Telemetry status (Phase 9) ------------------------------------- #
        # Low-cardinality operational signal only: HTTP status class.
        from backend.app.telemetry import current_span_status

        current_span_status(response.status_code)

        # --- Security headers (Phase 6) ------------------------------------ #
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age_seconds}; includeSubDomains",
            )

        # --- Cache-control for sensitive/authenticated responses ------------ #
        # Never let browsers or shared caches persist personalized data.
        if request.url.path.startswith("/api/v1/"):
            response.headers.setdefault("Cache-Control", "no-store")

        return response

    # --- Production config guard ------------------------------------------------ #
    # Refuse to serve production traffic with an insecure setup.
    if settings.is_production:
        from backend.app.core.security import _csrf_secret  # noqa: F401

        _csrf_secret(settings)  # raises if SECRET_KEY missing in production
        if not settings.cookie_secure:
            raise RuntimeError(
                "COOKIE_SECURE must be true when APP_ENV=production"
            )

    # --- OpenTelemetry (Phase 9) ---------------------------------------------- #
    # Operational request telemetry only; no medical or user data is ever
    # attached to spans. No-op unless OTEL_ENABLED + an OTLP endpoint are set.
    from backend.app.telemetry import configure_telemetry

    configure_telemetry(app)

    # --- Non-fatal capability warnings (logged, never printed) --------------- #
    for warning in settings.validate_runtime_services():
        logger.warning("startup: %s", warning)

    # --- Routers -------------------------------------------------------------- #
    # Health/readiness at the ROOT (operational endpoints, not business APIs).
    app.include_router(health_router)
    # Business APIs under /api/v1.
    app.include_router(api_v1_router)

    # --- Exception handling ---------------------------------------------------- #
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled exception",
            extra={"request_id": getattr(request.state, "request_id", None)},
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error={"code": "internal_error",
                       "message": "An unexpected error occurred."},
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )

    return app


app = create_app()
