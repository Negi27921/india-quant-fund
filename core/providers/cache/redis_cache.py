"""Redis / Upstash cache provider — enables cross-instance rate limiting and caching.

Activate with:
  CACHE_PROVIDER=redis
  REDIS_URL=redis://localhost:6379/0      (local)
  UPSTASH_REDIS_URL=rediss://...          (Upstash — preferred for Vercel)
  UPSTASH_REDIS_TOKEN=...

Falls back to MemoryCache if Redis is not reachable.
"""
from __future__ import annotations

from typing import Any

from core.providers.base import CacheProvider


class RedisCache(CacheProvider):
    """Redis-backed cache — works with standard Redis or Upstash (HTTP mode)."""

    def __init__(self) -> None:
        self._client = None
        self._init()

    def _init(self) -> None:
        from core.config import settings
        url = settings.redis_url
        if not url:
            return
        try:
            if "upstash" in url:
                # Upstash supports standard redis protocol via rediss://
                import redis
                self._client = redis.from_url(url, decode_responses=True)
            else:
                import redis
                self._client = redis.from_url(url, decode_responses=True)
            self._client.ping()
        except Exception:
            self._client = None

    def _ok(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> Any | None:
        if not self._ok():
            return None
        try:
            import json
            val = self._client.get(key)  # type: ignore[union-attr]
            return json.loads(val) if val is not None else None
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        if not self._ok():
            return
        try:
            import json
            self._client.setex(key, ttl_seconds, json.dumps(value))  # type: ignore[union-attr]
        except Exception:
            pass

    def delete(self, key: str) -> None:
        if not self._ok():
            return
        try:
            self._client.delete(key)  # type: ignore[union-attr]
        except Exception:
            pass

    def clear(self) -> None:
        pass  # don't flush entire Redis keyspace

    def is_connected(self) -> bool:
        return self._ok()

    def name(self) -> str:
        return "redis"
