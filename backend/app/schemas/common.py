"""Shared API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable, non-sensitive message.")


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = Field(default=None, description="Correlation ID for log lookup.")


class ServiceStatus(BaseModel):
    database: str
    redis: str
    model: str
    storage: str = Field(
        default="ok",
        description="Report storage backend ('ok', 'unavailable' or 'unconfigured').",
    )


class ReadinessResponse(BaseModel):
    status: str = Field(description="'ready' or 'not_ready'.")
    services: ServiceStatus


class HealthResponse(BaseModel):
    status: str
    app_env: str
    model_version: str
