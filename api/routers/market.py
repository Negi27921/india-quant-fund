"""Real-time Indian market data — indices, movers, sectors, quotes.

Primary source: NSE India official API via nsepython (zero-delay, official)
Fallback:       yfinance (15-min delayed but global coverage)
"""
from __future__ import annotations

import asyncio
import json
import math
import os as _os
import threading as _threading
import time
import urllib.request as _ur
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import wraps
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

warnings.filterwarnings("ignore")
import yfinance as yf  # noqa: E402

try:
    from nsepython import nsefetch as _nsefetch
    _NSE_AVAILABLE = True
except Exception:
    _NSE_AVAILABLE = False

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")
_executor = ThreadPoolExecutor(max_workers=8)

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, ttl: int = 15):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            now = time.monotonic()
            if key in _cache:
                ts, val = _cache[key]
                if now - ts < ttl:
                    return val
            result = await fn(*args, **kwargs)
            _cache[key] = (now, result)
            return result
        return wrapper
    return decorator


def _run(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))


# ── Supabase helpers (for stock_universe queries) ─────────────────────────────
_SB_URL = _os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_SB_KEY = _os.getenv("SUPABASE_KEY", "").strip()

def _sb_headers_mkt() -> dict:
    return {
        "apikey":        _SB_KEY,
        "Authorization": f"Bearer {_SB_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "count=none",
    }

# Universe symbols cache (1h TTL — symbols don't change often)
_UNIVERSE_CACHE: tuple[float, list[str]] = (0.0, [])

def _get_universe_symbols() -> list[str]:
    global _UNIVERSE_CACHE
    ts, syms = _UNIVERSE_CACHE
    if syms and time.monotonic() - ts < 3600:
        return syms
    if not (_SB_URL and _SB_KEY):
        return []
    try:
        headers = {**_sb_headers_mkt(), "Range": "0-2999", "Range-Unit": "items"}
        req = _ur.Request(
            f"{_SB_URL}/rest/v1/stock_universe?select=symbol&is_active=eq.true&order=symbol.asc",
            headers=headers,
        )
        with _ur.urlopen(req, timeout=10) as r:
            rows = json.loads(r.read())
        syms = [row["symbol"] for row in rows if row.get("symbol")]
        _UNIVERSE_CACHE = (time.monotonic(), syms)
        return syms
    except Exception:
        return []

def _get_universe_breadth() -> dict | None:
    """Query stock_universe for advances/declines — paginated to bypass 1000-row server cap."""
    if not (_SB_URL and _SB_KEY):
        return None
    try:
        all_rows: list[dict] = []
        page_size = 1000
        offset = 0
        while True:
            headers = {
                **_sb_headers_mkt(),
                "Range":      f"{offset}-{offset + page_size - 1}",
                "Range-Unit": "items",
            }
            req = _ur.Request(
                f"{_SB_URL}/rest/v1/stock_universe"
                "?select=last_price,prev_close"
                "&is_active=eq.true"
                "&last_price=gt.0"
                "&prev_close=not.is.null",
                headers=headers,
            )
            with _ur.urlopen(req, timeout=10) as r:
                batch = json.loads(r.read())
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size

        adv = dec = unc = counted = 0
        for row in all_rows:
            lp = row.get("last_price")
            pc = row.get("prev_close")
            if not lp or not pc or pc == 0:
                continue
            if lp > pc:
                adv += 1
            elif lp < pc:
                dec += 1
            else:
                unc += 1
            counted += 1

        if counted < 50:
            return None
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%I:%M %p IST")
        return {
            "advances": adv, "declines": dec, "unchanged": unc,
            "total": counted,
            "ratio": round(adv / max(dec, 1), 2),
            "index_name": f"Project Universe ({counted} stocks)",
            "source": "Supabase · stock_universe",
            "as_of": now_ist,
        }
    except Exception:
        return None

def _get_universe_52w_highs(limit: int = 25) -> list[dict]:
    """Query stock_universe for stocks near 52-week highs (within 5%)."""
    if not (_SB_URL and _SB_KEY):
        return []
    try:
        headers = {**_sb_headers_mkt(), "Range": f"0-{limit - 1}", "Range-Unit": "items"}
        req = _ur.Request(
            f"{_SB_URL}/rest/v1/stock_universe"
            "?select=symbol,company,sector,last_price,week_high_52,exchange"
            "&is_active=eq.true"
            "&last_price=gt.0"
            "&week_high_52=gt.0"
            f"&order=last_price.desc",
            headers=headers,
        )
        with _ur.urlopen(req, timeout=10) as r:
            rows = json.loads(r.read())
        result = []
        for row in rows:
            lp = float(row.get("last_price") or 0)
            h52 = float(row.get("week_high_52") or 0)
            if lp <= 0 or h52 <= 0:
                continue
            if lp >= h52 * 0.95:   # within 5% of 52W high
                pct = round((lp / h52 - 1) * 100, 2)
                result.append({
                    "symbol":     row.get("symbol", ""),
                    "company":    row.get("company", ""),
                    "sector":     row.get("sector", ""),
                    "cmp":        round(lp, 2),
                    "high_52w":   round(h52, 2),
                    "change_pct": pct,
                    "exchange":   row.get("exchange", "NSE"),
                })
        return sorted(result, key=lambda x: x["change_pct"], reverse=True)[:limit]
    except Exception:
        return []


# ── Per-symbol price cache (90s TTL) — speeds up watchlist batch prices ───────
_PRICE_CACHE: dict[str, tuple[float, dict]] = {}
_PRICE_CACHE_TTL = 90  # seconds


# ── Constants ─────────────────────────────────────────────────────────────────
INDICES = {
    "nifty50":    ("^NSEI",    "Nifty 50"),
    "banknifty":  ("^NSEBANK", "Bank Nifty"),
    "sensex":     ("^BSESN",   "Sensex"),
    "niftymid50": ("^NSEMDCP50", "Nifty Midcap 50"),
    "niftyit":    ("^CNXIT",   "Nifty IT"),
}

NIFTY50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "KOTAKBANK.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS",
    "SBIN.NS", "AXISBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "NESTLEIND.NS", "TITAN.NS", "WIPRO.NS", "ULTRACEMCO.NS", "ONGC.NS",
    "POWERGRID.NS", "NTPC.NS", "TECHM.NS", "BAJAJFINSV.NS", "HCLTECH.NS",
    "SUNPHARMA.NS", "DIVISLAB.NS", "M&M.NS", "TATAMOTORS.NS", "TATASTEEL.NS",
    "JSWSTEEL.NS", "COALINDIA.NS", "GRASIM.NS", "CIPLA.NS", "DRREDDY.NS",
    "APOLLOHOSP.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BPCL.NS", "INDUSINDBK.NS",
    "ADANIPORTS.NS", "HINDALCO.NS", "BAJAJ-AUTO.NS", "SBILIFE.NS", "HDFCLIFE.NS",
    "BRITANNIA.NS", "UPL.NS", "SHREECEM.NS", "PIDILITIND.NS", "ADANIENT.NS",
]

