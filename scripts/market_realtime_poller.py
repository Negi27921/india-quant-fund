#!/usr/bin/env python3
"""
Live market price engine — writes to fact_market_realtime + fact_market_events.

Modes:
  --mode intraday  fetch top 500 by market cap (fast, ≈2 min — run every 15 min)
  --mode eod       fetch full universe + update 52W H/L (≈15 min — run at 3:45 PM IST)
  --mode events    detect events from current fact_market_realtime, no price fetch

Source: yFinance (15-min delayed, free — no broker dependency).
Writes:  SUPABASE_SERVICE_KEY required (upsert to fact_market_realtime + fact_market_events).

Architecture note:
  fact_screener_fundamentals → slow fundamentals  (never updated here)
  fact_market_realtime       → live prices        (updated here only)
  vw_stock_snapshot          → unified read model  (query for AI / UI)

GitHub Actions:
  Intraday: */15 4-9 * * 1-5   (every 15 min during market hours, UTC)
  EOD:      10 10 * * 1-5      (10:10 UTC = 3:40 PM IST, just after close)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import warnings
warnings.filterwarnings("ignore")
import yfinance as yf

from supabase import create_client

# ── Config ────────────────────────────────────────────────────────────────────

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN  = (9, 15)   # IST
MARKET_CLOSE = (15, 35)  # IST

INTRADAY_TOP_N   = 500    # stocks to cover in intraday mode
BATCH_YF         = 200    # tickers per yf.download() call
MAX_THREADS      = 10     # parallel yf.download() batches
EOD_52W_THREADS  = 20     # parallel threads for fast_info 52W fetch (EOD only)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("market_realtime_poller")
logging.getLogger("yfinance").setLevel(logging.ERROR)


# ── Supabase ──────────────────────────────────────────────────────────────────

def _get_sb():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    return create_client(url, key)


def _load_universe(sb, limit: Optional[int] = None) -> list[str]:
    """Return clean tickers from dim_company ordered by market_cap DESC."""
    resp = sb.table("dim_company").select(
        "ticker,market_cap_inr_cr"
    ).order("market_cap_inr_cr", desc=True).execute()
    tickers = [r["ticker"] for r in (resp.data or []) if r.get("ticker")]
    if limit:
        tickers = tickers[:limit]
    log.info("Universe loaded: %d tickers", len(tickers))
    return tickers


# ── Price fetch ───────────────────────────────────────────────────────────────

def _to_yf(ticker: str) -> str:
    """Convert clean NSE ticker to yFinance symbol."""
    if ticker.startswith("^") or "." in ticker:
        return ticker
    return f"{ticker}.NS"


def _fetch_batch_ohlcv(tickers: list[str]) -> dict[str, dict]:
    """
    Download 2-day daily OHLCV for a batch of tickers.
    Returns {clean_ticker: {open, high, low, close, volume, prev_close, pct_change}}.
    """
    yf_tickers = [_to_yf(t) for t in tickers]
    try:
        data = yf.download(
            tickers=yf_tickers,
            period="5d",           # 5d → guaranteed to have prev_close
            interval="1d",
            auto_adjust=True,
            prepost=False,
            threads=True,
            progress=False,
        )
    except Exception as exc:
        log.warning("yf.download error for batch: %s", exc)
        return {}

    if data is None or data.empty:
        return {}

    result: dict[str, dict] = {}
    now_ist = datetime.now(IST)
    market_open = (now_ist.hour, now_ist.minute) >= MARKET_OPEN
    market_status = "OPEN" if market_open and now_ist.weekday() < 5 else "CLOSED"

    # Multi-ticker: columns are MultiIndex (price_type, yf_ticker)
    for clean, yf_sym in zip(tickers, yf_tickers):
        try:
            if len(tickers) == 1:
                sub = data
            else:
                if isinstance(data.columns, type(data.columns)) and hasattr(data.columns, "levels"):
                    sub = data.xs(yf_sym, axis=1, level=1)
                else:
                    sub = data  # flat (single-ticker fallback)

            sub = sub.dropna(how="all")
            if len(sub) < 1:
                continue

            today  = sub.iloc[-1]
            prev   = sub.iloc[-2] if len(sub) >= 2 else sub.iloc[-1]

            prev_close = float(prev["Close"]) if prev["Close"] == prev["Close"] else None
            ltp        = float(today["Close"]) if today["Close"] == today["Close"] else None
            if ltp is None:
                continue

            pct = round((ltp - prev_close) / prev_close * 100, 2) if prev_close else None
            vol = int(today["Volume"]) if today["Volume"] == today["Volume"] else None

            result[clean] = {
                "symbol":         clean,
                "exchange":       "NSE",
                "ltp":            round(ltp, 2),
                "prev_close":     round(prev_close, 2) if prev_close else None,
                "day_open":       round(float(today["Open"]),  2) if today["Open"] == today["Open"] else None,
                "day_high":       round(float(today["High"]),  2) if today["High"] == today["High"] else None,
                "day_low":        round(float(today["Low"]),   2) if today["Low"]  == today["Low"]  else None,
                "volume":         vol,
                "pct_change":     pct,
                "abs_change":     round(ltp - prev_close, 2) if prev_close else None,
                "market_status":  market_status,
                "last_trade_time": datetime.now(timezone.utc).isoformat(),
                "updated_at":     datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            continue

    return result


def _fetch_52w(ticker: str) -> dict:
    """Fetch 52W high/low via yFinance fast_info (used in EOD mode only)."""
    try:
        t  = yf.Ticker(_to_yf(ticker))
        fi = t.fast_info
        h  = getattr(fi, "fifty_two_week_high", None)
        l  = getattr(fi, "fifty_two_week_low",  None)
        mc = getattr(fi, "market_cap",          None)
        shares = getattr(fi, "shares",          None)
        return {
            "symbol":        ticker,
            "week_high_52":  round(h,  2) if h else None,
            "week_low_52":   round(l,  2) if l else None,
            "market_cap_live_cr": round(mc / 1e7, 2) if mc else None,
        }
    except Exception:
        return {"symbol": ticker}


# ── Event detection ───────────────────────────────────────────────────────────

_EVENT_SQL = {
    "NEW_52W_HIGH": {
        "severity": "ALERT",
        "condition": "ltp >= week_high_52 AND week_high_52 IS NOT NULL AND week_high_52 > 0",
        "meta_cols": ["ltp", "week_high_52", "pct_change"],
    },
    "NEAR_52W_HIGH": {
        "severity": "INFO",
        "condition": "ltp >= week_high_52 * 0.98 AND ltp < week_high_52 AND week_high_52 IS NOT NULL",
        "meta_cols": ["ltp", "week_high_52", "pct_change"],
    },
    "NEAR_52W_LOW": {
        "severity": "WARN",
        "condition": "ltp <= week_low_52 * 1.05 AND week_low_52 IS NOT NULL AND week_low_52 > 0",
        "meta_cols": ["ltp", "week_low_52", "pct_change"],
    },
    "PRICE_GAP_UP": {
        "severity": "INFO",
        "condition": "day_open > prev_close * 1.03 AND prev_close IS NOT NULL",
        "meta_cols": ["day_open", "prev_close", "pct_change"],
    },
    "PRICE_GAP_DOWN": {
        "severity": "WARN",
        "condition": "day_open < prev_close * 0.97 AND prev_close IS NOT NULL",
        "meta_cols": ["day_open", "prev_close", "pct_change"],
    },
}


def _detect_and_emit_events(sb) -> int:
    """
    Read fact_market_realtime, detect events, insert into fact_market_events.
    The unique daily index prevents duplicate events per (type, symbol, date).
    """
    rows = sb.table("fact_market_realtime").select("*").execute().data or []
    today_str = datetime.now(IST).date().isoformat()
    events: list[dict] = []

    for r in rows:
        ltp        = r.get("ltp")
        prev_close = r.get("prev_close")
        week_high  = r.get("week_high_52")
        week_low   = r.get("week_low_52")
        day_open   = r.get("day_open")
        symbol     = r["symbol"]

        checks: list[tuple[str, str, dict]] = []

        if ltp and week_high and ltp >= week_high:
            checks.append(("NEW_52W_HIGH", "ALERT", {"ltp": ltp, "week_high_52": week_high}))
        elif ltp and week_high and ltp >= week_high * 0.98:
            checks.append(("NEAR_52W_HIGH", "INFO", {"ltp": ltp, "week_high_52": week_high}))

        if ltp and week_low and ltp <= week_low * 1.05:
            checks.append(("NEAR_52W_LOW", "WARN", {"ltp": ltp, "week_low_52": week_low}))

        if day_open and prev_close:
            if day_open > prev_close * 1.03:
                checks.append(("PRICE_GAP_UP",   "INFO", {"day_open": day_open, "prev_close": prev_close}))
            elif day_open < prev_close * 0.97:
                checks.append(("PRICE_GAP_DOWN",  "WARN", {"day_open": day_open, "prev_close": prev_close}))

        for event_type, severity, meta in checks:
            events.append({
                "event_type":  event_type,
                "symbol":      symbol,
                "severity":    severity,
                "metadata":    meta,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            })

    if not events:
        log.info("No events detected")
        return 0

    # Batch insert; unique daily index deduplicates automatically
    BATCH = 100
    inserted = 0
    for i in range(0, len(events), BATCH):
        try:
            sb.table("fact_market_events").upsert(
                events[i : i + BATCH],
                on_conflict="event_type,symbol,triggered_at::date",
                ignore_duplicates=True,
            ).execute()
            inserted += len(events[i : i + BATCH])
        except Exception as exc:
            log.warning("Event insert error: %s", exc)
    log.info("Events detected: %d total", inserted)
    return inserted


# ── Upsert helpers ────────────────────────────────────────────────────────────

def _upsert(sb, rows: list[dict], dry_run: bool) -> None:
    if not rows or dry_run:
        if dry_run:
            log.info("[dry-run] Would upsert %d rows to fact_market_realtime", len(rows))
        return
    BATCH = 200
    for i in range(0, len(rows), BATCH):
        try:
            sb.table("fact_market_realtime").upsert(
                rows[i : i + BATCH], on_conflict="symbol"
            ).execute()
        except Exception as exc:
            log.warning("Upsert error batch %d: %s", i // BATCH, exc)


# ── Main run modes ─────────────────────────────────────────────────────────────

def _is_market_hours() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:  # weekend
        return False
    t = (now.hour, now.minute)
    return MARKET_OPEN <= t <= MARKET_CLOSE


def run_intraday(sb, dry_run: bool) -> None:
    """Fast run: top 500 stocks, OHLCV only, ~2 minutes."""
    if not _is_market_hours():
        log.info("Market closed — skipping intraday run")
        return

    tickers = _load_universe(sb, limit=INTRADAY_TOP_N)
    chunks  = [tickers[i : i + BATCH_YF] for i in range(0, len(tickers), BATCH_YF)]
    all_rows: list[dict] = []

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as pool:
        futures = {pool.submit(_fetch_batch_ohlcv, chunk): chunk for chunk in chunks}
        for fut in as_completed(futures):
            try:
                all_rows.extend(fut.result().values())
            except Exception as exc:
                log.warning("Batch error: %s", exc)

    log.info("Fetched %d/%d price rows", len(all_rows), len(tickers))
    _upsert(sb, all_rows, dry_run)
    _detect_and_emit_events(sb)


def run_eod(sb, dry_run: bool) -> None:
    """Full run: all universe stocks + 52W H/L refresh, ~15 minutes."""
    tickers = _load_universe(sb)  # no limit
    chunks  = [tickers[i : i + BATCH_YF] for i in range(0, len(tickers), BATCH_YF)]
    all_rows: dict[str, dict] = {}

    # Step 1: batch OHLCV
    log.info("Step 1/2: batch OHLCV for %d tickers…", len(tickers))
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as pool:
        futures = {pool.submit(_fetch_batch_ohlcv, chunk): chunk for chunk in chunks}
        for fut in as_completed(futures):
            try:
                all_rows.update(fut.result())
            except Exception as exc:
                log.warning("Batch error: %s", exc)

    # Step 2: 52W high/low via fast_info (parallel, only for fetched rows)
    log.info("Step 2/2: 52W H/L for %d tickers…", len(all_rows))
    with ThreadPoolExecutor(max_workers=EOD_52W_THREADS) as pool:
        futures52 = {pool.submit(_fetch_52w, t): t for t in all_rows}
        for fut in as_completed(futures52):
            try:
                d52 = fut.result()
                sym = d52.pop("symbol")
                if sym in all_rows:
                    all_rows[sym].update({k: v for k, v in d52.items() if v is not None})
                    # Compute pct_from_52w_high
                    ltp = all_rows[sym].get("ltp")
                    h52 = all_rows[sym].get("week_high_52")
                    if ltp and h52:
                        all_rows[sym]["pct_from_52w_high"] = round((ltp - h52) / h52 * 100, 1)
            except Exception:
                pass

    log.info("EOD: writing %d rows to fact_market_realtime", len(all_rows))
    _upsert(sb, list(all_rows.values()), dry_run)

    # Also patch dim_company with fresh price/cap
    if not dry_run:
        dim_updates = [
            {
                "ticker":             sym,
                "market_cap_inr_cr":  r.get("market_cap_live_cr"),
                "current_price_inr":  r.get("ltp"),
                "high_52w_inr":       r.get("week_high_52"),
                "low_52w_inr":        r.get("week_low_52"),
                "prices_as_of":       datetime.now(timezone.utc).isoformat(),
                "updated_at":         datetime.now(timezone.utc).isoformat(),
            }
            for sym, r in all_rows.items()
            if r.get("ltp")
        ]
        for i in range(0, len(dim_updates), 200):
            try:
                sb.table("dim_company").upsert(
                    dim_updates[i : i + 200], on_conflict="ticker"
                ).execute()
            except Exception as exc:
                log.warning("dim_company patch error: %s", exc)
        log.info("dim_company patched for %d stocks", len(dim_updates))

    _detect_and_emit_events(sb)
    log.info("EOD run complete: %d rows written", len(all_rows))


def run_events_only(sb, dry_run: bool) -> None:
    """Only detect events from the current fact_market_realtime snapshot."""
    if dry_run:
        log.info("[dry-run] events detection skipped")
        return
    _detect_and_emit_events(sb)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["intraday", "eod", "events"], default="intraday")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sb = _get_sb()
    t0 = time.monotonic()
    if args.mode == "intraday":
        run_intraday(sb, args.dry_run)
    elif args.mode == "eod":
        run_eod(sb, args.dry_run)
    else:
        run_events_only(sb, args.dry_run)
    log.info("Done in %.1fs", time.monotonic() - t0)
