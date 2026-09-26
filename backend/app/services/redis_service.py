"""Redis service — health checking plus one justified lightweight cache.

Scope (Phase 2):
- health/readiness probing,
- short-lived cache of model metadata for the /ready endpoint (60s TTL),
  which reduces redundant DB/redis round-trips under readiness probes.

Explicitly NOT cached: individual patient assessments (privacy/consistency).
The async client is closed during application shutdown.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from backend.app.core.logging import get_logger

logger = get_logger("backend.redis_service")

MODEL_META_CACHE_KEY = "remedy:model_metadata"
MODEL_META_CACHE_TTL = 60


class RedisService:
    def __init__(self, redis_url: str) -> None:
        self._redis: aioredis.Redis | None = None
        self._url = redis_url

    async def connect(self) -> None:
        # Assign _redis ONLY after a successful ping: a half-open client must
        # never look "ready" (fail-closed posture for sessions/rate limits).
        client = aioredis.from_url(
            self._url, decode_responses=True, socket_connect_timeout=3
        )
        await client.ping()
        self._redis = client
        logger.info("Redis connected")

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            logger.info("Redis connection closed")

    @property
    def is_ready(self) -> bool:
        return self._redis is not None

    # ------------------------------------------------------------------ #
    # Health / cache
    # ------------------------------------------------------------------ #

    async def ping(self) -> bool:
        if self._redis is None:
            return False
        try:
            return bool(await self._redis.ping())
        except Exception:  # noqa: BLE001 - readiness must not raise
            return False

    async def get_model_metadata_cached(self, loader) -> dict[str, Any] | None:
        """Read-through cache for model metadata (60s TTL)."""
        if self._redis is None:
            return loader()
        try:
            raw = await self._redis.get(MODEL_META_CACHE_KEY)
            if raw:
                return json.loads(raw)
            value = loader()
            if value is not None:
                await self._redis.set(
                    MODEL_META_CACHE_KEY,
                    json.dumps(value, default=str),
                    ex=MODEL_META_CACHE_TTL,
                )
            return value
        except Exception as exc:  # noqa: BLE001 - cache must never break serving
            logger.warning("Model metadata cache degraded: %s", exc)
            return loader()

    async def invalidate_model_metadata(self) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(MODEL_META_CACHE_KEY)
        except Exception:  # noqa: BLE001
            pass
