"""Session service — Redis-backed server-side sessions (Phase 6).

Fail-closed policy: if Redis is unavailable, session-DEPENDENT operations
(login, session lookup, logout) raise SessionStoreUnavailableError — the API
never silently degrades to an insecure state (e.g. accepting un-validated
sessions or falling back to signed client-side tokens). Endpoints that need
no session (health, readiness) are unaffected.

Storage: Redis key ``session:{sha256(session_id)}`` → JSON
``{user_id, created_at, expires_at}``. Only the opaque id is client-visible
(HttpOnly cookie); Redis stores the id's SHA-256, never the raw cookie value.

Expiry is enforced by the Redis TTL itself (the key disappears), so an
expired session is indistinguishable from a non-existent one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError

from backend.app.core.logging import get_logger
from backend.app.core.security import generate_session_id, hash_session_id

logger = get_logger("backend.session_service")

_SESSION_KEY_PREFIX = "session:"


class SessionStoreUnavailableError(RuntimeError):
    """Redis is unreachable — session-dependent auth must fail CLOSED."""


def _now() -> datetime:
    return datetime.now(UTC)


class SessionService:
    """Server-side session store backed by the shared Redis service."""

    def __init__(self, redis_service, ttl_seconds: int) -> None:
        self._redis = redis_service
        self._ttl = ttl_seconds

    @property
    def is_available(self) -> bool:
        return self._redis is not None and self._redis.is_ready

    def _key(self, session_id: str) -> str:
        return _SESSION_KEY_PREFIX + hash_session_id(session_id)

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #

    async def create(self, user_id: str) -> tuple[str, datetime]:
        """Create a session; return (session_id, expires_at)."""
        if not self.is_available:
            raise SessionStoreUnavailableError("session store unavailable")
        session_id = generate_session_id()
        created = _now()
        expires = created + timedelta(seconds=self._ttl)
        record = {
            "user_id": str(user_id),
            "created_at": created.isoformat(),
            "expires_at": expires.isoformat(),
        }
        try:
            await self._redis._redis.set(
                self._key(session_id),
                json.dumps(record),
                ex=self._ttl,
            )
        except RedisError as exc:
            logger.error("Session create failed: %s", type(exc).__name__)
            raise SessionStoreUnavailableError("session store write failed") from exc
        return session_id, expires

    async def get(self, session_id: str) -> dict | None:
        """Return the session record, or None if missing/expired/invalid."""
        if not session_id or not self.is_available:
            if not self.is_available:
                raise SessionStoreUnavailableError("session store unavailable")
            return None
        try:
            raw = await self._redis._redis.get(self._key(session_id))
        except RedisError as exc:
            logger.error("Session read failed: %s", type(exc).__name__)
            raise SessionStoreUnavailableError("session store read failed") from exc
        if not raw:
            return None
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            # Corrupt entry — treat as invalid, never crash a request.
            await self.delete_quiet(session_id)
            return None
        if not isinstance(record, dict) or "user_id" not in record:
            return None
        return record

    async def delete(self, session_id: str) -> None:
        """Invalidate a session server-side (logout)."""
        if not self.is_available:
            raise SessionStoreUnavailableError("session store unavailable")
        try:
            await self._redis._redis.delete(self._key(session_id))
        except RedisError as exc:
            logger.error("Session delete failed: %s", type(exc).__name__)
            raise SessionStoreUnavailableError("session store delete failed") from exc

    async def delete_quiet(self, session_id: str) -> None:
        """Best-effort delete used for cleanup paths (never raises)."""
        if not self.is_available or not session_id:
            return
        try:
            await self._redis._redis.delete(self._key(session_id))
        except RedisError:  # noqa: BLE001
            pass

    async def touch(self, session_id: str) -> None:
        """Sliding expiration on activity (optional; keeps TTL policy in one place)."""
        if not self.is_available or not session_id:
            return
        try:
            await self._redis._redis.expire(self._key(session_id), self._ttl)
        except RedisError:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Cookie helpers
# --------------------------------------------------------------------------- #


def session_cookie_kwargs(settings) -> dict:
    """Cookie attributes for the session cookie (never readable by JS)."""
    return {
        "key": settings.session_cookie_name_resolved,
        "max_age": settings.session_ttl_seconds,
        "path": "/",
        "domain": settings.cookie_domain or None,
        "secure": settings.cookie_secure,
        "httponly": True,
        "samesite": "lax",
    }


def csrf_cookie_kwargs(settings) -> dict:
    """Cookie attributes for the CSRF token (JS-readable by design)."""
    return {
        "key": settings.csrf_cookie_name,
        "max_age": settings.session_ttl_seconds,
        "path": "/",
        "domain": settings.cookie_domain or None,
        "secure": settings.cookie_secure,
        "httponly": False,
        "samesite": "lax",
    }
