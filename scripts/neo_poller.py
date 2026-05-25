#!/usr/bin/env python3
"""NEO Master Poller — single process, all data streams.

Streams running concurrently:
  1. Announcements    — SI.ai tagged feed,       every 60s
  2. Filings          — SI.ai filings feed,       every 60s
  3. Fundamentals     — SI.ai income/BS/CF,       triggered on new results + slow backfill
  4. Results Calendar — SI.ai calendar,           every 60 min
  5. Technicals       — yFinance OHLCV+indicators, daily 15:40 IST + on-demand
  6. Bulk/Block Deals — NSE API,                  every 15 min during market hours

Usage (from india-quant-fund/):
    python3 scripts/neo_poller.py

Run persistently on Railway, Fly.io, or nohup locally.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone
from typing import Any, Union

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import httpx
import pandas as pd
import yfinance as yf
from supabase import create_client

from core.config import settings
from core.providers.stockinsights import get_si_client
from core.providers.stockinsights.client import SIFatalError

_SI_QUOTA_EXHAUSTED = False  # set True on 429; suppresses repeated SI.ai calls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("neo_poller")

_THREAD_POOL = ThreadPoolExecutor(max_workers=8)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sb():
    key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
    return create_client(settings.SUPABASE_URL, key)


def _iso(dt) -> Union[str, None]:
    if dt is None:
        return None
    if isinstance(dt, (date, datetime)):
        return dt.isoformat()
    return str(dt)


def _int_safe(v) -> Union[int, None]:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip().upper().lstrip("Q")
    if not s or s.lower() in ("null", "none"):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _log_job(sb, name: str, rows_in: int, rows_out: int, status: str, error: str = "") -> None:
    try:
        sb.table("job_run").insert({
            "job_name": name,
            "end_ts":   datetime.now(timezone.utc).isoformat(),
            "rows_in":  rows_in,
            "rows_out": rows_out,
            "status":   status,
            "error":    error[:500] if error else None,
        }).execute()
    except Exception as e:
        logger.warning("job_run insert failed: %s", e)


def _is_market_hours() -> bool:
    """True if current IST time is between 09:00 and 15:35 on a weekday."""
    now_utc = datetime.now(timezone.utc)
    # IST = UTC+5:30
    ist_hour = (now_utc.hour + 5) % 24
    ist_min  = (now_utc.minute + 30) % 60
    if ist_hour == (now_utc.hour + 5) % 24 and now_utc.minute + 30 >= 60:
        ist_hour = (ist_hour + 1) % 24
    weekday = now_utc.weekday()  # 0=Mon, 6=Sun
    if weekday >= 5:
        return False
    return (9, 0) <= (ist_hour, ist_min) <= (15, 35)


def _after_market_close() -> bool:
    """True if IST time is between 15:40 and 23:59 on a weekday."""
    now_utc = datetime.now(timezone.utc)
    ist_hour = (now_utc.hour + 5) % 24
    ist_min  = (now_utc.minute + 30) % 60
    if now_utc.minute + 30 >= 60:
        ist_hour = (ist_hour + 1) % 24
    weekday = now_utc.weekday()
    if weekday >= 5:
        return False
    return (ist_hour, ist_min) >= (15, 40)


# ---------------------------------------------------------------------------
# Stream 1 & 2: Announcements + Filings  (60s)
# ---------------------------------------------------------------------------

async def _upsert_announcements(si, sb, seen: set) -> int:
    global _SI_QUOTA_EXHAUSTED
    if _SI_QUOTA_EXHAUSTED:
        return 0
    try:
        items, _ = await si.get_announcements(limit=100)
    except SIFatalError as e:
        if "rate_limited" in str(e) or "429" in str(e):
            _SI_QUOTA_EXHAUSTED = True
            logger.critical("[ann] SI.ai quota exhausted — suppressing SI calls. Upgrade plan at stockinsights.ai")
        else:
            logger.error("[ann] fetch error: %s", e)
        return 0
    except Exception as e:
        logger.error("[ann] fetch error: %s", e)
        return 0

    new = [a for a in items if a.id not in seen]
    if not new:
        return 0

    rows = []
    for a in new:
        ai = a.ai_insights
        rows.append({
            "announcement_id":      a.id,
            "company_id":           a.company_id,
            "ticker":               a.ticker,
            "company_name":         a.company_name,
            "announcement_type_id": ai.announcement_type_id if ai else None,
            "announcement_type":    ai.announcement_type    if ai else None,
            "sentiment":            ai.sentiment             if ai else None,
            "summary_header":       ai.summary_header        if ai else None,
            "summary_text":         ai.summary_text          if ai else None,
            "source_link":          a.source_link,
            "published_date":       _iso(a.published_date),
            "exchange_tickers":     json.dumps([
                e.model_dump() if hasattr(e, "model_dump") else e
                for e in (a.exchange_tickers or [])
            ]),
            "source":    "stockinsights",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    try:
        sb.table("fact_announcements_tagged").upsert(rows, on_conflict="announcement_id").execute()
        for a in new:
            seen.add(a.id)
        logger.info("[ann] +%d new (total seen: %d)", len(new), len(seen))
    except Exception as e:
        logger.error("[ann] upsert error: %s", e)
        return 0
    return len(new)


async def _upsert_filings(si, sb, seen: set, fundamentals_queue: asyncio.Queue) -> int:
    global _SI_QUOTA_EXHAUSTED
    if _SI_QUOTA_EXHAUSTED:
        return 0
    DOC_TYPES = ("earnings-transcript", "annual-report", "quarterly-result", "investor-presentation")
    new_total = 0
    for doc_type in DOC_TYPES:
        try:
            docs, _ = await si.get_filings_feed(document_type=doc_type, limit=50)
        except SIFatalError as e:
            if "rate_limited" in str(e) or "429" in str(e):
                _SI_QUOTA_EXHAUSTED = True
                logger.critical("[filings] SI.ai quota exhausted. Upgrade at stockinsights.ai")
                break
            logger.error("[filings/%s] fetch error: %s", doc_type, e)
            continue
        except Exception as e:
            logger.error("[filings/%s] fetch error: %s", doc_type, e)
            continue

        new = [d for d in docs if d.id not in seen]
        if not new:
            continue

        rows = [{
            "filing_id":        d.id,
            "company_id":       d.company_id,
            "ticker":           d.ticker,
            "company_name":     d.company_name,
            "document_type":    d.type or doc_type,
            "fiscal_year":      _int_safe(d.year),
            "fiscal_quarter":   _int_safe(d.quarter),
            "published_date":   _iso(d.published_date),
            "pdf_link":         d.pdf_link,
            "html_link":        d.html_link,
            "exchange_tickers": json.dumps(d.exchange_tickers or []),
            "source":           "stockinsights",
            "fetched_at":       datetime.now(timezone.utc).isoformat(),
        } for d in new]

        try:
            sb.table("fact_filings").upsert(rows, on_conflict="filing_id").execute()
            for d in new:
                seen.add(d.id)
                # Trigger fundamentals fetch for new quarterly results
                if doc_type == "quarterly-result" and d.ticker:
                    try:
                        fundamentals_queue.put_nowait(d.ticker)
                        logger.info("[filings] queued fundamentals for %s", d.ticker)
                    except asyncio.QueueFull:
                        pass
            new_total += len(new)
            logger.info("[filings/%s] +%d new", doc_type, len(new))
        except Exception as e:
            logger.error("[filings/%s] upsert error: %s", doc_type, e)

    return new_total


# ---------------------------------------------------------------------------
# Stream 3: Fundamentals  (triggered + slow backfill at 1 company/8s)
# ---------------------------------------------------------------------------

async def _fetch_and_store_fundamentals(si, sb, ticker: str) -> int:
    """Fetch income statement + balance sheet + cash flow for one ticker."""
    stored = 0
    # Find company_id
    try:
        cr = sb.table("dim_company").select("company_id").eq("ticker", ticker).limit(1).execute()
        company_id = cr.data[0]["company_id"] if cr.data else None
    except Exception:
        company_id = None

    for scope in ("consolidated", "standalone"):
        for period_type in ("quarterly",):
            # Get results calendar to know which periods to fetch
            try:
                cal, _ = await si.get_results_calendar(ticker=ticker, limit=8)
            except Exception as e:
                logger.warning("[fund/%s] calendar error: %s", ticker, e)
                cal = []

            for entry in cal[:4]:  # last 4 quarters
                period_str = _iso(entry.result_date)
                if not period_str:
                    continue
                # Income statement
                try:
                    is_data = await si.get_income_statement(
                        ticker=ticker,
                        period_end_date=period_str,
                        reporting_type=period_type,
                        statement_scope=scope,
                    )
                    if is_data and is_data.financials:
                        sb.table("fact_income_statement").upsert({
                            "company_id":     company_id or is_data.company_id,
                            "ticker":         ticker,
                            "statement_scope": scope,
                            "reporting_type": period_type,
                            "fiscal_year":    is_data.fiscal_year,
                            "fiscal_quarter": is_data.fiscal_quarter,
                            "period_end_date": _iso(is_data.period_end_date),
                            "audit_status":   is_data.audit_status,
                            "currency":       is_data.currency,
                            "scale":          is_data.scale,
                            "financials":     json.dumps(is_data.financials),
                            "source":         "stockinsights",
                            "fetched_at":     datetime.now(timezone.utc).isoformat(),
                        }, on_conflict="company_id,statement_scope,reporting_type,period_end_date").execute()
                        stored += 1
                except Exception as e:
                    logger.debug("[fund/%s] income-stmt error %s %s: %s", ticker, scope, period_str, e)

                # Balance sheet
                try:
                    bs_data = await si.get_balance_sheet(
                        ticker=ticker,
                        period_end_date=period_str,
                        statement_scope=scope,
                    )
                    if bs_data and bs_data.financials:
                        sb.table("fact_balance_sheet").upsert({
                            "company_id":     company_id or bs_data.company_id,
                            "ticker":         ticker,
                            "statement_scope": scope,
                            "fiscal_year":    bs_data.fiscal_year,
                            "fiscal_quarter": bs_data.fiscal_quarter,
                            "period_end_date": _iso(bs_data.period_end_date),
                            "audit_status":   bs_data.audit_status,
                            "currency":       bs_data.currency,
                            "scale":          bs_data.scale,
                            "financials":     json.dumps(bs_data.financials),
                            "source":         "stockinsights",
                            "fetched_at":     datetime.now(timezone.utc).isoformat(),
                        }, on_conflict="company_id,statement_scope,period_end_date").execute()
                        stored += 1
                except Exception as e:
                    logger.debug("[fund/%s] balance-sheet error %s %s: %s", ticker, scope, period_str, e)

                # Cash flow
                try:
                    cf_data = await si.get_cash_flow(
                        ticker=ticker,
                        period_end_date=period_str,
                        reporting_type=period_type,
                        statement_scope=scope,
                    )
                    if cf_data and cf_data.financials:
                        sb.table("fact_cash_flow").upsert({
                            "company_id":     company_id or cf_data.company_id,
                            "ticker":         ticker,
                            "statement_scope": scope,
                            "reporting_type": period_type,
                            "fiscal_year":    cf_data.fiscal_year,
                            "fiscal_quarter": cf_data.fiscal_quarter,
                            "period_end_date": _iso(cf_data.period_end_date),
                            "audit_status":   cf_data.audit_status,
                            "currency":       cf_data.currency,
                            "scale":          cf_data.scale,
                            "financials":     json.dumps(cf_data.financials),
                            "source":         "stockinsights",
                            "fetched_at":     datetime.now(timezone.utc).isoformat(),
                        }, on_conflict="company_id,statement_scope,reporting_type,period_end_date").execute()
                        stored += 1
                except Exception as e:
                    logger.debug("[fund/%s] cash-flow error %s %s: %s", ticker, scope, period_str, e)

    return stored


async def _stream_fundamentals(si, sb, queue: asyncio.Queue, backfill_tickers: list[str]) -> None:
    """Process triggered fetches from queue; also slow-drip backfill all companies."""
    backfill_index = 0
    BACKFILL_INTERVAL = 8   # seconds between backfill companies (450/hr = well within 10 req/s limit)
    last_backfill = 0.0

    import time
    while True:
        # 1. Drain triggered queue first (priority)
        try:
            ticker = queue.get_nowait()
            logger.info("[fund] triggered fetch: %s", ticker)
            stored = await _fetch_and_store_fundamentals(si, sb, ticker)
            logger.info("[fund] %s: stored %d rows", ticker, stored)
            if stored:
                _log_job(sb, "si_fund_triggered", 3, stored, "success")
            queue.task_done()
            continue
        except asyncio.QueueEmpty:
            pass

        # 2. Slow backfill
        now = time.monotonic()
        if now - last_backfill >= BACKFILL_INTERVAL and backfill_index < len(backfill_tickers):
            ticker = backfill_tickers[backfill_index]
            backfill_index += 1
            logger.debug("[fund/backfill] %s (%d/%d)", ticker, backfill_index, len(backfill_tickers))
            try:
                stored = await _fetch_and_store_fundamentals(si, sb, ticker)
                if stored:
                    logger.info("[fund/backfill] %s: +%d rows", ticker, stored)
            except Exception as e:
                logger.warning("[fund/backfill] %s error: %s", ticker, e)
            last_backfill = time.monotonic()

            if backfill_index >= len(backfill_tickers):
                logger.info("[fund/backfill] Complete. All %d companies processed.", len(backfill_tickers))

        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Stream 4: Results Calendar  (hourly)
# ---------------------------------------------------------------------------

async def _stream_calendar(si, sb) -> None:
    while True:
        try:
            rows = []
            page = 1
            total_seen = 0
            while True:
                results, total = await si.get_results_calendar(page=page, limit=100)
                if not results:
                    break
                for r in results:
                    rows.append({
                        "ticker":         r.ticker,
                        "company_name":   r.company_name,
                        "result_date":    _iso(r.result_date),
                        "fiscal_year":    _int_safe(r.fiscal_year),
                        "fiscal_quarter": _int_safe(r.fiscal_quarter),
                        "result_type":    r.result_type,
                        "raw_data":       json.dumps(r.model_dump(mode="json")),
                        "source":         "stockinsights",
                        "fetched_at":     datetime.now(timezone.utc).isoformat(),
                    })
                total_seen += len(results)
                if total_seen >= total or not results:
                    break
                page += 1

            if rows:
                sb.table("fact_results_calendar").upsert(
                    rows, on_conflict="ticker,fiscal_year,fiscal_quarter"
                ).execute()
                logger.info("[calendar] synced %d entries", len(rows))
                _log_job(sb, "si_calendar_sync", len(rows), len(rows), "success")
        except Exception as e:
            logger.error("[calendar] error: %s", e)

        await asyncio.sleep(3600)


# ---------------------------------------------------------------------------
# Stream 5: Technicals  (daily post-market, yFinance)
# ---------------------------------------------------------------------------

def _compute_indicators(df: pd.DataFrame) -> dict:
    """Compute technical indicators from a daily OHLCV DataFrame."""
    if df is None or len(df) < 20:
        return {}

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    def ema(series, period):
        return series.ewm(span=period, adjust=False).mean()

    def sma(series, period):
        return series.rolling(period).mean()

    # Indicators on the last row
    last = len(df) - 1

    # RSI-14
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = (100 - 100 / (1 + rs)).iloc[last]

    # MACD 12/26/9
    ema12      = ema(close, 12).iloc[last]
    ema26      = ema(close, 26).iloc[last]
    macd_val   = ema12 - ema26
    macd_sig   = ema(ema(close, 12) - ema(close, 26), 9).iloc[last]
    macd_hist  = macd_val - macd_sig

    # ATR-14
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[last]

    # Bollinger 20
    sma20  = sma(close, 20).iloc[last]
    std20  = close.rolling(20).std().iloc[last]
    bb_up  = sma20 + 2 * std20
    bb_lo  = sma20 - 2 * std20

    c = close.iloc[last]
    c_prev = close.iloc[last - 1] if last >= 1 else c
    c_5    = close.iloc[last - 5]  if last >= 5  else c
    c_20   = close.iloc[last - 20] if last >= 20 else c

    vol_sma20  = vol.rolling(20).mean().iloc[last]
    rel_vol    = (vol.iloc[last] / vol_sma20) if vol_sma20 and vol_sma20 > 0 else None

    high_52w = high.tail(252).max()
    low_52w  = low.tail(252).min()

    def _f(v):
        try:
            x = float(v)
            return None if (x != x) else round(x, 4)  # NaN check
        except (TypeError, ValueError):
            return None

    return {
        "sma_20":            _f(sma20),
        "sma_50":            _f(sma(close, 50).iloc[last]),
        "sma_200":           _f(sma(close, 200).iloc[last] if len(df) >= 200 else None),
        "ema_20":            _f(ema(close, 20).iloc[last]),
        "rsi_14":            _f(rsi),
        "macd":              _f(macd_val),
        "macd_signal":       _f(macd_sig),
        "macd_hist":         _f(macd_hist),
        "atr_14":            _f(atr),
        "bb_upper":          _f(bb_up),
        "bb_mid":            _f(sma20),
        "bb_lower":          _f(bb_lo),
        "pct_change_1d":     _f((c - c_prev) / c_prev * 100) if c_prev else None,
        "pct_change_5d":     _f((c - c_5) / c_5 * 100) if c_5 else None,
        "pct_change_20d":    _f((c - c_20) / c_20 * 100) if c_20 else None,
        "high_52w":          _f(high_52w),
        "low_52w":           _f(low_52w),
        "pct_from_52w_high": _f((c - high_52w) / high_52w * 100) if high_52w else None,
        "vol_sma_20":        _f(vol_sma20),
        "rel_volume":        _f(rel_vol),
    }


def _fetch_technicals_sync(ticker: str) -> Union[dict, None]:
    """Blocking yFinance call — run in thread pool."""
    try:
        t = yf.Ticker(ticker + ".NS")
        df = t.history(period="1y", interval="1d", auto_adjust=True)
        if df is None or len(df) < 20:
            return None
        df = df.dropna(subset=["Close"])
        last_row = df.iloc[-1]
        indicators = _compute_indicators(df)
        return {
            "ticker":      ticker,
            "date":        df.index[-1].date().isoformat(),
            "open":        round(float(last_row["Open"]),  2),
            "high":        round(float(last_row["High"]),  2),
            "low":         round(float(last_row["Low"]),   2),
            "close":       round(float(last_row["Close"]), 2),
            "volume":      int(last_row["Volume"]) if last_row["Volume"] else None,
            **indicators,
            "source":      "yfinance",
            "fetched_at":  datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return None


async def _run_technicals_batch(sb, tickers: list[str]) -> int:
    """Fetch technicals for a batch of tickers via thread pool."""
    loop = asyncio.get_event_loop()
    stored = 0
    BATCH = 20

    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i + BATCH]
        tasks = [loop.run_in_executor(_THREAD_POOL, _fetch_technicals_sync, t) for t in chunk]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        rows = []
        for r in results:
            if isinstance(r, dict) and r.get("ticker"):
                rows.append(r)

        if rows:
            try:
                # Resolve company_ids
                tickers_in = [r["ticker"] for r in rows]
                cmap_res = sb.table("dim_company").select("ticker,company_id").in_("ticker", tickers_in).execute()
                cmap = {c["ticker"]: c["company_id"] for c in (cmap_res.data or [])}
                for r in rows:
                    r["company_id"] = cmap.get(r["ticker"])

                sb.table("fact_technicals").upsert(rows, on_conflict="ticker,date").execute()
                stored += len(rows)
                logger.info("[tech] batch %d-%d: %d/%d stored", i, i+BATCH, len(rows), len(chunk))
            except Exception as e:
                logger.error("[tech] upsert error: %s", e)

        await asyncio.sleep(2)  # brief pause between batches

    return stored


async def _stream_technicals(sb, universe_tickers: list[str]) -> None:
    """Run technicals once daily after market close (15:40 IST), then sleep until next day."""
    ran_today: Union[date, None] = None

    while True:
        today = datetime.now(timezone.utc).date()
        if _after_market_close() and ran_today != today:
            logger.info("[tech] Starting daily technicals run for %d tickers", len(universe_tickers))
            try:
                n = await _run_technicals_batch(sb, universe_tickers)
                _log_job(sb, "neo_technicals_daily", len(universe_tickers), n, "success")
                logger.info("[tech] Daily run complete: %d rows stored", n)
            except Exception as e:
                logger.error("[tech] daily run error: %s", e)
                _log_job(sb, "neo_technicals_daily", 0, 0, "failed", str(e))
            ran_today = today

        await asyncio.sleep(300)  # check every 5 min


# ---------------------------------------------------------------------------
# Stream 6: Bulk / Block Deals  (NSE, every 15 min during market hours)
# ---------------------------------------------------------------------------

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

INSTITUTIONAL_KEYWORDS = [
    "FII", "FPI", "MUTUAL FUND", "MF", "LIC", "SBI", "HDFC MF", "ICICI MF",
    "MORGAN STANLEY", "GOLDMAN", "BLACKROCK", "JPMORGAN", "CITIGROUP",
    "MERRILL", "NOMURA", "MACQUARIE", "UBS", "CREDIT SUISSE", "DEUTSCHE",
    "SOCIETE", "BNP PARIBAS", "BARCLAYS", "HSBC", "STANDARD CHARTERED",
]


def _is_institutional(name: str) -> bool:
    if not name:
        return False
    n = name.upper()
    return any(kw in n for kw in INSTITUTIONAL_KEYWORDS)


def _deal_id(ticker: str, deal_date: str, client: str, qty: Any) -> str:
    raw = f"{ticker}|{deal_date}|{client}|{qty}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


async def _fetch_nse_bulk_block(sb) -> int:
    stored = 0
    async with httpx.AsyncClient(headers=NSE_HEADERS, timeout=20, follow_redirects=True) as http:
        # Establish NSE session
        try:
            await http.get("https://www.nseindia.com/")
            await asyncio.sleep(1)
        except Exception:
            pass

        for deal_type, endpoint in [
            ("bulk",  "https://www.nseindia.com/api/snapshot-capital-market-largedeal"),
            ("block", "https://www.nseindia.com/api/live-analysis-data-block-deals"),
        ]:
            try:
                r = await http.get(endpoint)
                if r.status_code != 200:
                    logger.warning("[bbd/%s] NSE returned %d", deal_type, r.status_code)
                    continue
                data = r.json()
                deals = data if isinstance(data, list) else data.get("data", [])
            except Exception as e:
                logger.error("[bbd/%s] fetch error: %s", deal_type, e)
                continue

            rows = []
            for d in deals:
                ticker = d.get("symbol", "").strip()
                client = d.get("clientName", "") or d.get("client_name", "")
                qty    = _int_safe(d.get("quantity", d.get("qty_traded_")))
                price  = d.get("tradePrice", d.get("trade_price_"))
                try:
                    price_f = float(price) if price else None
                except (TypeError, ValueError):
                    price_f = None
                deal_date = str(d.get("tradeDate", d.get("trade_date_", date.today().isoformat())))[:10]
                deal_id = _deal_id(ticker, deal_date, client, qty)

                rows.append({
                    "deal_id":         deal_id,
                    "ticker":          ticker,
                    "company_name":    d.get("company", ""),
                    "exchange":        "NSE",
                    "deal_type":       deal_type,
                    "deal_date":       deal_date,
                    "client_name":     client,
                    "buy_sell":        (d.get("buySell", d.get("buy_sell_", "")) or "").upper(),
                    "quantity":        qty,
                    "price":           price_f,
                    "value_cr":        round(qty * price_f / 1e7, 4) if qty and price_f else None,
                    "is_institutional": _is_institutional(client),
                    "source":          "nse",
                    "fetched_at":      datetime.now(timezone.utc).isoformat(),
                })

            if rows:
                try:
                    sb.table("fact_bulk_block_deals").upsert(rows, on_conflict="deal_id").execute()
                    stored += len(rows)
                    logger.info("[bbd/%s] %d deals stored", deal_type, len(rows))
                except Exception as e:
                    logger.error("[bbd/%s] upsert error: %s", deal_type, e)

    return stored


async def _stream_bulk_block(sb) -> None:
    while True:
        if _is_market_hours():
            try:
                n = await _fetch_nse_bulk_block(sb)
                if n:
                    _log_job(sb, "nse_bulk_block", n, n, "success")
            except Exception as e:
                logger.error("[bbd] stream error: %s", e)
            await asyncio.sleep(900)  # 15 min
        else:
            await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# Main entry: run all streams concurrently
# ---------------------------------------------------------------------------

async def main() -> None:
    si = get_si_client()
    sb = _sb()

    # Load universe
    logger.info("Loading universe from dim_company...")
    try:
        res = sb.table("dim_company").select("ticker,company_id").order("ticker").execute()
        universe = res.data or []
        tickers = [c["ticker"] for c in universe]
        logger.info("Universe: %d tickers", len(tickers))
    except Exception as e:
        logger.error("Could not load universe: %s. Falling back to empty list.", e)
        tickers = []

    # Pre-load seen IDs
    seen_ann: set[str] = set()
    seen_fil: set[str] = set()
    try:
        r = sb.table("fact_announcements_tagged").select("announcement_id").execute()
        seen_ann = {x["announcement_id"] for x in (r.data or [])}
        logger.info("Pre-loaded %d announcement IDs", len(seen_ann))
    except Exception:
        pass
    try:
        r = sb.table("fact_filings").select("filing_id").execute()
        seen_fil = {x["filing_id"] for x in (r.data or [])}
        logger.info("Pre-loaded %d filing IDs", len(seen_fil))
    except Exception:
        pass

    # Fundamentals queue for triggered fetches
    fund_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    logger.info("=" * 60)
    logger.info("NEO MASTER POLLER STARTED")
    logger.info("  Streams: announcements | filings | fundamentals | calendar | technicals | bulk-block")
    logger.info("  Universe: %d companies", len(tickers))
    logger.info("  Primary source: %s | Trial expires: %s", settings.DATA_PRIMARY_SOURCE, settings.TRIAL_EXPIRES_AT)
    logger.info("=" * 60)

    # Kick off first calendar sync immediately
    asyncio.create_task(_stream_calendar(si, sb))

    # 60s announcement + filings loop
    async def _ann_fil_loop():
        while True:
            tick_start = asyncio.get_event_loop().time()
            try:
                a = await _upsert_announcements(si, sb, seen_ann)
                f = await _upsert_filings(si, sb, seen_fil, fund_queue)
                if a + f:
                    _log_job(sb, "si_realtime_poll", a + f, a + f, "success")
            except Exception as e:
                logger.exception("[poll] cycle error: %s", e)
                _log_job(sb, "si_realtime_poll", 0, 0, "failed", str(e))
            elapsed = asyncio.get_event_loop().time() - tick_start
            await asyncio.sleep(max(0, 60 - elapsed))

    await asyncio.gather(
        _ann_fil_loop(),
        _stream_fundamentals(si, sb, fund_queue, tickers),
        _stream_technicals(sb, tickers),
        _stream_bulk_block(sb),
    )


if __name__ == "__main__":
    asyncio.run(main())
