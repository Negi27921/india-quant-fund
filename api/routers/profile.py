"""GET /profile/{symbol} — fully-hydrated Stock Profile object.

This is the single source of truth for every LLM agent in NEO.
Agents read from here; they do NOT call SI.ai or NSE directly.

Response is assembled from Supabase tables populated by the SI pipeline.
p95 target: <200ms (all data is pre-materialized, no external calls on request path).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from supabase import create_client
from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile", tags=["profile"])


def _sb():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def _safe(fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning("Profile query error: %s", e)
        return None


@router.get("/{symbol}")
async def get_stock_profile(symbol: str) -> dict:
    """Return the fully-hydrated Stock Profile for a given NSE/BSE ticker.

    The profile is assembled from pre-materialized Supabase tables.
    LLM agents, screeners, and the dashboard all consume this endpoint.
    """
    symbol = symbol.upper().strip()
    sb = _sb()

    # 1. Company master
    res = sb.table("dim_company").select("*").eq("ticker", symbol).limit(1).execute()
    if not res.data:
        # Try by NSE symbol
        res = sb.table("dim_company").select("*").eq("nse_symbol", symbol).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found in universe.")

    company = res.data[0]
    company_id = company["company_id"]

    # 2. Income statement (last 20 quarterly consolidated + standalone)
    is_res = _safe(
        lambda: sb.table("fact_income_statement")
        .select("statement_scope,reporting_type,fiscal_year,fiscal_quarter,period_end_date,financials,currency,scale,audit_status")
        .eq("company_id", company_id)
        .order("period_end_date", desc=True)
        .limit(40)
        .execute()
    )

    # 3. Balance sheet (last 20 quarterly)
    bs_res = _safe(
        lambda: sb.table("fact_balance_sheet")
        .select("statement_scope,fiscal_year,fiscal_quarter,period_end_date,financials,currency,scale")
        .eq("company_id", company_id)
        .order("period_end_date", desc=True)
        .limit(40)
        .execute()
    )

    # 4. Cash flow (last 20 quarterly)
    cf_res = _safe(
        lambda: sb.table("fact_cash_flow")
        .select("statement_scope,reporting_type,fiscal_year,fiscal_quarter,period_end_date,financials,currency,scale")
        .eq("company_id", company_id)
        .order("period_end_date", desc=True)
        .limit(40)
        .execute()
    )

    # 5. Upcoming results calendar
    cal_res = _safe(
        lambda: sb.table("fact_results_calendar")
        .select("result_date,fiscal_year,fiscal_quarter,result_type")
        .eq("ticker", symbol)
        .order("result_date", desc=False)
        .limit(4)
        .execute()
    )

    # 6. Recent filings (transcripts, annual reports)
    filings_res = _safe(
        lambda: sb.table("fact_filings")
        .select("filing_id,document_type,fiscal_year,fiscal_quarter,published_date,pdf_link,html_link")
        .eq("ticker", symbol)
        .order("published_date", desc=True)
        .limit(20)
        .execute()
    )

    # 7. Recent tagged announcements (last 60 days)
    ann_res = _safe(
        lambda: sb.table("fact_announcements_tagged")
        .select("announcement_id,announcement_type,sentiment,summary_header,summary_text,published_date,source_link")
        .eq("ticker", symbol)
        .order("published_date", desc=True)
        .limit(50)
        .execute()
    )

    # 8. Sentiment trend (last 60 announcements)
    sentiment_trend: dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
    for ann in (ann_res.data if ann_res else []):
        s = ann.get("sentiment") or "neutral"
        sentiment_trend[s] = sentiment_trend.get(s, 0) + 1

    # Assemble profile
    profile: dict[str, Any] = {
        "identifiers": {
            "company_id":        company_id,
            "ticker":            company["ticker"],
            "isin":              company.get("isin"),
            "nse_symbol":        company.get("nse_symbol"),
            "bse_scrip_code":    company.get("bse_scrip_code"),
            "company_name":      company["company_name"],
            "sector":            company.get("sector"),
            "industry":          company.get("industry"),
            "marketcap_category": company.get("marketcap_category"),
        },
        "market": {
            "current_price_inr":  company.get("current_price_inr"),
            "market_cap_inr_cr":  company.get("market_cap_inr_cr"),
            "high_52w_inr":       company.get("high_52w_inr"),
            "low_52w_inr":        company.get("low_52w_inr"),
            "prices_as_of":       company.get("prices_as_of"),
        },
        "fundamentals": {
            "income_statement": is_res.data if is_res else [],
            "balance_sheet":    bs_res.data if bs_res else [],
            "cash_flow":        cf_res.data if cf_res else [],
        },
        "events": {
            "upcoming_results": cal_res.data if cal_res else [],
        },
        "filings": filings_res.data if filings_res else [],
        "announcements": ann_res.data if ann_res else [],
        "ai_layer": {
            "sentiment_trend": sentiment_trend,
        },
        "meta": {
            "primary_source":    settings.DATA_PRIMARY_SOURCE,
            "trial_expires_at":  settings.TRIAL_EXPIRES_AT,
            "last_refreshed_ts": company.get("updated_at"),
        },
    }

    return profile


@router.get("/{symbol}/announcements")
async def get_announcements(symbol: str, limit: int = 50) -> list[dict]:
    """Return recent AI-tagged announcements for a symbol."""
    symbol = symbol.upper().strip()
    sb = _sb()
    res = sb.table("fact_announcements_tagged") \
        .select("*") \
        .eq("ticker", symbol) \
        .order("published_date", desc=True) \
        .limit(min(limit, 200)) \
        .execute()
    return res.data or []


@router.get("/{symbol}/filings")
async def get_filings(symbol: str, doc_type: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Return filings for a symbol, optionally filtered by document_type."""
    symbol = symbol.upper().strip()
    sb = _sb()
    q = sb.table("fact_filings") \
        .select("*") \
        .eq("ticker", symbol) \
        .order("published_date", desc=True) \
        .limit(min(limit, 100))
    if doc_type:
        q = q.eq("document_type", doc_type)
    return (q.execute().data) or []
