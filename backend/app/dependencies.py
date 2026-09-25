"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from backend.app.services.model_service import ModelService
from backend.app.services.redis_service import RedisService


def get_model_service(request: Request) -> ModelService:
    service: ModelService | None = getattr(request.app.state, "model_service", None)
    if service is None or not service.is_ready:
        from backend.app.services.model_service import ModelUnavailableError

        raise ModelUnavailableError("ML model is not available")
    return service


def get_redis_service(request: Request) -> RedisService | None:
    return getattr(request.app.state, "redis_service", None)


def get_db_session(request: Request) -> Iterator[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        from backend.app.services.model_service import ModelUnavailableError

        raise ModelUnavailableError("Database is not configured")
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


ModelServiceDep = Annotated[ModelService, Depends(get_model_service)]
RedisServiceDep = Annotated[RedisService | None, Depends(get_redis_service)]
DbSessionDep = Annotated[Session, Depends(get_db_session)]
