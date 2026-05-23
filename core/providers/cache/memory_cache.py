"""In-process memory cache (current default).

Thread-safe.  Data is lost on cold start (serverless limitation).
For persistence across lambda instances use the supabase or redis provider.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from core.providers.base import CacheProvider


class MemoryCache(CacheProvider):
    """Thread-safe TTL cache backed by a Python dict."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expiry, value = entry
            if time.monotonic() > expiry:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def name(self) -> str:
        return "memory"
