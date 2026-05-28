"""Canonical stock universe — single source of truth for all modules.

All screener, breadth, watchlist, and portfolio queries read from this module.
Universe = dim_company WHERE market_cap_inr_cr >= UNIVERSE_MIN_MCAP_CR.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request as _ur
from typing import Any

UNIVERSE_MIN_MCAP_CR: int = 1000  # ← single config constant

_SB_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_SB_KEY = os.getenv("SUPABASE_KEY", "").strip()

_CACHE_TTL = 3600  # 1 hour
_UNIVERSE_CACHE: tuple[float, list[dict]] = (0.0, [])


def _sb_headers() -> dict[str, str]:
    return {
        "apikey":        _SB_KEY,
        "Authorization": f"Bearer {_SB_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "count=none",
    }


def get_canonical_universe(force_refresh: bool = False) -> list[dict]:
    """Return all companies with market_cap_inr_cr >= UNIVERSE_MIN_MCAP_CR.

    Cached for 1 hour. Returns list of dicts with keys:
      ticker, company_name, sector, industry, market_cap_inr_cr, current_price_inr
    """
    global _UNIVERSE_CACHE
    ts, rows = _UNIVERSE_CACHE
    if not force_refresh and rows and time.monotonic() - ts < _CACHE_TTL:
        return rows

    if not (_SB_URL and _SB_KEY):
        return []

    all_rows: list[dict] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            headers = {
                **_sb_headers(),
                "Range-Unit": "items",
                "Range":      f"{offset}-{offset + page_size - 1}",
            }
            url = (
                f"{_SB_URL}/rest/v1/dim_company"
                f"?select=ticker,company_name,sector,industry,market_cap_inr_cr,current_price_inr"
                f"&market_cap_inr_cr=gte.{UNIVERSE_MIN_MCAP_CR}"
                f"&ticker=not.is.null"
                f"&order=market_cap_inr_cr.desc.nullslast"
            )
            req = _ur.Request(url, headers=headers)
            with _ur.urlopen(req, timeout=15) as r:
                batch = json.loads(r.read())
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
    except Exception:
        return rows or []

    _UNIVERSE_CACHE = (time.monotonic(), all_rows)
    return all_rows


def get_canonical_tickers_ns() -> list[str]:
    """Return canonical universe as .NS-suffixed tickers for yfinance calls."""
    rows = get_canonical_universe()
    return [
        (r["ticker"] if r["ticker"].endswith(".NS") else f"{r['ticker']}.NS")
        for r in rows
        if r.get("ticker")
    ]


def get_canonical_ticker_set() -> set[str]:
    """Return bare ticker symbols (no exchange suffix) for O(1) membership tests."""
    rows = get_canonical_universe()
    return {
        r["ticker"].replace(".NS", "").replace(".BO", "")
        for r in rows
        if r.get("ticker")
    }


def get_universe_size() -> int:
    """Return count of stocks in canonical universe (cached)."""
    return len(get_canonical_universe())
