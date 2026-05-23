"""Supabase-backed cache — persists across lambda cold starts.

Uses the `cache_entries` table in Supabase.
Migration SQL is in scripts/migrations/002_cache_entries.sql.

Falls back silently to returning None on any error — the caller should
always have a regeneration path.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from core.providers.base import CacheProvider


class SupabaseCache(CacheProvider):
    """Persisted KV cache backed by Supabase PostgreSQL."""

    _TABLE = "cache_entries"

    def get(self, key: str) -> Any | None:
        try:
            from data.storage import supabase_db as sdb
            rows = sdb.select(
                self._TABLE,
                cols="value,expires_at",
                filters={"cache_key": key},
                limit=1,
            )
            if not rows:
                return None
            row = rows[0]
            expires_at_str = row.get("expires_at", "")
            if expires_at_str:
                expires_at = datetime.fromisoformat(
                    expires_at_str.replace("Z", "+00:00")
                )
                if datetime.now(timezone.utc) > expires_at:
                    self.delete(key)
                    return None
            raw = row.get("value")
            if isinstance(raw, str):
                return json.loads(raw)
            return raw
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        try:
            from data.storage import supabase_db as sdb
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            ).isoformat()
            sdb.upsert(
                self._TABLE,
                {
                    "cache_key":  key,
                    "value":      json.dumps(value),
                    "expires_at": expires_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="cache_key",
            )
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            from data.storage import supabase_db as sdb
            sdb.delete(self._TABLE, {"cache_key": key})
        except Exception:
            pass

    def clear(self) -> None:
        pass  # don't flush all prod cache keys by accident

    def name(self) -> str:
        return "supabase"