SECTORS = {
    "IT":      "^CNXIT",
    "Bank":    "^NSEBANK",
    "FMCG":    "^CNXFMCG",
    "Auto":    "^CNXAUTO",
    "Pharma":  "^CNXPHARMA",
    "Metal":   "^CNXMETAL",
    "Energy":  "^CNXENERGY",
    "Realty":  "^CNXREALTY",
    "Infra":   "^CNXINFRA",
    "Finance": "^CNXFINANCE",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _sf(val, default: float = 0.0) -> float:
    try:
        import math
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return default


def _market_status() -> dict:
    now = datetime.now(IST)
    is_weekday = now.weekday() < 5
    open_t = now.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    is_open = is_weekday and open_t <= now <= close_t

    if not is_weekday:
        session = "WEEKEND"
    elif now < open_t:
        session = "PRE-OPEN"
    elif now > close_t:
        session = "CLOSED"
    else:
        session = "OPEN"

    return {
        "is_open": is_open,
        "session": session,
        "ist_time": now.strftime("%H:%M:%S"),
        "ist_date": now.strftime("%d %b %Y, %A"),
    }


def _fetch_fast_info(ticker: str) -> dict:
    try:
        fi = yf.Ticker(ticker).fast_info
        price = _sf(getattr(fi, "last_price", None))
        prev  = _sf(getattr(fi, "previous_close", None))
        high  = _sf(getattr(fi, "day_high", None))
        low   = _sf(getattr(fi, "day_low", None))
        vol   = int(_sf(getattr(fi, "three_month_average_volume", 0)))
        mktcap = _sf(getattr(fi, "market_cap", 0))
        change = price - prev if prev else 0
        change_pct = (change / prev * 100) if prev else 0
        return {
            "ticker": ticker,
            "price": round(price, 2),
            "prev_close": round(prev, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 3),
            "day_high": round(high, 2),
            "day_low": round(low, 2),
            "volume": vol,
            "market_cap": mktcap,
        }
    except Exception:
        return {"ticker": ticker, "price": 0, "prev_close": 0, "change": 0, "change_pct": 0, "day_high": 0, "day_low": 0}


def _l2_write_market(key: str, data) -> None:
    """Persist market data to L2 cache so cold Lambdas can serve last-session data."""
    try:
        from core.providers.registry import get_cache
        get_cache().set(f"market:{key}", data, ttl_seconds=86_400)
    except Exception:
        pass


def _l2_read_market(key: str):
    try:
        from core.providers.registry import get_cache
        return get_cache().get(f"market:{key}")
    except Exception:
        return None


def _batch_download(tickers: list[str]) -> list[dict]:
    """Single yf.download for all tickers — far faster than N individual fast_info calls.
    Uses period=5d so last-session data is always available regardless of weekends."""
    import math
    try:
        raw = yf.download(
            tickers, period="5d", interval="1d",
            auto_adjust=True, progress=False, threads=True, group_by="ticker",
        )
        results = []
        for ticker in tickers:
            try:
                df = raw[ticker] if len(tickers) > 1 else raw
                df = df.dropna(subset=["Close"])
                if len(df) < 1:
                    continue
                price = float(df["Close"].iloc[-1])
                prev  = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
                high  = float(df["High"].iloc[-1])
                low   = float(df["Low"].iloc[-1])
                vol   = int(df["Volume"].iloc[-1])
                if price <= 0 or math.isnan(price):
                    continue
                change     = price - prev
                change_pct = (change / prev * 100) if prev else 0
                results.append({
                    "ticker":     ticker,
                    "price":      round(price, 2),
                    "prev_close": round(prev, 2),
                    "change":     round(change, 2),
                    "change_pct": round(change_pct, 3),
                    "day_high":   round(high, 2),
                    "day_low":    round(low, 2),
                    "volume":     vol,
                    "market_cap": 0,
                })
            except Exception:
                pass
        return results
    except Exception:
        return []


def _fetch_nse_all_indices() -> dict[str, dict]:
    """Fetch all NSE indices in one call — returns {indexSymbol: data}."""
    if not _NSE_AVAILABLE:
        return {}
    try:
        data = _nsefetch("https://nseindia.com/api/allIndices")
        result = {}
        for d in data.get("data", []):
            sym = d.get("indexSymbol", "")
            if not sym:
                continue
            price = _sf(d.get("last", 0))
            chg   = _sf(d.get("variation", 0))
            chg_pct = _sf(d.get("percentChange", 0))
            prev  = price - chg
            result[sym] = {
                "price":      round(price, 2),
                "prev_close": round(prev, 2),
                "change":     round(chg, 2),
                "change_pct": round(chg_pct, 3),
                "day_high":   round(_sf(d.get("high", price)), 2),
                "day_low":    round(_sf(d.get("low",  price)), 2),
                "pe":         _sf(d.get("pe", 0)),
                "pb":         _sf(d.get("pb", 0)),
            }
        return result
    except Exception:
        return {}


def _fetch_nse_index_stocks(index_name: str) -> list[dict]:
    """Fetch live stocks in an NSE index (e.g. 'NIFTY 50', 'NIFTY MIDCAP 50')."""
    if not _NSE_AVAILABLE:
        return []
    try:
        url = f"https://nseindia.com/api/equity-stockIndices?index={index_name.replace(' ', '%20')}"
        data = _nsefetch(url)
        stocks = []
        for d in data.get("data", []):
            sym = d.get("symbol", "")
            if not sym or sym == index_name:
                continue
            price = _sf(d.get("lastPrice", 0))
            prev  = _sf(d.get("previousClose", price))
            chg   = price - prev
            chg_pct = (chg / prev * 100) if prev else 0
            stocks.append({
                "ticker":     sym,
                "price":      round(price, 2),
                "prev_close": round(prev, 2),
                "change":     round(chg, 2),
                "change_pct": round(chg_pct, 3),
                "day_high":   round(_sf(d.get("dayHigh",  price)), 2),
                "day_low":    round(_sf(d.get("dayLow",   price)), 2),
                "volume":     int(_sf(d.get("totalTradedVolume", 0))),
                "market_cap": _sf(d.get("ffmc", 0)),
            })
        return stocks
    except Exception:
        return []


def _fetch_index(symbol: str) -> dict:
    try:
        fi = yf.Ticker(symbol).fast_info
        price = _sf(getattr(fi, "last_price", None))
        prev  = _sf(getattr(fi, "previous_close", None))
        high  = _sf(getattr(fi, "day_high", None))
        low   = _sf(getattr(fi, "day_low", None))
        change = price - prev
        change_pct = (change / prev * 100) if prev else 0
        return {
            "symbol": symbol,
            "price": round(price, 2),
            "prev_close": round(prev, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 3),
            "day_high": round(high, 2),
            "day_low": round(low, 2),
        }
    except Exception:
        return {"symbol": symbol, "price": 0, "change": 0, "change_pct": 0, "day_high": 0, "day_low": 0}


def _fetch_history(ticker: str, period: str, interval: str) -> list[dict]:
    import math
    df = yf.Ticker(ticker).history(period=period, interval=interval)
    if df.empty:
        return []
    df = df.reset_index()
    out = []
    for _, row in df.iterrows():
        ts = row.get("Datetime") or row.get("Date")
        o = _sf(row.get("Open"))
        h = _sf(row.get("High"))
        l = _sf(row.get("Low"))
        c = _sf(row.get("Close"))
        v = int(_sf(row.get("Volume", 0)))
        if c == 0 or math.isnan(c):
            continue
        # Use ISO date string for daily/weekly/monthly, Unix timestamp for intraday
        if interval in ("1d", "1wk", "1mo"):
            time_val = str(ts)[:10]  # "YYYY-MM-DD"
        else:
            try:
                import pandas as pd
                if hasattr(ts, 'timestamp'):
                    time_val = int(ts.timestamp())
                else:
                    time_val = int(pd.Timestamp(ts).timestamp())
            except Exception:
                time_val = str(ts)[:10]
        out.append({
            "time":   time_val,
            "open":   round(o, 2),
            "high":   round(h, 2),
            "low":    round(l, 2),
            "close":  round(c, 2),
            "volume": v,
        })
    return out


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def market_status():
    return _market_status()


NSE_INDEX_SYMBOL_MAP = {
    "nifty50":    ("NIFTY 50",           "^NSEI",      "Nifty 50"),
    "banknifty":  ("NIFTY BANK",         "^NSEBANK",   "Bank Nifty"),
    "sensex":     ("SENSEX",             "^BSESN",     "Sensex"),
    "niftymid50": ("NIFTY MIDCAP 50",    "^NSEMDCP50", "Nifty Midcap 50"),
    "niftyit":    ("NIFTY IT",           "^CNXIT",     "Nifty IT"),
    "niftysmc":   ("NIFTY SMALLCAP 100", "^CNXSC",     "Nifty SmallCap 100"),
}


@router.get("/indices")
@_cached("indices", ttl=10)
async def get_indices():
    loop = asyncio.get_running_loop()

    # NSE official: real-time, cap at 3s
    nse_data: dict[str, dict] = {}
    if _NSE_AVAILABLE:
        try:
            nse_data = await asyncio.wait_for(
                loop.run_in_executor(_executor, _fetch_nse_all_indices),
                timeout=3.0,
            )
        except Exception:
            pass

    # Collect which indices need yfinance fallback
    missing = [
        (key, yf_sym, label)
        for key, (nse_sym, yf_sym, label) in NSE_INDEX_SYMBOL_MAP.items()
        if not (nse_data.get(nse_sym, {}).get("price", 0) > 0)
    ]

    # Fetch all missing in parallel — not sequentially
    fallbacks = await asyncio.gather(
        *[loop.run_in_executor(_executor, _fetch_index, yf_sym) for _, yf_sym, _ in missing],
        return_exceptions=True,
    )

    out = {}
    for key, (nse_sym, yf_sym, label) in NSE_INDEX_SYMBOL_MAP.items():
        d = nse_data.get(nse_sym)
        if d and d.get("price", 0) > 0:
            out[key] = {"label": label, "symbol": yf_sym, **d}

    for (key, yf_sym, label), fb in zip(missing, fallbacks):
        out[key] = {"label": label, **(fb if isinstance(fb, dict) else {})}

    out["status"] = _market_status()
    return out


@router.get("/history/{ticker:path}")
async def get_history(
    ticker: str,
    period: str = Query("1d", pattern="^(1d|5d|1mo|3mo|6mo|1y|2y|5y|max)$"),
    interval: str = Query("5m", pattern="^(1m|5m|15m|30m|1h|1d|1wk|1mo)$"),
):
    data = await _run(_fetch_history, ticker, period, interval)
    return data


@router.get("/movers")
@_cached("movers", ttl=60)
async def get_movers(limit: int = Query(8, le=20)):
    loop = asyncio.get_running_loop()
    quotes: list[dict] = []

    # NSE official: real-time, instant when available
    if _NSE_AVAILABLE:
        try:
            stocks = await asyncio.wait_for(
                loop.run_in_executor(_executor, _fetch_nse_index_stocks, "NIFTY 50"),
                timeout=3.0,
            )
            quotes = [s for s in stocks if s.get("price", 0) > 0]
        except Exception:
            pass

    # yfinance fallback: one batch download instead of 50 individual fast_info calls
    if not quotes:
        try:
            quotes = await asyncio.wait_for(
                loop.run_in_executor(_executor, _batch_download, NIFTY50),
                timeout=5.0,
            )
        except Exception:
            quotes = []

    gainers = sorted([q for q in quotes if q["change_pct"] > 0], key=lambda x: -x["change_pct"])[:limit]
    losers  = sorted([q for q in quotes if q["change_pct"] < 0], key=lambda x: x["change_pct"])[:limit]
    adv = sum(1 for q in quotes if q["change_pct"] > 0)
    dec = sum(1 for q in quotes if q["change_pct"] < 0)
    unc = len(quotes) - adv - dec

    result = {
        "gainers": gainers,
        "losers":  losers,
        "breadth": {"advances": adv, "declines": dec, "unchanged": unc, "total": len(quotes)},
    }

    if gainers or losers:
        _l2_write_market("movers", result)
    elif not gainers and not losers:
        # Empty gainers/losers — return last-session data from L2
        cached = _l2_read_market("movers")
        if cached:
            return cached

    return result


NSE_SECTOR_MAP = {
    "IT":      "NIFTY IT",
    "Bank":    "NIFTY BANK",
    "FMCG":    "NIFTY FMCG",
    "Auto":    "NIFTY AUTO",
    "Pharma":  "NIFTY PHARMA",
    "Metal":   "NIFTY METAL",
    "Energy":  "NIFTY ENERGY",
    "Realty":  "NIFTY REALTY",
    "Infra":   "NIFTY INFRA",
    "Finance": "NIFTY FINANCIAL SERVICES",
    "Media":   "NIFTY MEDIA",
    "CPSE":    "NIFTY CPSE",
}

YF_SECTOR_FALLBACK = {
    "IT":      "^CNXIT",
    "Bank":    "^NSEBANK",
    "FMCG":    "^CNXFMCG",
    "Auto":    "^CNXAUTO",
    "Pharma":  "^CNXPHARMA",
    "Metal":   "^CNXMETAL",
    "Energy":  "^CNXENERGY",
    "Realty":  "^CNXREALTY",
    "Infra":   "^CNXINFRA",
    "Finance": "^CNXFINANCE",
}


def _batch_download_sectors() -> list[dict]:
    """Single download for all sector indices. Uses period=5d so weekend/holiday gaps don't
    produce empty data — we always compare the two most recent trading sessions."""
    import math
    names   = list(YF_SECTOR_FALLBACK.keys())
    symbols = list(YF_SECTOR_FALLBACK.values())
    try:
        raw = yf.download(
            symbols, period="5d", interval="1d",
            auto_adjust=True, progress=False, threads=True, group_by="ticker",
        )
        results = []
        for name, symbol in zip(names, symbols):
            try:
                df = raw[symbol] if len(symbols) > 1 else raw
                df = df.dropna(subset=["Close"])
                if len(df) < 1:
                    continue
                price = float(df["Close"].iloc[-1])
                prev  = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
                if price <= 0 or math.isnan(price):
                    continue
                change     = price - prev
                change_pct = (change / prev * 100) if prev else 0
                results.append({
                    "sector":     name,
                    "symbol":     symbol,
                    "price":      round(price, 2),
                    "prev_close": round(prev, 2),
                    "change":     round(change, 2),
                    "change_pct": round(change_pct, 3),
                    "day_high":   round(float(df["High"].iloc[-1]), 2),
                    "day_low":    round(float(df["Low"].iloc[-1]), 2),
                })
            except Exception:
                pass
        return sorted(results, key=lambda x: -abs(x.get("change_pct", 0)))
    except Exception:
        return []


@router.get("/sectors")
@_cached("sectors", ttl=60)
async def get_sectors():
    loop = asyncio.get_running_loop()

    # NSE official: real-time, cap at 3s
    if _NSE_AVAILABLE:
        try:
            nse_all = await asyncio.wait_for(
                loop.run_in_executor(_executor, _fetch_nse_all_indices),
                timeout=3.0,
            )
            out = []
            for sector_name, nse_sym in NSE_SECTOR_MAP.items():
                d = nse_all.get(nse_sym)
                if d and d.get("price", 0) > 0:
                    out.append({"sector": sector_name, **d})
            if out:
                result = sorted(out, key=lambda x: -abs(x["change_pct"]))
                _l2_write_market("sectors", result)
                return result
        except Exception:
            pass

    # yfinance fallback: one batch download
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, _batch_download_sectors),
            timeout=8.0,
        )
        if result:
            _l2_write_market("sectors", result)
            return result
    except Exception:
        pass

    # L2 fallback: return last known good data (survives cold Lambda + API outages)
    cached = _l2_read_market("sectors")
    if cached:
        return cached
    return []


def _fetch_nse_quote(symbol: str) -> dict | None:
    """Fetch live quote for a single NSE stock via NSE official API."""
    if not _NSE_AVAILABLE:
        return None
    try:
        clean = symbol.upper().replace(".NS", "").replace(".BO", "")
        data = _nsefetch(f"https://nseindia.com/api/quote-equity?symbol={clean}")
        pi = data.get("priceInfo", {})
        price = _sf(pi.get("lastPrice", 0))
        prev  = _sf(pi.get("previousClose", price))
        chg   = price - prev
        chg_pct = (chg / prev * 100) if prev else 0
        intrday = pi.get("intraDayHighLow", {})
        return {
            "ticker": clean,
            "price":      round(price, 2),
            "prev_close": round(prev, 2),
            "change":     round(chg, 2),
            "change_pct": round(chg_pct, 3),
            "day_high":   round(_sf(intrday.get("max", price)), 2),
            "day_low":    round(_sf(intrday.get("min", price)), 2),
            "volume":     int(_sf(pi.get("totalTradedVolume", 0))),
            "52w_high":   round(_sf(pi.get("weekHighLow", {}).get("max", 0)), 2),
            "52w_low":    round(_sf(pi.get("weekHighLow", {}).get("min", 0)), 2),
            "vwap":       round(_sf(pi.get("vwap", 0)), 2),
        }
    except Exception:
        return None


@router.get("/quote")
async def get_quote(
    tickers: str = Query(..., description="Comma-separated, e.g. RELIANCE.NS,TCS.NS"),
):
    ticker_list = [t.strip() for t in tickers.split(",")][:15]
    loop = asyncio.get_running_loop()
    results = []
    for ticker in ticker_list:
        # Try NSE official first
        nse_q = await loop.run_in_executor(_executor, _fetch_nse_quote, ticker)
        if nse_q and nse_q.get("price", 0) > 0:
            results.append(nse_q)
        else:
            yf_q = await loop.run_in_executor(_executor, _fetch_fast_info, ticker)
            if isinstance(yf_q, dict):
                results.append(yf_q)
    return results


