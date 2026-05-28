"""
Earnings Results API
====================
Serves quarterly earnings data extracted from @earnings_pulse Telegram
channel (Gemini Flash OCR) and stored in the earnings_results Supabase table.
"""

from __future__ import annotations

import os
import urllib.parse as _up
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_SB_URL = os.environ.get("SUPABASE_URL", "")
_SB_KEY = os.environ.get("SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_ANON_KEY", ""))
_SB_HDR = {
    "apikey": _SB_KEY,
    "Authorization": f"Bearer {_SB_KEY}",
    "Accept": "application/json",
}

_ALL_COLS = (
    "id,ticker,company,sector,quarter,period_end,"
    "sales_cr,sales_prev_q_cr,sales_prev_y_cr,sales_qoq_pct,sales_yoy_pct,"
    "other_income_cr,"
    "op_cr,op_prev_q_cr,op_prev_y_cr,op_qoq_pct,op_yoy_pct,"
    "opm_pct,opm_prev_q_pct,opm_prev_y_pct,opm_qoq_bps,opm_yoy_bps,"
    "pat_cr,pat_prev_q_cr,pat_prev_y_cr,pat_qoq_pct,pat_yoy_pct,"
    "eps,eps_prev_q,eps_prev_y,eps_qoq_pct,eps_yoy_pct,"
    "cmp,pe_ratio,market_cap_cr,"
    "pulse_rating,confidence_score,source,filed_at,created_at"
)


async def _sb_get(path: str) -> list[dict]:
    url = f"{_SB_URL}/rest/v1/{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_SB_HDR)
    if r.status_code == 200:
        return r.json()
    raise HTTPException(502, f"Supabase error {r.status_code}: {r.text[:200]}")


@router.get("/latest")
async def get_latest_earnings(
    limit: int = Query(20, ge=1, le=100),
    quarter: Optional[str] = Query(None, description="e.g. Q4FY26"),
    rating: Optional[str] = Query(None, description="Great|Good|Mixed|Poor"),
    sector: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="ticker or company name"),
):
    """Latest earnings results, newest first."""
    filters = [f"select={_ALL_COLS}", "order=filed_at.desc.nullslast", f"limit={limit}"]

    if quarter:
        filters.append(f"quarter=eq.{_up.quote(quarter, safe='')}")
    if rating:
        filters.append(f"pulse_rating=eq.{_up.quote(rating, safe='')}")
    if sector:
        filters.append(f"sector=ilike.%25{_up.quote(sector, safe='')}%25")
    if search:
        s = _up.quote(search.strip().upper(), safe="")
        filters.append(f"or=(ticker.ilike.{s}%25,company.ilike.%25{_up.quote(search.strip(), safe='')}%25)")

    return await _sb_get("earnings_results?" + "&".join(filters))


@router.get("/ticker/{ticker}")
async def get_ticker_earnings(ticker: str, limit: int = Query(8, ge=1, le=20)):
    """Earnings history for a specific ticker, newest first."""
    rows = await _sb_get(
        f"earnings_results?ticker=eq.{ticker.upper()}"
        f"&select={_ALL_COLS}&order=filed_at.desc&limit={limit}"
    )
    if not rows:
        raise HTTPException(404, f"No earnings data for {ticker}")
    return rows


@router.get("/stats")
async def get_earnings_stats():
    """Summary stats: total count, breakdown by rating, latest quarter."""
    rows = await _sb_get(
        "earnings_results?select=pulse_rating,quarter,filed_at"
        "&order=filed_at.desc&limit=1000"
    )
    by_rating: dict[str, int] = {}
    quarters: dict[str, int] = {}
    for row in rows:
        r = row.get("pulse_rating") or "Unknown"
        q = row.get("quarter") or "Unknown"
        by_rating[r] = by_rating.get(r, 0) + 1
        quarters[q]  = quarters.get(q, 0) + 1

    return {
        "total": len(rows),
        "by_rating": by_rating,
        "by_quarter": quarters,
        "latest_quarter": rows[0]["quarter"] if rows else None,
        "latest_filed": rows[0]["filed_at"] if rows else None,
    }


@router.get("/quarters")
async def list_quarters():
    """All distinct quarters available in the database."""
    rows = await _sb_get(
        "earnings_results?select=quarter&order=quarter.desc"
    )
    seen: set[str] = set()
    result = []
    for row in rows:
        q = row.get("quarter")
        if q and q not in seen:
            seen.add(q)
            result.append(q)
    return result
