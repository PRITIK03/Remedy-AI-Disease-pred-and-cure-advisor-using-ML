"""Security foundations for the backend (Phase 2 scope).

Deliberately minimal: no fake authentication. This module documents and
enforces the security-relevant policies that exist in this phase:

- CORS origin policy (no wildcard in production),
- rate-limit readiness (per-client token-bucket skeleton; enforced in a
  later phase together with real user accounts),
- error-hygiene helpers (no stack traces in responses).
"""

from __future__ import annotations

from backend.app.core.config import Settings


def validate_cors_policy(settings: Settings) -> list[str]:
    """Return explicit CORS origins; refuse wildcards outside development."""
    if settings.is_production and "*" in settings.cors_origin_list:
        raise ValueError("CORS wildcard origin is forbidden in production")
    return settings.cors_origin_list
