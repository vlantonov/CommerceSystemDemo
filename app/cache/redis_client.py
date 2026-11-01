"""Redis client lifecycle helpers for optional cache-backed features."""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import get_settings

_redis_client: Redis | None = None
_active_redis_url: str | None = None


def get_redis_client() -> Redis | None:
    """Return a process-wide Redis client when caching is configured."""
    global _redis_client, _active_redis_url

    settings = get_settings()
    redis_url = settings.redis_url
    if not settings.category_subtree_cache_enabled or redis_url is None:
        return None

    if _redis_client is not None and _active_redis_url == redis_url:
        return _redis_client

    _redis_client = from_url(redis_url, decode_responses=True)
    _active_redis_url = redis_url
    return _redis_client


async def close_redis_client() -> None:
    """Close the cached Redis client during application shutdown."""
    global _redis_client, _active_redis_url

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        _active_redis_url = None

