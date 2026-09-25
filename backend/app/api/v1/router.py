"""API v1 router — all business endpoints live under /api/v1.

Health/readiness live at the ROOT (/health, /ready) — they are operational
endpoints, not business APIs — and are mounted directly in main.py.

Note: the version prefix is applied here at include time; FastAPI 0.141+
materializes lazy sub-routers reliably when a prefix is present on
include_router.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1 import assessments

api_v1_router = APIRouter()
api_v1_router.include_router(assessments.router, prefix="/api/v1")
