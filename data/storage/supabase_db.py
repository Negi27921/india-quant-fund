"""Supabase data access layer — replaces DuckDB for cloud deployment."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import pandas as pd
from loguru import logger

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ohwgibzmaxfxivenbfhm.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


@lru_cache(maxsize=1)
def get_client():
    from supabase import create_client
    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_KEY not set")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Generic helpers ────────────────────────────────────────────────────────────

def select(table: str, cols: str = "*", filters: dict | None = None,
           order: str | None = None, limit: int | None = None) -> list[dict]:
    c = get_client()
    q = c.table(table).select(cols)
    for k, v in (filters or {}).items():
        q = q.eq(k, v)
    if order:
        desc = order.startswith("-")
        q = q.order(order.lstrip("-"), desc=desc)
    if limit:
        q = q.limit(limit)
    res = q.execute()
    return res.data or []


def select_df(table: str, cols: str = "*", filters: dict | None = None,
              order: str | None = None, limit: int | None = None) -> pd.DataFrame:
    rows = select(table, cols, filters, order, limit)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def insert(table: str, rows: list[dict] | dict) -> list[dict]:
    c = get_client()
    if isinstance(rows, dict):
        rows = [rows]
    res = c.table(table).insert(rows).execute()
    return res.data or []


def upsert(table: str, rows: list[dict] | dict, on_conflict: str = "id") -> list[dict]:
    c = get_client()
    if isinstance(rows, dict):
        rows = [rows]
    res = c.table(table).upsert(rows, on_conflict=on_conflict).execute()
    return res.data or []


def update(table: str, values: dict, filters: dict) -> list[dict]:
    c = get_client()
    q = c.table(table).update(values)
    for k, v in filters.items():
        q = q.eq(k, v)
    return q.execute().data or []


def delete(table: str, filters: dict) -> None:
    c = get_client()
    q = c.table(table).delete()
    for k, v in filters.items():
        q = q.eq(k, v)
    q.execute()


def delete_before(table: str, date_col: str, cutoff: str) -> int:
    """Delete rows where date_col < cutoff (ISO date string). Returns count."""
    c = get_client()
    res = c.table(table).delete().lt(date_col, cutoff).execute()
    deleted = len(res.data or [])
    logger.info(f"Deleted {deleted} rows from {table} before {cutoff}")
    return deleted