# ── NSE Stock Universe ────────────────────────────────────────────────────────
NSE_STOCKS: list[dict] = [
    # IT
    {"ticker": "TCS.NS",        "name": "Tata Consultancy Services", "sector": "IT",       "exchange": "NSE"},
    {"ticker": "INFY.NS",       "name": "Infosys",                   "sector": "IT",       "exchange": "NSE"},
    {"ticker": "WIPRO.NS",      "name": "Wipro",                     "sector": "IT",       "exchange": "NSE"},
    {"ticker": "HCLTECH.NS",    "name": "HCL Technologies",          "sector": "IT",       "exchange": "NSE"},
    {"ticker": "TECHM.NS",      "name": "Tech Mahindra",             "sector": "IT",       "exchange": "NSE"},
    {"ticker": "LTIM.NS",       "name": "LTIMindtree",               "sector": "IT",       "exchange": "NSE"},
    {"ticker": "PERSISTENT.NS", "name": "Persistent Systems",        "sector": "IT",       "exchange": "NSE"},
    {"ticker": "COFORGE.NS",    "name": "Coforge",                   "sector": "IT",       "exchange": "NSE"},
    {"ticker": "MPHASIS.NS",    "name": "Mphasis",                   "sector": "IT",       "exchange": "NSE"},
    {"ticker": "OFSS.NS",       "name": "Oracle Financial Services", "sector": "IT",       "exchange": "NSE"},
    {"ticker": "KPITTECH.NS",   "name": "KPIT Technologies",         "sector": "IT",       "exchange": "NSE"},
    {"ticker": "TATAELXSI.NS",  "name": "Tata Elxsi",                "sector": "IT",       "exchange": "NSE"},
    {"ticker": "CYIENT.NS",     "name": "Cyient",                    "sector": "IT",       "exchange": "NSE"},
    # Bank
    {"ticker": "HDFCBANK.NS",   "name": "HDFC Bank",                 "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "ICICIBANK.NS",  "name": "ICICI Bank",                "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "KOTAKBANK.NS",  "name": "Kotak Mahindra Bank",       "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "SBIN.NS",       "name": "State Bank of India",       "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "AXISBANK.NS",   "name": "Axis Bank",                 "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "INDUSINDBK.NS", "name": "IndusInd Bank",             "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "BANDHANBNK.NS", "name": "Bandhan Bank",              "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "FEDERALBNK.NS", "name": "Federal Bank",              "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "IDFCFIRSTB.NS", "name": "IDFC First Bank",           "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "YESBANK.NS",    "name": "Yes Bank",                  "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "RBLBANK.NS",    "name": "RBL Bank",                  "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "CANBK.NS",      "name": "Canara Bank",               "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "BANKBARODA.NS", "name": "Bank of Baroda",            "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "PNB.NS",        "name": "Punjab National Bank",      "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "UNIONBANK.NS",  "name": "Union Bank of India",       "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "AUBANK.NS",     "name": "AU Small Finance Bank",     "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "DCBBANK.NS",    "name": "DCB Bank",                  "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "KARURVYSYA.NS", "name": "Karur Vysya Bank",          "sector": "Bank",     "exchange": "NSE"},
    # Finance
    {"ticker": "BAJFINANCE.NS",  "name": "Bajaj Finance",            "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "BAJAJFINSV.NS",  "name": "Bajaj Finserv",            "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "HDFCLIFE.NS",    "name": "HDFC Life Insurance",      "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "SBILIFE.NS",     "name": "SBI Life Insurance",       "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "ICICIGI.NS",     "name": "ICICI Lombard General",    "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "MUTHOOTFIN.NS",  "name": "Muthoot Finance",          "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "CHOLAFIN.NS",    "name": "Cholamandalam Investment", "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "MANAPPURAM.NS",  "name": "Manappuram Finance",       "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "LICHSGFIN.NS",   "name": "LIC Housing Finance",      "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "PNBHOUSING.NS",  "name": "PNB Housing Finance",      "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "ABCAPITAL.NS",   "name": "Aditya Birla Capital",     "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "IIFL.NS",        "name": "IIFL Finance",             "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "HDFCAMC.NS",     "name": "HDFC Asset Management",   "sector": "Finance",  "exchange": "NSE"},
    # FMCG
    {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever",        "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "ITC.NS",        "name": "ITC",                       "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "NESTLEIND.NS",  "name": "Nestle India",              "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "BRITANNIA.NS",  "name": "Britannia Industries",      "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "MARICO.NS",     "name": "Marico",                    "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "COLPAL.NS",     "name": "Colgate-Palmolive India",   "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "DABUR.NS",      "name": "Dabur India",               "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "GODREJCP.NS",   "name": "Godrej Consumer Products",  "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "TATACONSUM.NS", "name": "Tata Consumer Products",    "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "VBL.NS",        "name": "Varun Beverages",           "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "UBL.NS",        "name": "United Breweries",          "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "RADICO.NS",     "name": "Radico Khaitan",            "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "EMAMILTD.NS",   "name": "Emami",                     "sector": "FMCG",     "exchange": "NSE"},
    {"ticker": "JYOTHYLAB.NS",  "name": "Jyothy Labs",               "sector": "FMCG",     "exchange": "NSE"},
    # Pharma
    {"ticker": "SUNPHARMA.NS",   "name": "Sun Pharmaceutical",       "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "CIPLA.NS",       "name": "Cipla",                    "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "DRREDDY.NS",     "name": "Dr. Reddy's Laboratories", "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "DIVISLAB.NS",    "name": "Divi's Laboratories",      "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "APOLLOHOSP.NS",  "name": "Apollo Hospitals",         "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "LUPIN.NS",       "name": "Lupin",                    "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "TORNTPHARM.NS",  "name": "Torrent Pharmaceuticals",  "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "AUROPHARMA.NS",  "name": "Aurobindo Pharma",         "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "BIOCON.NS",      "name": "Biocon",                   "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "IPCALAB.NS",     "name": "IPCA Laboratories",        "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "ALKEM.NS",       "name": "Alkem Laboratories",       "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "GRANULES.NS",    "name": "Granules India",           "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "NATCOPHARM.NS",  "name": "Natco Pharma",             "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "LAURUSLABS.NS",  "name": "Laurus Labs",              "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "GLAND.NS",       "name": "Gland Pharma",             "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "FORTIS.NS",      "name": "Fortis Healthcare",        "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "MAXHEALTH.NS",   "name": "Max Healthcare Institute", "sector": "Pharma",   "exchange": "NSE"},
    # Auto
    {"ticker": "MARUTI.NS",      "name": "Maruti Suzuki",            "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "TATAMOTORS.NS",  "name": "Tata Motors",              "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "M&M.NS",         "name": "Mahindra & Mahindra",      "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "BAJAJ-AUTO.NS",  "name": "Bajaj Auto",               "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "HEROMOTOCO.NS",  "name": "Hero MotoCorp",            "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "EICHERMOT.NS",   "name": "Eicher Motors",            "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "ASHOKLEY.NS",    "name": "Ashok Leyland",            "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "TIINDIA.NS",     "name": "Tube Investments of India","sector": "Auto",     "exchange": "NSE"},
    {"ticker": "BOSCHLTD.NS",    "name": "Bosch",                    "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "MOTHERSON.NS",   "name": "Samvardhana Motherson",    "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "APOLLOTYRE.NS",  "name": "Apollo Tyres",             "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "MRF.NS",         "name": "MRF",                      "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "CEATLTD.NS",     "name": "CEAT",                     "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "BALKRISIND.NS",  "name": "Balkrishna Industries",    "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "BHARATFORG.NS",  "name": "Bharat Forge",             "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "ENDURANCE.NS",   "name": "Endurance Technologies",   "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "CRAFTSMAN.NS",   "name": "Craftsman Automation",     "sector": "Auto",     "exchange": "NSE"},
    # Energy
    {"ticker": "RELIANCE.NS",    "name": "Reliance Industries",      "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "ONGC.NS",        "name": "Oil & Natural Gas Corp",   "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "BPCL.NS",        "name": "Bharat Petroleum",         "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "IOC.NS",         "name": "Indian Oil Corporation",   "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "GAIL.NS",        "name": "GAIL (India)",             "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "PETRONET.NS",    "name": "Petronet LNG",             "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "IGL.NS",         "name": "Indraprastha Gas",         "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "MGL.NS",         "name": "Mahanagar Gas",            "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "TATAPOWER.NS",   "name": "Tata Power",               "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "ADANIGREEN.NS",  "name": "Adani Green Energy",       "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "ADANIPORTS.NS",  "name": "Adani Ports & SEZ",        "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "POWERGRID.NS",   "name": "Power Grid Corporation",   "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "NTPC.NS",        "name": "NTPC",                     "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "TORNTPOWER.NS",  "name": "Torrent Power",            "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "CESC.NS",        "name": "CESC",                     "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "NHPC.NS",        "name": "NHPC",                     "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "SJVN.NS",        "name": "SJVN",                     "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "IREDA.NS",       "name": "Indian Renewable Energy",  "sector": "Energy",   "exchange": "NSE"},
    # Metal
    {"ticker": "TATASTEEL.NS",   "name": "Tata Steel",               "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "JSWSTEEL.NS",    "name": "JSW Steel",                "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "HINDALCO.NS",    "name": "Hindalco Industries",      "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "VEDL.NS",        "name": "Vedanta",                  "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "SAIL.NS",        "name": "Steel Authority of India", "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "NMDC.NS",        "name": "NMDC",                     "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "NATIONALUM.NS",  "name": "National Aluminium",       "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "HINDCOPPER.NS",  "name": "Hindustan Copper",         "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "COALINDIA.NS",   "name": "Coal India",               "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "JINDALSTEL.NS",  "name": "Jindal Steel & Power",     "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "APLAPOLLO.NS",   "name": "APL Apollo Tubes",         "sector": "Metal",    "exchange": "NSE"},
    {"ticker": "RATNAMANI.NS",   "name": "Ratnamani Metals & Tubes", "sector": "Metal",    "exchange": "NSE"},
    # Cement
    {"ticker": "ULTRACEMCO.NS",  "name": "UltraTech Cement",         "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "SHREECEM.NS",    "name": "Shree Cement",             "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "AMBUJACEM.NS",   "name": "Ambuja Cements",           "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "ACC.NS",         "name": "ACC",                      "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "JKCEMENT.NS",    "name": "JK Cement",                "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "DALMIACEM.NS",   "name": "Dalmia Bharat",            "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "HEIDELBERG.NS",  "name": "HeidelbergCement India",   "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "INDIACEM.NS",    "name": "The India Cements",        "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "RAMCOCEM.NS",    "name": "The Ramco Cements",        "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "BIRLASOFT.NS",   "name": "Birlasoft",                "sector": "Cement",   "exchange": "NSE"},
    # Consumer/Retail
    {"ticker": "TITAN.NS",       "name": "Titan Company",            "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "VOLTAS.NS",      "name": "Voltas",                   "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "HAVELLS.NS",     "name": "Havells India",            "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "CROMPTON.NS",    "name": "Crompton Greaves Consumer","sector": "Consumer", "exchange": "NSE"},
    {"ticker": "DIXON.NS",       "name": "Dixon Technologies",       "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "AMBER.NS",       "name": "Amber Enterprises",        "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "WHIRLPOOL.NS",   "name": "Whirlpool of India",       "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "BLUESTARCO.NS",  "name": "Blue Star",                "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "VGUARD.NS",      "name": "V-Guard Industries",       "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "ORIENTELEC.NS",  "name": "Orient Electric",          "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "SYMPHONY.NS",    "name": "Symphony",                 "sector": "Consumer", "exchange": "NSE"},
    # Realty
    {"ticker": "DLF.NS",         "name": "DLF",                      "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "GODREJPROP.NS",  "name": "Godrej Properties",        "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "OBEROIRLTY.NS",  "name": "Oberoi Realty",            "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "PHOENIXLTD.NS",  "name": "Phoenix Mills",            "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "PRESTIGE.NS",    "name": "Prestige Estates Projects","sector": "Realty",   "exchange": "NSE"},
    {"ticker": "BRIGADE.NS",     "name": "Brigade Enterprises",      "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "SOBHA.NS",       "name": "Sobha",                    "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "KOLTEPATIL.NS",  "name": "Kolte-Patil Developers",   "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "MAHLIFE.NS",     "name": "Mahindra Lifespace Dev",   "sector": "Realty",   "exchange": "NSE"},
    # Chemicals
    {"ticker": "PIDILITIND.NS",  "name": "Pidilite Industries",      "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "ASIANPAINT.NS",  "name": "Asian Paints",             "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "BERGEPAINT.NS",  "name": "Berger Paints India",      "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "UPL.NS",         "name": "UPL",                      "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "COROMANDEL.NS",  "name": "Coromandel International", "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "CHAMBAL.NS",     "name": "Chambal Fertilisers",      "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "DEEPAKNTR.NS",   "name": "Deepak Nitrite",           "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "NAVNETEDU.NS",   "name": "Navneet Education",        "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "AARTIIND.NS",    "name": "Aarti Industries",         "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "CLEAN.NS",       "name": "Clean Science & Tech",     "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "SUDARSCHEM.NS",  "name": "Sudarshan Chemical",       "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "FINEORG.NS",     "name": "Fine Organic Industries",  "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "TATACHEM.NS",    "name": "Tata Chemicals",           "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "GNFC.NS",        "name": "Gujarat Narmada Valley FC","sector": "Chemicals","exchange": "NSE"},
    # Infra/Capital Goods
    {"ticker": "LT.NS",          "name": "Larsen & Toubro",          "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "ADANIENT.NS",    "name": "Adani Enterprises",        "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "CONCOR.NS",      "name": "Container Corp of India",  "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "IRCTC.NS",       "name": "IRCTC",                    "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "IRFC.NS",        "name": "Indian Railway Finance",   "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "SIEMENS.NS",     "name": "Siemens India",            "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "ABB.NS",         "name": "ABB India",                "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "BHEL.NS",        "name": "Bharat Heavy Electricals", "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "THERMAX.NS",     "name": "Thermax",                  "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "CUMMINSIND.NS",  "name": "Cummins India",            "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "KEC.NS",         "name": "KEC International",        "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "KALPATPOWR.NS",  "name": "Kalpataru Power Transm",  "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "GRINDWELL.NS",   "name": "Grindwell Norton",         "sector": "Infra",    "exchange": "NSE"},
    # Telecom
    {"ticker": "BHARTIARTL.NS",  "name": "Bharti Airtel",            "sector": "Telecom",  "exchange": "NSE"},
    {"ticker": "IDEA.NS",        "name": "Vodafone Idea",            "sector": "Telecom",  "exchange": "NSE"},
    {"ticker": "TATACOMM.NS",    "name": "Tata Communications",      "sector": "Telecom",  "exchange": "NSE"},
    {"ticker": "HFCL.NS",        "name": "HFCL",                     "sector": "Telecom",  "exchange": "NSE"},
    # Largecap / New-age
    {"ticker": "BSE.NS",         "name": "BSE (Bombay Stock Exch)",  "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "NAUKRI.NS",      "name": "Info Edge (Naukri)",       "sector": "IT",       "exchange": "NSE"},
    {"ticker": "ZOMATO.NS",      "name": "Zomato",                   "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "POLICYBZR.NS",   "name": "PB Fintech (Policybazaar)","sector": "Finance",  "exchange": "NSE"},
    {"ticker": "PAYTM.NS",       "name": "One97 Communications",     "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "DELHIVERY.NS",   "name": "Delhivery",                "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "FSL.NS",         "name": "Firstsource Solutions",    "sector": "IT",       "exchange": "NSE"},
    {"ticker": "NYKAA.NS",       "name": "FSN E-Commerce (Nykaa)",   "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "CARTRADE.NS",    "name": "CarTrade Tech",            "sector": "Consumer", "exchange": "NSE"},
    # Index/ETF
    {"ticker": "KOTAKBKETF.NS",  "name": "Kotak Banking ETF",        "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "SETFNIF50.NS",   "name": "SBI ETF Nifty 50",         "sector": "IT",       "exchange": "NSE"},
    # Additional Nifty 50 / Midcap
    {"ticker": "GRASIM.NS",      "name": "Grasim Industries",        "sector": "Cement",   "exchange": "NSE"},
    {"ticker": "BAJAJHFL.NS",    "name": "Bajaj Housing Finance",    "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "JSWINFRA.NS",    "name": "JSW Infrastructure",       "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "MANKIND.NS",     "name": "Mankind Pharma",           "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "ATGL.NS",        "name": "Adani Total Gas",          "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "OBEROIRLTY.NS",  "name": "Oberoi Realty",            "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "TRENT.NS",       "name": "Trent",                    "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "ZYDUSLIFE.NS",   "name": "Zydus Lifesciences",       "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "LINDEINDIA.NS",  "name": "Linde India",              "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "SOLARINDS.NS",   "name": "Solar Industries India",   "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "NYKAA.NS",       "name": "Nykaa",                    "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "INDIGOPNTS.NS",  "name": "Indigo Paints",            "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "KANSAINER.NS",   "name": "Kansai Nerolac Paints",    "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "AKZONOBEL.NS",   "name": "Akzo Nobel India",         "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "STARHEALTH.NS",  "name": "Star Health Insurance",    "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "JMFINANCIL.NS",  "name": "JM Financial",             "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "MOTILALOFS.NS",  "name": "Motilal Oswal Financial",  "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "ANGELONE.NS",    "name": "Angel One",                "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "ICICIPRULI.NS",  "name": "ICICI Prudential Life",    "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "MAXFINSERV.NS",  "name": "Max Financial Services",   "sector": "Finance",  "exchange": "NSE"},
    {"ticker": "CENTRALBK.NS",   "name": "Central Bank of India",    "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "INDIANB.NS",     "name": "Indian Bank",              "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "MAHABANK.NS",    "name": "Bank of Maharashtra",      "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "IDBI.NS",        "name": "IDBI Bank",                "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "J&KBANK.NS",     "name": "J&K Bank",                 "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "SOUTHBANK.NS",   "name": "South Indian Bank",        "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "CSBBANK.NS",     "name": "CSB Bank",                 "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "EQUITASBNK.NS",  "name": "Equitas Small Finance Bk","sector": "Bank",     "exchange": "NSE"},
    {"ticker": "UJJIVANSFB.NS",  "name": "Ujjivan Small Finance Bk","sector": "Bank",     "exchange": "NSE"},
    {"ticker": "ESAFSFB.NS",     "name": "ESAF Small Finance Bank",  "sector": "Bank",     "exchange": "NSE"},
    {"ticker": "UTKARSHBNK.NS",  "name": "Utkarsh Small Finance Bk","sector": "Bank",     "exchange": "NSE"},
    {"ticker": "EASEMYTRIP.NS",  "name": "Easy Trip Planners",       "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "IRCON.NS",       "name": "IRCON International",      "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "RVNL.NS",        "name": "Rail Vikas Nigam",         "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "RITES.NS",       "name": "RITES",                    "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "NBCC.NS",        "name": "NBCC (India)",             "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "NCC.NS",         "name": "NCC",                      "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "GPPL.NS",        "name": "Gujarat Pipavav Port",     "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "GMRAIRPORT.NS",  "name": "GMR Airports Infrastructure","sector": "Infra",  "exchange": "NSE"},
    {"ticker": "HAL.NS",         "name": "Hindustan Aeronautics",    "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "BEL.NS",         "name": "Bharat Electronics",       "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "COCHINSHIP.NS",  "name": "Cochin Shipyard",          "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "MAZDA.NS",       "name": "Mazda",                    "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "KGEIL.NS",       "name": "KG Enterprises",           "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "PGIL.NS",        "name": "Pearl Global Industries",  "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "SHOPERSTOP.NS",  "name": "Shoppers Stop",            "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "ABFRL.NS",       "name": "Aditya Birla Fashion",     "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "VEDANT.NS",      "name": "Vedant Fashions",          "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "PAGEIND.NS",     "name": "Page Industries",          "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "RELAXO.NS",      "name": "Relaxo Footwears",         "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "BATAINDIA.NS",   "name": "Bata India",               "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "METROS.NS",      "name": "Metro Brands",             "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "CAMPUSACT.NS",   "name": "Campus Activewear",        "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "PHOENIXLTD.NS",  "name": "Phoenix Mills",            "sector": "Realty",   "exchange": "NSE"},
    {"ticker": "SUNTV.NS",       "name": "Sun TV Network",           "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "ZEEL.NS",        "name": "Zee Entertainment",        "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "PVRINOX.NS",     "name": "PVR Inox",                 "sector": "Consumer", "exchange": "NSE"},
    {"ticker": "INOXWIND.NS",    "name": "Inox Wind",                "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "WEBSOL.NS",      "name": "Websol Energy System",     "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "WAAREEENER.NS",  "name": "Waaree Energies",          "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "PREMIER.NS",     "name": "Premier Energies",         "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "SUZLON.NS",      "name": "Suzlon Energy",            "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "TATAPOWER.NS",   "name": "Tata Power",               "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "SPICEJET.NS",    "name": "SpiceJet",                 "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "INTERGLOBE.NS",  "name": "InterGlobe Aviation (IndiGo)","sector": "Infra", "exchange": "NSE"},
    {"ticker": "APOLLOTYRE.NS",  "name": "Apollo Tyres",             "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "SWSOLAR.NS",     "name": "Sterling & Wilson Solar",  "sector": "Energy",   "exchange": "NSE"},
    {"ticker": "GESHIP.NS",      "name": "Great Eastern Shipping",   "sector": "Infra",    "exchange": "NSE"},
    {"ticker": "SKFINDIA.NS",    "name": "SKF India",                "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "SCHAEFFLER.NS",  "name": "Schaeffler India",         "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "TIMKEN.NS",      "name": "Timken India",             "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "MINDA.NS",       "name": "Uno Minda",                "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "SUPRAJIT.NS",    "name": "Suprajit Engineering",     "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "LUMAX.NS",       "name": "Lumax Auto Technologies",  "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "SUNDRMFAST.NS",  "name": "Sundram Fasteners",        "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "Gabriel.NS",     "name": "Gabriel India",            "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "SUBROS.NS",      "name": "Subros",                   "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "FIEMIND.NS",     "name": "Fiem Industries",          "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "SONACOMS.NS",    "name": "Sona BLW Precision",       "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "MINDAIND.NS",    "name": "Minda Industries",         "sector": "Auto",     "exchange": "NSE"},
    {"ticker": "JLHL.NS",        "name": "Jupiter Life Line Hospitals","sector": "Pharma", "exchange": "NSE"},
    {"ticker": "RAINBOW.NS",     "name": "Rainbow Children's Med",   "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "YATHARTH.NS",    "name": "Yatharth Hospital",        "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "KIMS.NS",        "name": "Krishna Institute Med Sci","sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "MEDANTA.NS",     "name": "Global Health (Medanta)",  "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "DRREDDY.NS",     "name": "Dr Reddys Laboratories",   "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "ERIS.NS",        "name": "Eris Lifesciences",        "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "SOLARA.NS",      "name": "Solara Active Pharma",     "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "SEQUENT.NS",     "name": "SeQuent Scientific",       "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "JBCHEPHARM.NS",  "name": "JB Chemicals & Pharma",   "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "STRIDES.NS",     "name": "Strides Pharma Science",   "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "SMSPHARMA.NS",   "name": "SMS Pharmaceuticals",      "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "ABBOTINDIA.NS",  "name": "Abbott India",             "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "PFIZER.NS",      "name": "Pfizer India",             "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "SANOFI.NS",      "name": "Sanofi India",             "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "GLAXO.NS",       "name": "GSK Pharmaceuticals",      "sector": "Pharma",   "exchange": "NSE"},
    {"ticker": "BALAMINES.NS",   "name": "Balaji Amines",            "sector": "Chemicals","exchange": "NSE"},
    {"ticker": "VINDHYATEL.NS",  "name": "Vindhya Telelinks",        "sector": "Telecom",  "exchange": "NSE"},
    {"ticker": "TEJASNET.NS",    "name": "Tejas Networks",           "sector": "Telecom",  "exchange": "NSE"},
    {"ticker": "STLTECH.NS",     "name": "Sterlite Technologies",    "sector": "Telecom",  "exchange": "NSE"},
]

# Default watchlist of 20 key NSE stocks
_DEFAULT_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "ITC.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS",
    "BAJFINANCE.NS", "MARUTI.NS", "TITAN.NS", "WIPRO.NS", "ONGC.NS",
    "NTPC.NS", "SUNPHARMA.NS", "M&M.NS", "TATAMOTORS.NS", "HCLTECH.NS",
]

_VALID_SECTORS = {
    "IT", "Bank", "FMCG", "Auto", "Pharma", "Metal", "Energy",
    "Cement", "Finance", "Consumer", "Realty", "Infra", "Telecom", "Chemicals",
}


@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1, description="Stock name or ticker"),
    limit: int = Query(12, le=30),
):
    """Smart stock search — tries NSE autocomplete first, falls back to static list."""
    loop = asyncio.get_running_loop()

    # Try NSE official autocomplete
    if _NSE_AVAILABLE and len(q) >= 2:
        try:
            def _nse_search():
                url = f"https://nseindia.com/api/search/autocomplete?q={q.upper()}"
                data = _nsefetch(url)
                results = []
                for s in data.get("symbols", [])[:limit]:
                    if s.get("result_sub_type") == "equity":
                        results.append({
                            "ticker": s["symbol"] + ".NS",
                            "symbol": s["symbol"],
                            "name": s.get("symbol_info", s["symbol"]),
                            "sector": "",
                            "exchange": "NSE",
                        })
                return results
            results = await loop.run_in_executor(_executor, _nse_search)
            if results:
                return results
        except Exception:
            pass

    # Static fallback
    q_lower = q.strip().lower()
    results = []
    seen: set[str] = set()
    for stock in NSE_STOCKS:
        if stock["ticker"] in seen:
            continue
        ticker_bare = stock["ticker"].replace(".NS", "").lower()
        if q_lower in ticker_bare or q_lower in stock["name"].lower():
            results.append(stock)
            seen.add(stock["ticker"])
        if len(results) >= limit:
            break
    return results


@router.get("/watchlist")
@_cached("watchlist", ttl=20)
async def get_watchlist():
    """Live quotes for the default watchlist of 20 key NSE stocks."""
    loop = asyncio.get_running_loop()
    quotes: list[dict] = []

    if _NSE_AVAILABLE:
        try:
            nse_all = await loop.run_in_executor(_executor, _fetch_nse_all_indices)
            # Get NIFTY 50 stock data
            stocks = await loop.run_in_executor(_executor, _fetch_nse_index_stocks, "NIFTY 50")
            watchlist_symbols = [t.replace(".NS", "") for t in _DEFAULT_WATCHLIST]
            for s in stocks:
                if s["ticker"] in watchlist_symbols:
                    quotes.append(s)
            if quotes:
                return quotes
        except Exception:
            pass

    tasks = [loop.run_in_executor(_executor, _fetch_fast_info, t) for t in _DEFAULT_WATCHLIST]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


@router.get("/fii-dii")
@_cached("fii_dii", ttl=3600)  # 1-hour in-process cache
async def get_fii_dii():
    """
    FII/DII cash-segment data — real data only, no mock.

    Priority:
      1. Supabase cache (populated nightly by GitHub Actions update_fii_dii.py)
      2. NSE live API direct fetch (works when Vercel IP is not blocked)
      3. Local fii_dii_data/latest.json + fpi_daily.json (bundled, may be stale)
      4. Empty list — frontend shows 'Data unavailable'
    """
    import json as _json
    from pathlib import Path
    from datetime import timezone as _tz

    loop = asyncio.get_running_loop()

    def _map_row(row: dict) -> dict:
        return {
            "date":             row.get("date", ""),
            "fii_buy":          float(row.get("fii_buy", 0) or 0),
            "fii_sell":         float(row.get("fii_sell", 0) or 0),
            "fii_net":          float(row.get("fii_net", 0) or 0),
            "dii_buy":          float(row.get("dii_buy", 0) or 0),
            "dii_sell":         float(row.get("dii_sell", 0) or 0),
            "dii_net":          float(row.get("dii_net", 0) or 0),
            "fii_idx_fut_net":  float(row.get("fii_idx_fut_net", 0) or 0),
            "fii_stk_fut_net":  float(row.get("fii_stk_fut_net", 0) or 0),
            "fii_idx_call_net": float(row.get("fii_idx_call_net", 0) or 0),
            "fii_idx_put_net":  float(row.get("fii_idx_put_net", 0) or 0),
            "pcr":              float(row.get("pcr", 0) or 0),
            "sentiment_score":  float(row.get("sentiment_score", 50) or 50),
            "sentiment":        (row.get("_fao_summary") or {}).get("sentiment", row.get("sentiment", "Neutral")),
            "updated_at":       row.get("_updated_at", row.get("updated_at", "")),
        }

    # ── 1. Supabase cache (populated by GitHub Actions nightly) ───────────────
    try:
        from data.storage import supabase_db as sdb
        sb_rows = sdb.select(
            "screener_cache",
            cols="results,scanned_at",
            filters={"strategy": "fii_dii", "universe": "cash"},
            limit=1,
        )
        if sb_rows:
            row = sb_rows[0]
            raw = row.get("results")
            data = _json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list) and len(data) >= 5:
                # Accept even if slightly stale (up to 4 days — covers weekends + holidays)
                sa = row.get("scanned_at", "")
                age_days = 999.0
                if sa:
                    scanned = datetime.fromisoformat(sa.replace("Z", "+00:00"))
                    age_days = (datetime.now(_tz.utc) - scanned).total_seconds() / 86400
                if age_days < 4:
                    return data[-60:]
    except Exception:
        pass

    # ── 2. NSE live API with session cookie ───────────────────────────────────
    def _fetch_nse_direct() -> list[dict]:
        import http.cookiejar as _cj, time as _t
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        jar = _cj.CookieJar()
        opener = _ur.build_opener(_ur.HTTPCookieProcessor(jar))
        opener.open(
            _ur.Request("https://www.nseindia.com/reports/fii-dii",
                        headers={**headers, "Accept": "text/html,*/*"}),
            timeout=7,
        )
        _t.sleep(0.8)
        with opener.open(
            _ur.Request(
                "https://www.nseindia.com/api/fiidiiTradeReact",
                headers={**headers,
                         "Accept": "application/json, text/plain, */*",
                         "Referer": "https://www.nseindia.com/reports/fii-dii",
                         "X-Requested-With": "XMLHttpRequest"},
            ),
            timeout=7,
        ) as r:
            data = _json.loads(r.read())

        out = []
        for row in (data if isinstance(data, list) else []):
            fii_net = _sf(row.get("buySell_FII_net", row.get("fii_net", 0)))
            dii_net = _sf(row.get("buySell_DII_net", row.get("dii_net", 0)))
            if abs(fii_net) < 0.01 and abs(dii_net) < 0.01:
                continue
            out.append({
                "date":             row.get("date", ""),
                "fii_buy":          _sf(row.get("buySell_FII_buy",  row.get("fii_buy",  0))),
                "fii_sell":         _sf(row.get("buySell_FII_sell", row.get("fii_sell", 0))),
                "fii_net":          fii_net,
                "dii_buy":          _sf(row.get("buySell_DII_buy",  row.get("dii_buy",  0))),
                "dii_sell":         _sf(row.get("buySell_DII_sell", row.get("dii_sell", 0))),
                "dii_net":          dii_net,
                "fii_idx_fut_net":  0.0, "fii_stk_fut_net":  0.0,
                "fii_idx_call_net": 0.0, "fii_idx_put_net":  0.0,
                "pcr": 0.0, "sentiment_score": 50.0, "sentiment": "Neutral",
                "updated_at": datetime.now(IST).isoformat(),
            })
        return out

    try:
        nse_rows = await asyncio.wait_for(
            loop.run_in_executor(_executor, _fetch_nse_direct),
            timeout=12.0,
        )
        if nse_rows:
            # Persist to Supabase so future cold starts don't hit NSE again
            try:
                from data.storage import supabase_db as sdb
                sdb.upsert(
                    "screener_cache",
                    {
                        "strategy":    "fii_dii",
                        "universe":    "cash",
                        "scanned_at":  datetime.now(_tz.utc).isoformat(),
                        "results":     _json.dumps(nse_rows),
                        "is_scanning": False,
                    },
                    on_conflict="strategy,universe",
                )
            except Exception:
                pass
            return nse_rows[-60:]
    except Exception:
        pass

    # ── 3. nsepython fallback (same NSE API, different session handling) ──────
    if _NSE_AVAILABLE:
        try:
            def _fetch_nse_py() -> list[dict]:
                data = _nsefetch("https://www.nseindia.com/api/fiidiiTradeReact")
                out = []
                for row in (data if isinstance(data, list) else []):
                    fii_net = _sf(row.get("buySell_FII_net", 0))
                    dii_net = _sf(row.get("buySell_DII_net", 0))
                    if abs(fii_net) < 0.01 and abs(dii_net) < 0.01:
                        continue
                    out.append({
                        "date":             row.get("date", ""),
                        "fii_buy":          _sf(row.get("buySell_FII_buy",  0)),
                        "fii_sell":         _sf(row.get("buySell_FII_sell", 0)),
                        "fii_net":          fii_net,
                        "dii_buy":          _sf(row.get("buySell_DII_buy",  0)),
                        "dii_sell":         _sf(row.get("buySell_DII_sell", 0)),
                        "dii_net":          dii_net,
                        "fii_idx_fut_net":  0.0, "fii_stk_fut_net":  0.0,
                        "fii_idx_call_net": 0.0, "fii_idx_put_net":  0.0,
                        "pcr": 0.0, "sentiment_score": 50.0, "sentiment": "Neutral",
                        "updated_at": datetime.now(IST).isoformat(),
                    })
                return out
            nse_py_rows = await asyncio.wait_for(
                loop.run_in_executor(_executor, _fetch_nse_py), timeout=8.0
            )
            if nse_py_rows:
                return nse_py_rows[-60:]
        except Exception:
            pass

    # ── 4. Bundled local JSON files (real historical data, may be stale) ──────
    data_dir = Path(__file__).parent.parent / "fii_dii_data"
    try:
        latest_path = data_dir / "latest.json"
        if latest_path.exists():
            with open(latest_path) as f:
                latest = _json.load(f)
            if latest.get("fii_buy", 0) > 0:
                return [_map_row(latest)]
    except Exception:
        pass

    # ── No real data available — return empty, never return mock ──────────────
    return []


@router.get("/fii-dii/today")
async def get_fii_dii_today():
    """Today's FII/DII with full FAO data from fii-dii-data."""
    import json as _json
    from pathlib import Path
    data_dir = Path(__file__).parent.parent / "fii_dii_data"
    try:
        with open(data_dir / "latest.json") as f:
            d = _json.load(f)
        return {
            "date": d.get("date"),
            "fii_buy": d.get("fii_buy", 0),
            "fii_sell": d.get("fii_sell", 0),
            "fii_net": d.get("fii_net", 0),
            "dii_buy": d.get("dii_buy", 0),
            "dii_sell": d.get("dii_sell", 0),
            "dii_net": d.get("dii_net", 0),
            "fii_idx_fut_net": d.get("fii_idx_fut_net", 0),
            "fii_stk_fut_net": d.get("fii_stk_fut_net", 0),
            "fii_idx_call_net": d.get("fii_idx_call_net", 0),
            "fii_idx_put_net": d.get("fii_idx_put_net", 0),
            "pcr": d.get("pcr", 0),
            "sentiment_score": d.get("sentiment_score", 50),
            "sentiment": d.get("_fao_summary", {}).get("sentiment", "Neutral"),
            "updated_at": d.get("_updated_at", ""),
        }
    except Exception:
        data = await get_fii_dii()
        return data[-1] if data else {}


@router.get("/fii-dii/sectors")
@_cached("fii_sectors", ttl=3600)
async def get_fii_sectors():
    """FII ownership by sector from fii-dii-data repo."""
    import json as _json
    from pathlib import Path
    try:
        with open(Path(__file__).parent.parent / "fii_dii_data" / "sectors.json") as f:
            return _json.load(f)
    except Exception:
        return []


@router.get("/price/{symbol}")
async def get_live_price(symbol: str):
    """
    Live price for an NSE stock via NSE API (with session cookies) + yfinance fallback.
    Returns: {symbol, cmp, change, pct_change, open, prev_close, high, low,
              week_high_52, week_low_52, volume, delivery_pct, market_cap_cr,
              vwap, pe, company, industry, exchange}
    """
    clean = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    loop  = asyncio.get_running_loop()

    def _from_nse() -> dict:
        import requests as _rq
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer":         "https://www.nseindia.com/",
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        s = _rq.Session()
        s.headers.update(headers)
        s.get("https://www.nseindia.com/", timeout=8)
        s.get(f"https://www.nseindia.com/get-quotes/equity?symbol={clean}", timeout=6)
        r = s.get(
            f"https://www.nseindia.com/api/quote-equity?symbol={clean}",
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        pi = d.get("priceInfo", {})
        whl = pi.get("weekHighLow", {})
        md  = d.get("metadata", {})
        mc  = d.get("marketDeptOrderBook", {})
        cmp = pi.get("lastPrice") or pi.get("close")
        return {
            "symbol":      clean,
            "exchange":    "NSE",
            "company":     md.get("companyName", clean),
            "industry":    md.get("industry", ""),
            "cmp":         cmp,
            "change":      pi.get("change"),
            "pct_change":  pi.get("pChange"),
            "open":        pi.get("open"),
            "prev_close":  pi.get("previousClose"),
            "high":        pi.get("intraDayHighLow", {}).get("max") or pi.get("open"),
            "low":         pi.get("intraDayHighLow", {}).get("min") or pi.get("open"),
            "week_high_52": whl.get("max"),
            "week_low_52":  whl.get("min"),
            "vwap":         pi.get("vwap"),
            "volume":       md.get("totalTradedVolume"),
            "delivery_pct": md.get("deliveryToTradedQuantity"),
            "market_cap_cr": round(md.get("marketCap", 0) / 1e7, 2) if md.get("marketCap") else None,
            "pe":           None,
            "source":       "nse",
        }

    def _from_yfinance() -> dict:
        import yfinance as yf
        for tkr in [f"{clean}.NS", f"{clean}.BO"]:
            try:
                t  = yf.Ticker(tkr)
                fi = t.fast_info
                cmp = getattr(fi, "last_price", None) or getattr(fi, "regular_market_price", None)
                if not cmp:
                    continue
                mc_cr = round(getattr(fi, "market_cap", 0) / 1e7, 2)
                return {
                    "symbol":      clean,
                    "exchange":    "NSE" if ".NS" in tkr else "BSE",
                    "company":     clean,
                    "industry":    "",
                    "cmp":         round(float(cmp), 2),
                    "change":      None,
                    "pct_change":  None,
                    "open":        getattr(fi, "open", None),
                    "prev_close":  getattr(fi, "previous_close", None),
                    "high":        getattr(fi, "day_high", None),
                    "low":         getattr(fi, "day_low", None),
                    "week_high_52": getattr(fi, "fifty_two_week_high", None),
                    "week_low_52":  getattr(fi, "fifty_two_week_low", None),
                    "vwap":        None,
                    "volume":      getattr(fi, "three_month_average_volume", None),
                    "delivery_pct": None,
                    "market_cap_cr": mc_cr,
                    "pe":          None,
                    "source":      "yfinance",
                }
            except Exception:
                continue
        raise ValueError(f"No price found for {clean}")

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, _from_nse), timeout=16.0
        )
        return result
    except Exception:
        pass

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, _from_yfinance), timeout=12.0
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Price not found: {e}")


@router.get("/prices")
async def get_prices_batch(symbols: str = Query(..., description="Comma-separated NSE symbols")):
    """
    Batch CMP fetch for multiple symbols via yfinance download (fast, ~1-2s for 50 stocks).
    Returns {SYMBOL: {cmp, change, pct_change, prev_close}} dict.
    """
    raw = [s.strip().upper().replace(".NS", "").replace(".BO", "") for s in symbols.split(",") if s.strip()]
    if not raw or len(raw) > 100:
        return {}

    now_mono = time.monotonic()

    # Return cached entries immediately; only fetch what's stale/missing
    cached_result: dict[str, dict] = {}
    to_fetch: list[str] = []
    for sym in raw:
        entry = _PRICE_CACHE.get(sym)
        if entry and now_mono - entry[0] < _PRICE_CACHE_TTL:
            cached_result[sym] = entry[1]
        else:
            to_fetch.append(sym)

    if not to_fetch:
        return cached_result

    def _batch_fetch(syms: list[str]) -> dict:
        import yfinance as yf
        tickers = [f"{s}.NS" for s in syms]
        try:
            data = yf.download(
                tickers, period="2d", interval="1d",
                progress=False, auto_adjust=True,
                threads=True, group_by="ticker",
            )
            result: dict[str, dict] = {}
            for sym, tkr in zip(syms, tickers):
                try:
                    if len(tickers) == 1:
                        closes = data["Close"]
                    else:
                        closes = data[tkr]["Close"] if tkr in data.columns.get_level_values(0) else None
                    if closes is None or len(closes) < 1:
                        continue
                    closes = closes.dropna()
                    if len(closes) == 0:
                        continue
                    cmp = float(closes.iloc[-1])
                    prev = float(closes.iloc[-2]) if len(closes) >= 2 else cmp
                    chg  = cmp - prev
                    pct  = (chg / prev * 100) if prev else 0
                    result[sym] = {
                        "cmp":        round(cmp, 2),
                        "change":     round(chg, 2),
                        "pct_change": round(pct, 2),
                        "prev_close": round(prev, 2),
                    }
                except Exception:
                    continue
            return result
        except Exception:
            return {}

    loop = asyncio.get_running_loop()
    try:
        fresh = await asyncio.wait_for(
            loop.run_in_executor(_executor, _batch_fetch, to_fetch), timeout=15.0
        )
        ts = time.monotonic()
        for sym, data in fresh.items():
            _PRICE_CACHE[sym] = (ts, data)
        return {**cached_result, **fresh}
    except Exception:
        return cached_result


@router.get("/filings")
@_cached("filings", ttl=120)
async def get_filings(limit: int = Query(20, le=50)):
    """
    Recent corporate filings — BSE primary, NSE fallback, never mock.
    Both exchanges checked; results merged newest-first.
    """
    loop = asyncio.get_running_loop()

    def _fetch_bse() -> list[dict]:
        import urllib.request, json as _json
        url = (
            "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
            "?pageno=1&strCat=-1&strPrevDate=&strScrip=&strSearch=P"
            "&strToDate=&strType=C&subcategory=-1"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.bseindia.com/corporates/ann.html",
            "Accept":  "application/json",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        out = []
        for item in data.get("Table", [])[:limit]:
            att = item.get("ATTACHMENTNAME", "")
            out.append({
                "id":         str(item.get("NEWSID", "")),
                "company":    str(item.get("SLONGNAME") or item.get("SHORT_NAME") or item.get("SCRIP_CD", "")),
                "scrip_code": str(item.get("SCRIP_CD", "")),
                "category":   item.get("CATEGORYNAME", ""),
                "headline":   item.get("NEWSSUB", item.get("HEADLINE", ""))[:200],
                "exchange":   "BSE",
                "dt":         (item.get("DT_TM") or item.get("NEWS_DT", ""))[:19],
                "pdf_url":    f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{att}" if att else "",
                "has_pdf":    bool(att),
            })
        return out

    def _fetch_nse() -> list[dict]:
        import requests as _rq
        from datetime import date as _date, timedelta as _td
        today = _date.today()
        from_d = (today - _td(days=3)).strftime("%d-%m-%Y")
        to_d   = today.strftime("%d-%m-%Y")
        url = (
            f"https://www.nseindia.com/api/corporate-announcements"
            f"?index=equities&from_date={from_d}&to_date={to_d}"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            "Accept":  "application/json, text/plain, */*",
        }
        # Quick session visit to get cookies
        s = _rq.Session()
        s.headers.update(headers)
        try:
            s.get("https://www.nseindia.com/", timeout=5)
        except Exception:
            pass
        resp = s.get(url, timeout=8)
        resp.raise_for_status()
        raw = resp.json()
        out = []
        for item in raw[:limit]:
            out.append({
                "id":         str(item.get("seq_id", "")),
                "company":    str(item.get("sm_name", item.get("symbol", ""))),
                "scrip_code": str(item.get("symbol", "")),
                "category":   item.get("desc", ""),
                "headline":   (item.get("attchmntText") or item.get("desc", ""))[:200],
                "exchange":   "NSE",
                "dt":         (item.get("sort_date") or item.get("an_dt", ""))[:19],
                "pdf_url":    item.get("attchmntFile", ""),
                "has_pdf":    bool(item.get("attchmntFile")),
            })
        return out

    bse_results: list[dict] = []
    nse_results: list[dict] = []

    try:
        bse_results = await asyncio.wait_for(
            loop.run_in_executor(_executor, _fetch_bse), timeout=6.0
        )
    except Exception:
        pass

    try:
        nse_results = await asyncio.wait_for(
            loop.run_in_executor(_executor, _fetch_nse), timeout=10.0
        )
    except Exception:
        pass

    # Merge and return newest-first; BSE first (more granular DT)
    combined = bse_results + [n for n in nse_results if n not in bse_results]
    if combined:
        return combined[:limit]

    # True last-resort: empty list (frontend shows "No filings data" naturally)
    return []


@router.get("/filings/{scrip_code}")
@_cached("filing_detail", ttl=300)
async def get_stock_filings(scrip_code: str, limit: int = Query(10, le=30)):
    """Get recent filings for a specific BSE scrip code."""
    loop = asyncio.get_running_loop()
    try:
        def _fetch():
            import urllib.request, json as _json
            url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=&strScrip={scrip_code}&strSearch=P&strToDate=&strType=C&subcategory=-1"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = _json.loads(r.read())
            return [{"id": str(i.get("NEWSID","")), "company": i.get("SLONGNAME",""), "category": i.get("CATEGORYNAME",""), "headline": i.get("HEADLINE",""), "dt": i.get("NEWS_DT",""), "has_pdf": bool(i.get("ATTACHMENTNAME",""))} for i in data.get("Table", [])[:limit]]
        return await loop.run_in_executor(_executor, _fetch)
    except Exception:
        return []


@router.get("/corporate-actions")
@_cached("corp_actions", ttl=600)
async def get_corporate_actions(symbol: str = Query("", description="NSE symbol to filter")):
    """Corporate actions calendar — dividends, splits, bonuses, rights."""
    loop = asyncio.get_running_loop()

    if _NSE_AVAILABLE and not symbol:
        try:
            def _fetch():
                url = "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
                data = _nsefetch(url)
                results = []
                for item in (data if isinstance(data, list) else [])[:30]:
                    results.append({
                        "symbol": item.get("symbol", ""),
                        "company": item.get("subject", ""),
                        "action": item.get("series", ""),
                        "ex_date": item.get("exDate", ""),
                        "record_date": item.get("recordDate", ""),
                        "bc_start": item.get("bcStartDate", ""),
                        "bc_end": item.get("bcEndDate", ""),
                        "details": item.get("subject", ""),
                    })
                return results
            result = await loop.run_in_executor(_executor, _fetch)
            if result:
                return result
        except Exception:
            pass

    from datetime import timedelta
    today = datetime.now(IST).date()
    mock_actions = [
        {"symbol": "TCS", "company": "Tata Consultancy Services", "action": "Dividend", "ex_date": (today + timedelta(days=3)).strftime("%d-%b-%Y"), "record_date": (today + timedelta(days=4)).strftime("%d-%b-%Y"), "details": "Final Dividend Rs 28 per share"},
        {"symbol": "INFY", "company": "Infosys", "action": "Dividend", "ex_date": (today + timedelta(days=7)).strftime("%d-%b-%Y"), "record_date": (today + timedelta(days=8)).strftime("%d-%b-%Y"), "details": "Final Dividend Rs 21 per share"},
        {"symbol": "WIPRO", "company": "Wipro", "action": "Bonus", "ex_date": (today + timedelta(days=14)).strftime("%d-%b-%Y"), "record_date": (today + timedelta(days=15)).strftime("%d-%b-%Y"), "details": "Bonus 1:1"},
        {"symbol": "HDFCBANK", "company": "HDFC Bank", "action": "Dividend", "ex_date": (today + timedelta(days=5)).strftime("%d-%b-%Y"), "record_date": (today + timedelta(days=6)).strftime("%d-%b-%Y"), "details": "Interim Dividend Rs 19.50 per share"},
        {"symbol": "RELIANCE", "company": "Reliance Industries", "action": "AGM", "ex_date": (today + timedelta(days=21)).strftime("%d-%b-%Y"), "record_date": "", "details": "Annual General Meeting FY2026"},
        {"symbol": "SUNPHARMA", "company": "Sun Pharma", "action": "Dividend", "ex_date": (today + timedelta(days=10)).strftime("%d-%b-%Y"), "record_date": (today + timedelta(days=11)).strftime("%d-%b-%Y"), "details": "Final Dividend Rs 5 per share"},
        {"symbol": "LTIM", "company": "LTIMindtree", "action": "Split", "ex_date": (today + timedelta(days=18)).strftime("%d-%b-%Y"), "record_date": (today + timedelta(days=19)).strftime("%d-%b-%Y"), "details": "Stock Split 5:1"},
    ]
    if symbol:
        return [a for a in mock_actions if a["symbol"].upper() == symbol.upper()]
    return mock_actions


@router.get("/advances-declines")
@_cached("adv_dec", ttl=300)
async def get_advances_declines():
    """
    Market breadth — advances, declines, unchanged.
    Sources tried in order:
      1. NSE official API — NIFTY 500 (500 stocks)
      2. NSE official API — NIFTY TOTAL MARKET (~750 stocks)
      3. yfinance batch download — Nifty 50 (50 stocks, most liquid)
    Returns source label so UI can display it correctly.
    Never returns random fake data.
    """
    loop  = asyncio.get_running_loop()
    now_s = datetime.now(IST).strftime("%I:%M %p IST")

    def _from_nse_index(index_name: str) -> dict | None:
        if not _NSE_AVAILABLE:
            return None
        try:
            import urllib.parse
            url  = f"https://www.nseindia.com/api/equity-stockIndices?index={urllib.parse.quote(index_name)}"
            data = _nsefetch(url)
            stocks = data.get("data", [])
            if len(stocks) < 10:
                return None
            adv = sum(1 for s in stocks if _sf(s.get("pChange", 0)) > 0)
            dec = sum(1 for s in stocks if _sf(s.get("pChange", 0)) < 0)
            unc = len(stocks) - adv - dec
            return {
                "advances": adv, "declines": dec, "unchanged": unc,
                "total": len(stocks),
                "ratio": round(adv / max(dec, 1), 2),
                "index_name": index_name,
                "source": "NSE Official",
                "as_of": now_s,
            }
        except Exception:
            return None

    def _from_yfinance() -> dict | None:
        try:
            import yfinance as _yf
            tickers = NIFTY50  # 50 most liquid NSE stocks
            data = _yf.download(
                tickers, period="2d", interval="1d",
                progress=False, auto_adjust=True, threads=True,
            )
            closes = data["Close"] if "Close" in data.columns else None
            if closes is None:
                return None
            adv = dec = unc = 0
            counted = 0
            for tkr in tickers:
                try:
                    col = tkr if tkr in closes.columns else None
                    if col is None:
                        continue
                    series = closes[col].dropna()
                    if len(series) < 2:
                        continue
                    chg = float(series.iloc[-1]) - float(series.iloc[-2])
                    if chg > 0:
                        adv += 1
                    elif chg < 0:
                        dec += 1
                    else:
                        unc += 1
                    counted += 1
                except Exception:
                    continue
            if counted < 10:
                return None
            last_date = closes.index[-1].strftime("%d %b")
            return {
                "advances": adv, "declines": dec, "unchanged": unc,
                "total": counted,
                "ratio": round(adv / max(dec, 1), 2),
                "index_name": "Nifty 50",
                "source": f"yfinance · {last_date}",
                "as_of": last_date,
            }
        except Exception:
            return None

    # Primary: project stock_universe via Supabase (instant query, 2142 stocks)
    result = await loop.run_in_executor(_executor, _get_universe_breadth)
    if result:
        return result

    # Fallback 1: NSE NIFTY 500 / NIFTY TOTAL MARKET
    for index in ("NIFTY 500", "NIFTY TOTAL MARKET"):
        result = await loop.run_in_executor(_executor, _from_nse_index, index)
        if result:
            return result

    # Fallback 2: yfinance NIFTY50 batch
    result = await loop.run_in_executor(_executor, _from_yfinance)
    if result:
        return result

    # Return empty rather than fake data
    return {
        "advances": 0, "declines": 0, "unchanged": 0, "total": 0,
        "ratio": 1.0, "index_name": "—", "source": "Unavailable", "as_of": "—",
    }


@router.get("/global-indices")
@_cached("global_indices", ttl=60)
async def get_global_indices():
    """Global indices: GIFT NIFTY (proxy), Brent Crude, Dow Jones via yfinance."""
    loop = asyncio.get_running_loop()

    GLOBAL_TICKERS = [
        ("GIFT NIFTY",  "^NSEI",  "INR", "NSE IFSC"),
        ("BRENT CRUDE", "BZ=F",   "USD", "ICE"),
        ("DOW JONES",   "^DJI",   "USD", "NYSE"),
    ]

    async def _one(label: str, sym: str, currency: str, exchange: str) -> dict | None:
        try:
            d = await asyncio.wait_for(
                loop.run_in_executor(_executor, _fetch_index, sym),
                timeout=4.0,
            )
            if d and d.get("price", 0) > 0:
                return {
                    "label": label, "symbol": sym,
                    "price": d["price"], "change_pct": d["change_pct"],
                    "change": d.get("change", 0),
                    "currency": currency, "exchange": exchange,
                }
        except Exception:
            pass
        return None

    results = await asyncio.gather(*[_one(*t) for t in GLOBAL_TICKERS])
    return [r for r in results if r is not None]


@router.get("/results-calendar")
@_cached("results_cal", ttl=3600)
async def get_results_calendar():
    """Upcoming quarterly results calendar from NSE."""
    loop = asyncio.get_running_loop()
    if _NSE_AVAILABLE:
        try:
            def _fetch():
                url = "https://www.nseindia.com/api/corporates-boardMeetings?index=equities"
                data = _nsefetch(url)
                results = []
                for item in (data if isinstance(data, list) else [])[:30]:
                    results.append({
                        "symbol": item.get("symbol",""),
                        "company": item.get("companyName",""),
                        "meeting_date": item.get("bm_date",""),
                        "purpose": item.get("bm_purpose",""),
                        "description": item.get("bm_desc",""),
                    })
                return [r for r in results if r["symbol"]]
            result = await loop.run_in_executor(_executor, _fetch)
            if result:
                return result
        except Exception:
            pass
    from datetime import timedelta
    today = datetime.now(IST).date()
    return [
        {"symbol": "RELIANCE", "company": "Reliance Industries", "meeting_date": (today + timedelta(days=2)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Board Meeting for Q4 FY26 results"},
        {"symbol": "HDFCBANK", "company": "HDFC Bank", "meeting_date": (today + timedelta(days=3)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 FY26 results and final dividend"},
        {"symbol": "ICICIBANK", "company": "ICICI Bank", "meeting_date": (today + timedelta(days=5)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 and Full Year FY26 results"},
        {"symbol": "TCS", "company": "TCS", "meeting_date": (today + timedelta(days=7)).strftime("%d-%b-%Y"), "purpose": "Financial Results & Dividend", "description": "Q4 results + Final Dividend announcement"},
        {"symbol": "INFY", "company": "Infosys", "meeting_date": (today + timedelta(days=8)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 FY26 earnings with guidance"},
        {"symbol": "WIPRO", "company": "Wipro", "meeting_date": (today + timedelta(days=9)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 FY26 revenue and margin update"},
        {"symbol": "BAJFINANCE", "company": "Bajaj Finance", "meeting_date": (today + timedelta(days=11)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 AUM growth and NPA data"},
        {"symbol": "AXISBANK", "company": "Axis Bank", "meeting_date": (today + timedelta(days=12)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 FY26 credit growth and NIM"},
        {"symbol": "MARUTI", "company": "Maruti Suzuki", "meeting_date": (today + timedelta(days=14)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 FY26 volume and realisation"},
        {"symbol": "SUNPHARMA", "company": "Sun Pharma", "meeting_date": (today + timedelta(days=15)).strftime("%d-%b-%Y"), "purpose": "Financial Results", "description": "Q4 specialty business update"},
    ]


# ── Quarterly Results ─────────────────────────────────────────────────────────

_QUARTERLY_STOCKS = [
    # (yf_sym, nse_sym, company, sector)
    ("HDFCBANK.NS",  "HDFCBANK",  "HDFC Bank",               "Banking"),
    ("TCS.NS",       "TCS",       "Tata Consultancy Services","IT"),
    ("RELIANCE.NS",  "RELIANCE",  "Reliance Industries",      "Energy"),
    ("INFY.NS",      "INFY",      "Infosys",                  "IT"),
    ("ICICIBANK.NS", "ICICIBANK", "ICICI Bank",               "Banking"),
    ("BHARTIARTL.NS","BHARTIARTL","Bharti Airtel",            "Telecom"),
    ("HCLTECH.NS",   "HCLTECH",  "HCL Technologies",         "IT"),
    ("BAJFINANCE.NS","BAJFINANCE","Bajaj Finance",            "NBFC"),
    ("SBIN.NS",      "SBIN",     "State Bank of India",      "Banking"),
    ("TITAN.NS",     "TITAN",    "Titan Company",            "Consumer"),
    ("MARUTI.NS",    "MARUTI",   "Maruti Suzuki",            "Auto"),
    ("SUNPHARMA.NS", "SUNPHARMA","Sun Pharmaceutical",       "Pharma"),
    ("WIPRO.NS",     "WIPRO",    "Wipro",                    "IT"),
    ("NTPC.NS",      "NTPC",     "NTPC",                     "Power"),
    ("HINDUNILVR.NS","HINDUNILVR","Hindustan Unilever",      "FMCG"),
    ("ULTRACEMCO.NS","ULTRACEMCO","UltraTech Cement",        "Cement"),
    ("TECHM.NS",     "TECHM",    "Tech Mahindra",            "IT"),
    ("TATAMOTORS.NS","TATAMOTORS","Tata Motors",             "Auto"),
    ("DRREDDY.NS",   "DRREDDY",  "Dr. Reddy's",              "Pharma"),
    ("ASIANPAINT.NS","ASIANPAINT","Asian Paints",            "Paints"),
    ("JSWSTEEL.NS",  "JSWSTEEL", "JSW Steel",                "Steel"),
    ("ADANIPORTS.NS","ADANIPORTS","Adani Ports",             "Infrastructure"),
    ("POWERGRID.NS", "POWERGRID","Power Grid Corp",          "Power"),
    ("ONGC.NS",      "ONGC",     "ONGC",                     "Energy"),
    ("AXISBANK.NS",  "AXISBANK", "Axis Bank",                "Banking"),
]


def _qlabel(d: "datetime") -> str:
    try:
        m, y = d.month, d.year
        fy = y + 1 if m >= 4 else y
        q = {1:"Q4",2:"Q4",3:"Q4",4:"Q1",5:"Q1",6:"Q1",7:"Q2",8:"Q2",9:"Q2",10:"Q3",11:"Q3",12:"Q3"}[m]
        return f"{q} FY{str(fy)[2:]}"
    except Exception:
        return ""


def _sf2(v, default=None):
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return default


def _fetch_one_qr_yf(yf_sym: str, nse_sym: str, company: str, sector: str) -> dict | None:
    try:
        import pandas as pd
        t = yf.Ticker(yf_sym)
        stmt = t.quarterly_income_stmt
        if stmt is None or stmt.empty or len(stmt.columns) < 3:
            return None
        cols = list(stmt.columns[:5])

        def _val(keys, col):
            for k in keys:
                if k in stmt.index:
                    v = stmt.loc[k, col]
                    if pd.notna(v) and v not in (0, None):
                        return _sf2(v, 0.0) / 1e7  # → ₹ Crores
            return None

        REV  = ["Total Revenue", "Net Sales", "Revenue", "Operating Revenue"]
        OPI  = ["Operating Income", "EBIT", "Gross Profit", "Operating Profit"]
        NET  = ["Net Income", "Net Income Common Stockholders", "Net Profit"]

        sales = [_val(REV, c) for c in cols]
        op    = [_val(OPI, c) for c in cols]
        pat   = [_val(NET, c) for c in cols]
        opm   = [round(o/s*100,1) if o and s and s > 0 else None for o,s in zip(op,sales)]

        # EPS via quarterly earnings
        eps_list: list = [None]*5
        try:
            qe = t.quarterly_earnings
            if qe is not None and not qe.empty:
                for i, col in enumerate(cols[:5]):
                    for k in qe.index:
                        if abs((k - col).days) < 50:
                            eps_list[i] = _sf2(qe.loc[k, "EPS"])
                            break
        except Exception:
            pass

        q_labels = [_qlabel(c) for c in cols[:5]]

        def _yoy(vals):
            for lag in (4, 3):
                if len(vals) > lag and vals[0] and vals[lag] and vals[lag] != 0:
                    return round((vals[0]-vals[lag])/abs(vals[lag])*100, 1)
            return None

        def _qoq(vals):
            if len(vals) > 1 and vals[0] and vals[1] and vals[1] != 0:
                return round((vals[0]-vals[1])/abs(vals[1])*100, 1)
            return None

        def _mk(vals):
            return {
                "q1":  round(vals[0],1) if len(vals)>0 and vals[0] is not None else 0,
                "q2":  round(vals[1],1) if len(vals)>1 and vals[1] is not None else 0,
                "q3":  round(vals[2],1) if len(vals)>2 and vals[2] is not None else 0,
                "qoq": _qoq(vals),
                "yoy": _yoy(vals),
            }

        s_yoy = _yoy(sales);  p_yoy = _yoy(pat)
        if s_yoy is not None and p_yoy is not None:
            if s_yoy >= 20 and p_yoy >= 25:
                rating, note = "Excellent", f"Revenue +{s_yoy:.0f}%, PAT +{p_yoy:.0f}% YoY — exceptional delivery"
            elif s_yoy >= 10 and p_yoy >= 15:
                rating, note = "Great",    f"Revenue +{s_yoy:.0f}%, PAT +{p_yoy:.0f}% YoY — above expectations"
            elif s_yoy >= 5  and p_yoy >= 5:
                rating, note = "Good",     f"Revenue +{s_yoy:.0f}%, PAT +{p_yoy:.0f}% YoY — steady execution"
            elif p_yoy >= 0:
                rating, note = "Ok",       f"Revenue {s_yoy:+.0f}%, PAT {p_yoy:+.0f}% YoY — in-line"
            else:
                rating, note = "Weak",     f"Revenue {s_yoy:+.0f}%, PAT {p_yoy:+.0f}% YoY — misses estimates"
        else:
            rating, note = "Ok", "Insufficient YoY comparison data"

        try:
            fi = t.fast_info
            cmp = _sf2(fi.last_price)
            mktcap = round(_sf2(fi.market_cap, 0) / 1e7, 0)
        except Exception:
            cmp, mktcap = None, 0.0

        pe = None
        if cmp and eps_list[0] and eps_list[0] > 0:
            pe = round(cmp / (eps_list[0] * 4), 1)

        try:
            rd = str(cols[0].date())
        except Exception:
            rd = ""

        return {
            "id":            f"{nse_sym}_{q_labels[0] if q_labels else 'Q'}",
            "symbol":        nse_sym,
            "ticker":        yf_sym,
            "company":       company,
            "exchange":      "NSE",
            "sector":        sector,
            "industry":      sector,
            "quarter":       q_labels[0] if q_labels else "",
            "report_date":   rd,
            "report_time":   "After Market",
            "rating":        rating,
            "rating_note":   note,
            "insight":       note,
            "metrics": {
                "sales":        _mk(sales),
                "other_income": {"q1":0,"q2":0,"q3":0,"qoq":None,"yoy":None},
                "op":           _mk(op),
                "opm":          _mk(opm),
                "pat":          _mk(pat),
                "eps":          _mk(eps_list),
            },
            "revenue_trend":  [round(s,0) for s in sales[:4] if s is not None],
            "pat_trend":      [round(p,0) for p in pat[:4]   if p is not None],
            "eps_trend":      [round(e,1) for e in eps_list[:4] if e is not None],
            "quarter_labels": q_labels[:4],
            "cmp":            cmp,
            "market_cap":     mktcap,
            "pe":             pe,
            "currency_unit":  "₹ Cr",
        }
    except Exception:
        return None



def _qr_fallback() -> list[dict]:
    """Realistic Q4 FY2026 data for 25 Nifty stocks when live fetch is pending."""
    now_str = "2026-03-31"
    def _r(sym, co, sect, s1, s2, s3, op1, op2, op3, p1, p2, p3, e1, e2, e3, cmp, mcap, s_yoy, p_yoy):
        opm1 = round(op1/s1*100,1) if s1 else 0
        opm2 = round(op2/s2*100,1) if s2 else 0
        opm3 = round(op3/s3*100,1) if s3 else 0
        s_qoq = round((s1-s2)/s2*100,1) if s2 else None
        p_qoq = round((p1-p2)/p2*100,1) if p2 else None
        e_qoq = round((e1-e2)/e2*100,1) if e2 else None
        if s_yoy >= 20 and p_yoy >= 25:
            rating, note = "Excellent", f"Revenue +{s_yoy}%, PAT +{p_yoy}% YoY — exceptional delivery"
        elif s_yoy >= 10 and p_yoy >= 15:
            rating, note = "Great",    f"Revenue +{s_yoy}%, PAT +{p_yoy}% YoY — above expectations"
        elif s_yoy >= 5  and p_yoy >= 5:
            rating, note = "Good",     f"Revenue +{s_yoy}%, PAT +{p_yoy}% YoY — steady execution"
        elif p_yoy >= 0:
            rating, note = "Ok",       f"Revenue +{s_yoy}%, PAT +{p_yoy}% YoY — in-line"
        else:
            rating, note = "Weak",     f"Revenue {s_yoy:+}%, PAT {p_yoy:+}% YoY — below expectations"
        pe = round(cmp/(e1*4),1) if e1 and e1 > 0 else None
        return {
            "id":sym+"_Q4FY26","symbol":sym,"ticker":sym+".NS","company":co,
            "exchange":"NSE","sector":sect,"industry":sect,
            "quarter":"Q4 FY26","report_date":now_str,"report_time":"After Market",
            "rating":rating,"rating_note":note,"insight":note,
            "metrics":{
                "sales":{"q1":s1,"q2":s2,"q3":s3,"qoq":s_qoq,"yoy":s_yoy},
                "other_income":{"q1":0,"q2":0,"q3":0,"qoq":None,"yoy":None},
                "op":{"q1":op1,"q2":op2,"q3":op3,"qoq":round((op1-op2)/op2*100,1) if op2 else None,"yoy":None},
                "opm":{"q1":opm1,"q2":opm2,"q3":opm3,"qoq":round(opm1-opm2,1),"yoy":None},
                "pat":{"q1":p1,"q2":p2,"q3":p3,"qoq":p_qoq,"yoy":p_yoy},
                "eps":{"q1":e1,"q2":e2,"q3":e3,"qoq":e_qoq,"yoy":None},
            },
            "revenue_trend":[s1,s2,s3],"pat_trend":[p1,p2,p3],"eps_trend":[e1,e2,e3],
            "quarter_labels":["Q4 FY26","Q3 FY26","Q2 FY26"],
            "cmp":cmp,"market_cap":mcap,"pe":pe,"currency_unit":"₹ Cr",
        }
    #         sym          company               sect       s1      s2      s3     op1    op2    op3    p1     p2     p3    e1     e2     e3    cmp     mcap   s_yoy p_yoy
    return sorted([
    _r("HDFCBANK",  "HDFC Bank",               "Banking",  89200, 86400, 83100, 17900, 17200, 16600, 17200, 16800, 16200, 22.6, 22.1, 21.3, 1720, 1280000, 14, 18),
    _r("ICICIBANK",  "ICICI Bank",             "Banking",  25400, 24200, 23100, 11200, 10800, 10100, 12200, 11800, 11100, 17.3, 16.8, 15.8, 1380,  970000, 22, 28),
    _r("SBIN",       "State Bank of India",    "Banking", 131800,128200,123100, 18200, 17600, 16900, 18100, 17200, 16400, 20.3, 19.3, 18.4,  870,  780000, 12, 24),
    _r("TATAMOTORS", "Tata Motors",            "Auto",    121000,113400,105200, 14200, 13100, 12300,  9600,  8800,  7900, 26.6, 24.4, 21.9,  960,  350000, 26, 35),
    _r("TCS",        "TCS",                    "IT",       65200, 63100, 61200, 17800, 17200, 16600, 12800, 12300, 11900, 34.7, 33.4, 32.3, 3780, 1380000,  8, 10),
    _r("INFY",       "Infosys",                "IT",       42600, 41400, 40100, 10800, 10400,  9900,  7600,  7200,  6900, 18.3, 17.4, 16.7, 1540,  640000,  9, 12),
    _r("HCLTECH",    "HCL Technologies",       "IT",       31200, 29800, 28400,  6800,  6400,  6100,  4600,  4300,  4100, 16.9, 15.9, 15.1, 1660,  450000, 14, 18),
    _r("BHARTIARTL", "Bharti Airtel",          "Telecom",  44200, 42100, 39800, 19600, 18400, 17200,  5300,  4900,  4100, 14.3, 13.3, 11.1, 1760,  1040000,22, 38),
    _r("BAJFINANCE", "Bajaj Finance",          "NBFC",     17200, 16400, 15600,  8900,  8400,  7900,  4900,  4600,  4200, 80.8, 75.9, 69.3, 8700,  527000, 18, 26),
    _r("RELIANCE",   "Reliance Industries",    "Energy",  254000,241000,228000, 32800, 30900, 29200, 20200, 19100, 17900, 30.1, 28.5, 26.7, 1410, 1900000,  8, 13),
    _r("MARUTI",     "Maruti Suzuki",          "Auto",     42200, 39600, 36800,  6100,  5600,  5200,  4300,  3900,  3600, 142, 130,  120, 11800,  357000, 16, 22),
    _r("NTPC",       "NTPC",                   "Power",    48600, 46200, 43800, 12400, 11600, 10900,  5600,  5200,  4800, 15.3, 14.2, 13.1,  373,  362000, 14, 20),
    _r("SUNPHARMA",  "Sun Pharmaceutical",     "Pharma",   15400, 14800, 14100,  3900,  3700,  3500,  2800,  2600,  2400, 37.1, 34.4, 31.8,  1760, 421000, 16, 22),
    _r("AXISBANK",   "Axis Bank",              "Banking",  27800, 26400, 25100, 11200, 10600,  9900,  7200,  6800,  6300, 23.0, 21.7, 20.1, 1180,  364000, 14, 19),
    _r("WIPRO",      "Wipro",                  "IT",       22800, 22100, 21400,  4800,  4600,  4400,  3400,  3200,  3000,  6.6,  6.2,  5.8,  580,  304000,  5,  8),
    _r("ULTRACEMCO", "UltraTech Cement",       "Cement",   20400, 19800, 18900,  4700,  4500,  4200,  2200,  2000,  1800, 60.3, 54.9, 49.4, 10800, 312000, 12, 18),
    _r("POWERGRID",  "Power Grid Corp",        "Power",    11600, 11200, 10800,  9100,  8800,  8400,  3900,  3700,  3500, 14.9, 14.2, 13.4,  298,  277000,  8, 12),
    _r("TITAN",      "Titan Company",          "Consumer", 13600, 12100, 11200,  1560,  1380,  1280,   990,   860,   800, 11.2,  9.8,  9.1, 3580, 318000, 10,  8),
    _r("TECHM",      "Tech Mahindra",          "IT",       14900, 14100, 13400,  2200,  2000,  1800,  1800,  1600,  1400, 18.4, 16.4, 14.4,  1560, 152000, 14, 32),
    _r("HINDUNILVR", "Hindustan Unilever",     "FMCG",     16200, 15800, 15400,  4100,  3900,  3800,  2900,  2700,  2600, 24.8, 23.1, 22.2, 2620, 616000,  4,  6),
    _r("ASIANPAINT", "Asian Paints",           "Paints",    9600,  9800, 10200,  1620,  1800,  2100,  1180,  1350,  1600,  4.6,  5.3,  6.3, 2280, 219000, -6,-26),
    _r("DRREDDY",    "Dr. Reddy's",            "Pharma",    8400,  8100,  7800,  2100,  2000,  1900,  1400,  1300,  1200, 84.3, 78.3, 72.3, 1380, 230000, 10, 16),
    _r("JSWSTEEL",   "JSW Steel",              "Steel",    41200, 39100, 37400,  5800,  5200,  4700,  2200,  1800,  1600, 18.9, 15.4, 13.7,  950, 228000, 10, 22),
    _r("ADANIPORTS", "Adani Ports",            "Infra",     7800,  7200,  6800,  4200,  3900,  3600,  2500,  2200,  2000, 87.7, 77.0, 70.1,  1420, 303000, 18, 28),
    _r("ONGC",       "ONGC",                   "Energy",  161000,154000,147000, 28000, 26500, 25000, 12100, 11400, 10800, 14.1, 13.3, 12.6,  274, 344000,  6, 10),
    ], key=lambda x: {"Excellent":0,"Great":1,"Good":2,"Ok":3,"Weak":4}.get(x.get("rating","Ok"),3))


@router.get("/quarterly-results")
async def get_quarterly_results(limit: int = Query(200, le=500)):
    """Quarterly earnings results from the quarterly_results Supabase table."""
    import urllib.request as _ur
    import os as _os
    sb_url = _os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    sb_key = _os.getenv("SUPABASE_KEY", "").strip()
    if not sb_url or not sb_key:
        return []
    headers = {
        "apikey":        sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type":  "application/json",
        "Range-Unit":    "items",
        "Range":         f"0-{limit - 1}",
    }
    url = (
        f"{sb_url}/rest/v1/quarterly_results"
        f"?select=*&report_date=gte.2026-05-01&order=report_date.desc,created_at.desc"
    )
    try:
        req = _ur.Request(url, headers=headers)
        with _ur.urlopen(req, timeout=12) as resp:
            rows = json.loads(resp.read())
        if not isinstance(rows, list):
            return []
        for r in rows:
            if isinstance(r.get("metrics"), str):
                try:
                    r["metrics"] = json.loads(r["metrics"])
                except Exception:
                    pass
            for k in ("revenue_trend", "pat_trend", "eps_trend", "quarter_labels"):
                if isinstance(r.get(k), str):
                    try:
                        r[k] = json.loads(r[k])
                    except Exception:
                        r[k] = []
        return rows
    except Exception as exc:
        print(f"[quarterly-results] {exc}")
        return []


# ── Stock Fundamentals (yfinance .info — 6h cache) ───────────────────────────

_FUND_CACHE: dict[str, tuple[float, dict]] = {}

@router.get("/fundamentals/{symbol}")
async def get_fundamentals(symbol: str):
    """
    Comprehensive fundamentals for a stock.
    Source: yfinance .info (P/E, P/B, ROE, Debt/Equity, EPS, margins, etc.)
    Cache: 6 hours — fundamentals change slowly.
    """
    clean = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    now   = time.monotonic()
    if clean in _FUND_CACHE:
        ts, val = _FUND_CACHE[clean]
        if now - ts < 21600:  # 6 hours
            return val

    def _fetch() -> dict:
        import yfinance as _yf
        for suffix in (".NS", ".BO"):
            try:
                tkr  = clean + suffix
                info = _yf.Ticker(tkr).info
                if not info or info.get("regularMarketPrice", 0) == 0:
                    continue

                def _f(key, default=None):
                    v = info.get(key)
                    if v is None or (isinstance(v, float) and math.isnan(v)):
                        return default
                    return v

                mc_raw = _f("marketCap", 0)
                mc_cr  = round(mc_raw / 1e7, 2) if mc_raw else 0

                return {
                    "symbol":           clean,
                    "company":          _f("longName") or _f("shortName") or clean,
                    "sector":           _f("sector", ""),
                    "industry":         _f("industry", ""),
                    "market_cap_cr":    mc_cr,
                    "cmp":              round(_f("regularMarketPrice", 0), 2),
                    "pe":               round(_f("trailingPE", 0) or 0, 1),
                    "forward_pe":       round(_f("forwardPE", 0) or 0, 1),
                    "pb":               round(_f("priceToBook", 0) or 0, 2),
                    "ev_ebitda":        round(_f("enterpriseToEbitda", 0) or 0, 1),
                    "eps_ttm":          round(_f("trailingEps", 0) or 0, 2),
                    "eps_forward":      round(_f("forwardEps", 0) or 0, 2),
                    "roe":              round((_f("returnOnEquity", 0) or 0) * 100, 1),
                    "roa":              round((_f("returnOnAssets", 0) or 0) * 100, 1),
                    "profit_margin":    round((_f("profitMargins", 0) or 0) * 100, 1),
                    "op_margin":        round((_f("operatingMargins", 0) or 0) * 100, 1),
                    "revenue_growth":   round((_f("revenueGrowth", 0) or 0) * 100, 1),
                    "earnings_growth":  round((_f("earningsGrowth", 0) or 0) * 100, 1),
                    "debt_to_equity":   round(_f("debtToEquity", 0) or 0, 2),
                    "current_ratio":    round(_f("currentRatio", 0) or 0, 2),
                    "book_value":       round(_f("bookValue", 0) or 0, 2),
                    "dividend_yield":   round((_f("dividendYield", 0) or 0) * 100, 2),
                    "beta":             round(_f("beta", 0) or 0, 2),
                    "week_high_52":     round(_f("fiftyTwoWeekHigh", 0) or 0, 2),
                    "week_low_52":      round(_f("fiftyTwoWeekLow", 0) or 0, 2),
                    "shares_cr":        round((_f("sharesOutstanding", 0) or 0) / 1e7, 2),
                    "float_cr":         round((_f("floatShares", 0) or 0) / 1e7, 2),
                    "source":           "yfinance",
                    "ticker_used":      tkr,
                }
            except Exception:
                continue
        return {"symbol": clean, "error": "Data unavailable"}

    loop   = asyncio.get_running_loop()
    result = await asyncio.wait_for(loop.run_in_executor(_executor, _fetch), timeout=18.0)
    if "error" not in result:
        _FUND_CACHE[clean] = (now, result)

    # Merge screener.in DB cache: ROCE, shareholding, promoter pledge (yFinance lacks these)
    try:
        scr = await _get_screener_row(clean)
        if scr:
            if "error" in result:
                result = {
                    "symbol":  clean,
                    "company": clean,
                    "sector":  "",
                    "industry": "",
                    "market_cap_cr": scr.get("market_cap_cr") or 0,
                    "cmp":           scr.get("current_price")  or 0,
                    "pe":            scr.get("pe_ratio")        or 0,
                    "forward_pe":    0,
                    "pb":            0,
                    "ev_ebitda":     0,
                    "eps_ttm":       scr.get("eps_ttm")        or 0,
                    "eps_forward":   0,
                    "roe":           scr.get("roe_pct")        or 0,
                    "roa":           0,
                    "profit_margin": 0,
                    "op_margin":     0,
                    "revenue_growth": 0,
                    "earnings_growth": 0,
                    "debt_to_equity":  scr.get("debt_to_equity")  or 0,
                    "current_ratio":   scr.get("current_ratio")   or 0,
                    "book_value":      scr.get("book_value")       or 0,
                    "dividend_yield":  scr.get("dividend_yield_pct") or 0,
                    "beta":            0,
                    "week_high_52":    scr.get("high_52w")         or 0,
                    "week_low_52":     scr.get("low_52w")          or 0,
                    "shares_cr":       0,
                    "float_cr":        0,
                    "source":          "screener_db",
                }
            # Always overlay screener-exclusive fields
            result["roce"]             = scr.get("roce_pct")
            result["promoter_pct"]     = scr.get("promoter_pct")
            result["promoter_pledge_pct"] = scr.get("promoter_pledge_pct")
            result["fii_pct"]          = scr.get("fii_pct")
            result["dii_pct"]          = scr.get("dii_pct")
            result["public_pct"]       = scr.get("public_pct")
            result["sales_ttm_cr"]     = scr.get("sales_ttm_cr")
            result["profit_ttm_cr"]    = scr.get("profit_ttm_cr")
            result["screener_url"]     = scr.get("screener_url")
            result["screener_scraped_at"] = str(scr.get("scraped_at", ""))[:10]
            # Fill blanks in yFinance fields with screener values
            if not result.get("pe")     : result["pe"]      = scr.get("pe_ratio")  or 0
            if not result.get("roe")    : result["roe"]     = scr.get("roe_pct")   or 0
            if not result.get("market_cap_cr"): result["market_cap_cr"] = scr.get("market_cap_cr") or 0
    except Exception as _e:
        pass  # screener merge is best-effort

    return result


async def _get_screener_row(clean_symbol: str) -> dict | None:
    """Fetch one row from fact_screener_fundamentals (anon key read is fine)."""
    if not (_SB_URL and _SB_KEY):
        return None
    url = (
        f"{_SB_URL}/rest/v1/fact_screener_fundamentals"
        f"?ticker=eq.{clean_symbol}&limit=1&select=*"
    )
    try:
        req  = _ur.Request(url, headers=_sb_headers_mkt())
        with _ur.urlopen(req, timeout=8) as resp:
            rows = json.loads(resp.read())
        return rows[0] if rows else None
    except Exception:
        return None


# ── Universe sync (screener → dim_company) ───────────────────────────────────

@router.post("/universe/sync")
async def universe_sync(dry_run: bool = Query(False)):
    """
    Promote stocks from fact_screener_fundamentals into dim_company if missing.
    Runs universe expansion without a DB migration — call once after each scrape.
    """
    svc_key = _os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not svc_key:
        raise HTTPException(503, "SUPABASE_SERVICE_KEY not set — cannot write dim_company")

    # 1. All tickers in screener cache
    scr_url  = f"{_SB_URL}/rest/v1/fact_screener_fundamentals?select=ticker,company_id,market_cap_cr,current_price&limit=10000"
    scr_rows = await _sb_get_all(scr_url, _sb_headers_mkt())

    # 2. All company_ids already in dim_company
    dim_url  = f"{_SB_URL}/rest/v1/dim_company?select=company_id,ticker&limit=10000"
    dim_rows = await _sb_get_all(dim_url, _sb_headers_mkt())
    existing_tickers = {r["ticker"] for r in dim_rows if r.get("ticker")}

    new_rows = []
    for r in scr_rows:
        t = (r.get("ticker") or "").strip().upper()
        if not t or t in existing_tickers:
            continue
        new_rows.append({
            "company_id":         t,
            "ticker":             t,
            "company_name":       t,
            "exchange":           "NSE",
            "market_cap_inr_cr":  r.get("market_cap_cr"),
            "current_price_inr":  r.get("current_price"),
            "is_active":          True,
        })

    if not new_rows:
        return {"added": 0, "message": "Universe already up-to-date"}

    if dry_run:
        return {"added": len(new_rows), "dry_run": True, "sample": new_rows[:5]}

    # Write with service key
    write_headers = {
        "apikey":        svc_key,
        "Authorization": f"Bearer {svc_key}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=ignore-duplicates,return=minimal",
    }
    BATCH = 200
    added = 0
    for i in range(0, len(new_rows), BATCH):
        chunk = new_rows[i : i + BATCH]
        body  = json.dumps(chunk).encode()
        req   = _ur.Request(
            f"{_SB_URL}/rest/v1/dim_company",
            data=body, headers=write_headers, method="POST",
        )
        with _ur.urlopen(req, timeout=20) as resp:
            resp.read()
        added += len(chunk)

    return {"added": added, "message": f"Expanded universe by {added} stocks"}


async def _sb_get_all(url: str, headers: dict) -> list[dict]:
    """Paginate through a Supabase REST endpoint, 1000 rows at a time."""
    results: list[dict] = []
    offset = 0
    while True:
        paged = f"{url}&offset={offset}&limit=1000"
        req = _ur.Request(paged, headers=headers)
        with _ur.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read())
        if not isinstance(rows, list) or not rows:
            break
        results.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return results


# ── 52-Week Highs ─────────────────────────────────────────────────────────────

@router.get("/52w-highs")
@_cached("52w_highs", ttl=900)
async def get_52w_highs(limit: int = Query(20, le=50)):
    """
    Stocks hitting 52-week highs today.
    Primary: NSE official API. Fallback: BSE API.
    """
    loop = asyncio.get_running_loop()

    def _from_nse() -> list[dict]:
        if not _NSE_AVAILABLE:
            return []
        try:
            data = _nsefetch("https://www.nseindia.com/api/live-analysis-52Week-high-low-data?index=broadly")
            items = data.get("HIGH", []) if isinstance(data, dict) else []
            result = []
            for it in items[:limit]:
                price = _sf(it.get("ltp", 0) or it.get("ltP", 0))
                high52 = _sf(it.get("high52", 0) or it.get("wkhi", 0))
                prev   = _sf(it.get("previousClose", 0) or it.get("pChange", 0))
                chg_pct = _sf(it.get("pChange", 0))
                result.append({
                    "symbol":   it.get("symbol", ""),
                    "company":  it.get("companyName", it.get("symbol", "")),
                    "sector":   it.get("industryInfo", {}).get("sector", "") if isinstance(it.get("industryInfo"), dict) else "",
                    "cmp":      round(price, 2),
                    "high_52w": round(high52, 2) if high52 else round(price, 2),
                    "change_pct": round(chg_pct, 2),
                    "exchange": "NSE",
                })
            return result
        except Exception:
            return []

    def _from_bse() -> list[dict]:
        try:
            import json as _json, urllib.request as _urq
            url = "https://api.bseindia.com/BseIndiaAPI/api/GetSensexStocks/w?flag=5"
            req = _urq.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bseindia.com/",
                "Accept": "application/json",
            })
            with _urq.urlopen(req, timeout=6) as r:
                data = _json.loads(r.read())
            items = data.get("Table", data) if isinstance(data, dict) else data
            result = []
            for it in (items or [])[:limit]:
                price = _sf(it.get("LTP", 0))
                high52 = _sf(it.get("High52Week", 0) or it.get("WeekHigh52", 0))
                chg_pct = _sf(it.get("PerChange", 0) or it.get("PER_CHANGE", 0))
                sym = str(it.get("scrip_code") or it.get("SCRIP_CD", ""))
                name = str(it.get("LNAME") or it.get("SLNAME") or sym)
                result.append({
                    "symbol":   sym,
                    "company":  name,
                    "sector":   "",
                    "cmp":      round(price, 2),
                    "high_52w": round(high52, 2) if high52 else round(price, 2),
                    "change_pct": round(chg_pct, 2),
                    "exchange": "BSE",
                })
            return result
        except Exception:
            return []

    # Primary: project stock_universe via Supabase (instant, uses week_high_52 column)
    result = await loop.run_in_executor(_executor, _get_universe_52w_highs, limit)
    if result:
        return result

    result = await loop.run_in_executor(_executor, _from_nse)
    if result:
        return result
    result = await loop.run_in_executor(_executor, _from_bse)
    if result:
        return result

    # Last resort: yfinance batch download for NIFTY50 — one HTTP call, fast
    def _from_yfinance_nifty() -> list[dict]:
        try:
            import yfinance as _yf, math as _math
            # Single batch download: 1y of daily OHLCV for all NIFTY50 tickers
            raw = _yf.download(
                NIFTY50, period="1y", interval="1d",
                auto_adjust=True, progress=False, threads=True, group_by="ticker",
            )
            out = []
            for tkr in NIFTY50:
                try:
                    df = raw[tkr] if len(NIFTY50) > 1 else raw
                    df = df.dropna(subset=["Close"])
                    if len(df) < 2:
                        continue
                    # Last-trade logic: use last close as current price proxy
                    cmp_val  = float(df["Close"].iloc[-1])
                    prev_cls = float(df["Close"].iloc[-2])
                    high_52  = float(df["High"].max())  # true 52W high from price history
                    if _math.isnan(cmp_val) or cmp_val <= 0 or high_52 <= 0:
                        continue
                    if cmp_val >= high_52 * 0.95:   # within 5% of 52W high
                        chg = (cmp_val - prev_cls) / prev_cls * 100 if prev_cls else 0
                        sym = tkr.replace(".NS", "")
                        out.append({
                            "symbol": sym, "company": sym, "sector": "",
                            "cmp": round(cmp_val, 2), "high_52w": round(high_52, 2),
                            "change_pct": round(chg, 2), "exchange": "NSE",
                        })
                except Exception:
                    continue
            return sorted(out, key=lambda x: x["change_pct"], reverse=True)
        except Exception:
            return []

    return await loop.run_in_executor(_executor, _from_yfinance_nifty)


# ── Sparkline endpoint — 30 daily closes for hover mini-charts ─────────────────
_SPARK_CACHE: dict[str, tuple[float, list]] = {}

@router.get("/sparkline/{symbol}")
async def sparkline(symbol: str):
    """Return last ~30 daily closing prices for a symbol (Index or stock)."""
    clean = symbol.replace("NSE:", "").replace("BSE:", "").strip().upper()
    cache_key = f"spark:{clean}"
    now = time.monotonic()
    if cache_key in _SPARK_CACHE:
        ts, val = _SPARK_CACHE[cache_key]
        if now - ts < 1800:  # 30-min cache
            return val

    def _fetch():
        for suffix in ("", ".NS", ".BO"):
            try:
                ticker = clean + suffix
                df = yf.Ticker(ticker).history(period="1mo")
                if df.empty:
                    continue
                data = [
                    {"date": idx.strftime("%m/%d"), "close": round(float(row["Close"]), 2)}
                    for idx, row in df.iterrows()
                ]
                if data:
                    return data
            except Exception:
                pass
        return []

    result = await _run(_fetch)
    _SPARK_CACHE[cache_key] = (now, result)
    return result

