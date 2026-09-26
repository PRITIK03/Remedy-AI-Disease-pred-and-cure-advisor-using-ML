"""Health and readiness endpoints.

- GET /health  → liveness (process up, model generation configured)
- GET /ready   → dependency checks (database, redis, ML model)
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.schemas.common import HealthResponse, ReadinessResponse, ServiceStatus

logger = get_logger("backend.health")
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_env=settings.app_env,
        model_version=settings.model_version,
    )


@router.get("/ready", response_model=ReadinessResponse, tags=["health"])
async def ready(request: Request) -> ReadinessResponse:
    services: dict[str, str] = {"database": "ok", "redis": "ok", "model": "ok"}

    # --- Model -------------------------------------------------------------- #
    model_service = getattr(request.app.state, "model_service", None)
    if model_service is None or not model_service.is_ready:
        services["model"] = "unavailable"

    # --- Database ----------------------------------------------------------- #
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        services["database"] = "unconfigured"
    else:
        try:
            session = session_factory()
            try:
                session.execute(text("SELECT 1"))
            finally:
                session.close()
        except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
            services["database"] = "unavailable"
            logger.warning("Readiness: database check failed: %s", exc)

    # --- Redis --------------------------------------------------------------- #
    redis_service = getattr(request.app.state, "redis_service", None)
    if redis_service is None or not await redis_service.ping():
        services["redis"] = "unavailable"

    # --- Storage (Phase 9) --------------------------------------------------- #
    # Report uploads must have a working destination, otherwise the ingestion
    # path fails at request time. Report the backend name, never credentials.
    services["storage"] = "ok"
    try:
        from backend.app.storage import get_storage_provider, storage_backend_name

        backend_name = storage_backend_name()
        if backend_name == "s3":
            provider = get_storage_provider()
            if not provider.exists(".remedy-healthcheck"):
                services["storage"] = "unavailable"
        else:
            get_storage_provider()
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        services["storage"] = "unavailable"
        logger.warning("Readiness: storage check failed: %s", type(exc).__name__)

    status = "ready" if all(v == "ok" for v in services.values()) else "not_ready"
    return ReadinessResponse(status=status, services=ServiceStatus(**services))
