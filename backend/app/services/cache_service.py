from __future__ import annotations

import json
import logging
from typing import Any

from app.config import (
    REDIS_DEFAULT_TTL_SECONDS,
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
    REDIS_URL,
)

try:
    import redis
except ImportError:  # pragma: no cover - graceful degradation when the dependency is not installed
    redis = None


logger = logging.getLogger(__name__)
_redis_client: Any | None = None
_redis_unavailable_logged = False


def _build_key(key: str) -> str:
    """Add a consistent prefix to the cache key to avoid collisions between different projects."""
    return f"{REDIS_KEY_PREFIX}:{key}"


def _get_redis_client():
    """Lazily load the Redis client; return None if unavailable."""
    global _redis_client
    global _redis_unavailable_logged

    if not REDIS_ENABLED:
        return None
    if redis is None:
        if not _redis_unavailable_logged:
            logger.warning("Redis is enabled, but the redis dependency is not installed in this environment; caching will be skipped.")
            _redis_unavailable_logged = True
        return None
    if _redis_client is not None:
        return _redis_client

    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as exc:  # pragma: no cover - graceful degradation on connection issues
        if not _redis_unavailable_logged:
            logger.warning("Failed to connect to Redis; caching will be skipped: %s", exc)
            _redis_unavailable_logged = True
        return None


def get_cached_json(key: str) -> Any | None:
    """Read a JSON cache entry; return None on a cache miss or when Redis is unavailable."""
    client = _get_redis_client()
    if client is None:
        return None

    try:
        raw_value = client.get(_build_key(key))
        if raw_value is None:
            return None
        return json.loads(raw_value)
    except Exception as exc:  # pragma: no cover - cache failures should not affect the main flow
        logger.debug("Failed to read Redis cache: %s", exc)
        return None


def set_cached_json(
    key: str,
    value: Any,
    expire_seconds: int | None = None,
) -> None:
    """Write a JSON cache entry; skip directly if Redis is unavailable."""
    client = _get_redis_client()
    if client is None:
        return

    ttl = expire_seconds or REDIS_DEFAULT_TTL_SECONDS
    try:
        client.set(_build_key(key), json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as exc:  # pragma: no cover - cache failures should not affect the main flow
        logger.debug("Failed to write Redis cache: %s", exc)
