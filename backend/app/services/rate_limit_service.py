"""Lightweight Redis fixed-window rate limiting (Phase 6).

Scope: sensitive auth endpoints only (register, login). Deliberately simple —
one INCR + EXPIRE per request; no distributed Lua/Sliding-window machinery.
Fail-closed: if Redis is unavailable, auth endpoints refuse rather than run
unlimited (see docs/auth-security.md).
"""

from __future__ import annotations

from redis.exceptions import RedisError

from backend.app.core.logging import get_logger

logger = get_logger("backend.rate_limit")


class RateLimitExceededError(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after = retry_after


class RateLimiter:
    def __init__(self, redis_service) -> None:
        self._redis = redis_service

    def _available(self) -> bool:
        return self._redis is not None and self._redis.is_ready

    async def check(
        self,
        *,
        bucket: str,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        """Raise RateLimitExceededError when the caller exceeds `limit`/window."""
        if not self._available():
            # Fail closed for auth endpoints.
            from backend.app.services.session_service import (
                SessionStoreUnavailableError,
            )

            raise SessionStoreUnavailableError("rate limiter unavailable")

        key = f"ratelimit:{bucket}:{identifier}:{int(window_seconds)}"
        try:
            redis = self._redis._redis
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
            ttl = await redis.ttl(key)
        except RedisError as exc:
            logger.error("Rate limit check failed: %s", type(exc).__name__)
            from backend.app.services.session_service import (
                SessionStoreUnavailableError,
            )

            raise SessionStoreUnavailableError("rate limiter error") from exc

        if count > limit:
            retry_after = max(ttl, 1) if ttl and ttl > 0 else window_seconds
            logger.warning(
                "Rate limit hit: bucket=%s window=%ss (no identifiers logged)",
                bucket,
                window_seconds,
            )
            raise RateLimitExceededError(retry_after)
