"""
Stock screener — VCP, IPO Base, Rocket Base strategies.
Uses yfinance for historical data. Results cached for 1 hour.
Adapted from project-neo screener logic.
"""
from __future__ import annotations

import asyncio
import math
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Query

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=6)

# ── Cache ──────────────────────────────────────────────────────────────────
_cache: dict[str, tuple[float, list[dict]]] = {}
_scan_running: set[str] = set()
CACHE_TTL = 3600  # 1 hour

# ── Universe: Nifty 150 most liquid stocks ─────────────────────────────────
SCAN_UNIVERSE = [
    # Nifty 50
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","KOTAKBANK.NS","BHARTIARTL.NS","ITC.NS","LT.NS",
    "SBIN.NS","AXISBANK.NS","BAJFINANCE.NS","ASIANPAINT.NS","MARUTI.NS",
    "NESTLEIND.NS","TITAN.NS","WIPRO.NS","ULTRACEMCO.NS","ONGC.NS",
    "POWERGRID.NS","NTPC.NS","TECHM.NS","BAJAJFINSV.NS","HCLTECH.NS",
    "SUNPHARMA.NS","DIVISLAB.NS","M&M.NS","TATAMOTORS.NS","TATASTEEL.NS",
    "JSWSTEEL.NS","COALINDIA.NS","GRASIM.NS","CIPLA.NS","DRREDDY.NS",
    "APOLLOHOSP.NS","EICHERMOT.NS","HEROMOTOCO.NS","BPCL.NS","INDUSINDBK.NS",
    "ADANIPORTS.NS","HINDALCO.NS","BAJAJ-AUTO.NS","SBILIFE.NS","HDFCLIFE.NS",
    "BRITANNIA.NS","UPL.NS","SHREECEM.NS","PIDILITIND.NS","ADANIENT.NS",
    # Nifty Next 50
    "ZOMATO.NS","TRENT.NS","JSWINFRA.NS","BAJAJHFL.NS","IRFC.NS",
    "LODHA.NS","LTIM.NS","MAXHEALTH.NS","PERSISTENT.NS","POLYCAB.NS",
    "NAUKRI.NS","SIEMENS.NS","ABB.NS","GODREJPROP.NS","DLF.NS",
    "MANKIND.NS","CANBK.NS","BANKBARODA.NS","PNB.NS","UNIONBANK.NS",
    "NMDC.NS","SAIL.NS","VEDL.NS","ADANIGREEN.NS","TATAPOWER.NS",
    "IOC.NS","GAIL.NS","IRCTC.NS","CONCOR.NS","CHOLAFIN.NS",
    "MUTHOOTFIN.NS","HDFCAMC.NS","SOLARINDS.NS","ANGELONE.NS","BSE.NS",
    "POLICYBZR.NS","COFORGE.NS","MPHASIS.NS","LUPIN.NS","TORNTPHARM.NS",
    "AUROPHARMA.NS","BIOCON.NS","AUBANK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS",
    "VBL.NS","MARICO.NS","COLPAL.NS","DABUR.NS","GODREJCP.NS",
    # Midcap picks
    "KPITTECH.NS","TATAELXSI.NS","PHOENIXLTD.NS","OBEROIRLTY.NS","PRESTIGE.NS",
    "DEEPAKNTR.NS","AARTIIND.NS","CLEAN.NS","LINDEINDIA.NS","INDIGOPNTS.NS",
    "DIXON.NS","AMBER.NS","HAVELLS.NS","CROMPTON.NS","VOLTAS.NS",
    "ASHOKLEY.NS","BHARATFORG.NS","APOLLOTYRE.NS","BALKRISIND.NS","MRF.NS",
    "TIINDIA.NS","MOTHERSON.NS","ENDURANCE.NS","BOSCHLTD.NS","CEATLTD.NS",
    "FORTIS.NS","ALKEM.NS","IPCALAB.NS","LAURUSLABS.NS","GLAND.NS",
    "NATCOPHARM.NS","GRANULES.NS","LICHSGFIN.NS","MANAPPURAM.NS","IIFL.NS",
    "MOTILALOFS.NS","ICICIPRULI.NS","STARHEALTH.NS","ICICIGI.NS","ABCAPITAL.NS",
    "JMFINANCIL.NS","PNBHOUSING.NS","RBLBANK.NS","YESBANK.NS","DCBBANK.NS",
    "KARURVYSYA.NS","BANDHANBNK.NS","TATACOMM.NS","HFCL.NS","IDEA.NS",
    "IREDA.NS","SJVN.NS","NHPC.NS","CESC.NS","TORNTPOWER.NS",
    "ATGL.NS","MGL.NS","IGL.NS","PETRONET.NS","APLAPOLLO.NS",
    "RATNAMANI.NS","JSWSTEEL.NS","JINDALSTEL.NS","HINDCOPPER.NS","NATIONALUM.NS",
    "JKCEMENT.NS","DALMIACEM.NS","RAMCOCEM.NS","ACC.NS","AMBUJACEM.NS",
    "TATACHEM.NS","CHAMBAL.NS","COROMANDEL.NS","BERGEPAINT.NS","KANSAINER.NS",
    "PIDILITIND.NS","AKZONOBEL.NS","SUDARSCHEM.NS","FINEORG.NS","GNFC.NS",
    "NYKAA.NS","DELHIVERY.NS","CARTRADE.NS","FSL.NS","PAYTM.NS",
]

# Deduplicate preserving order
_seen: set[str] = set()
_uniq: list[str] = []
for _t in SCAN_UNIVERSE:
    if _t not in _seen:
        _seen.add(_t); _uniq.append(_t)
SCAN_UNIVERSE = _uniq


# ── Technical helpers ──────────────────────────────────────────────────────

def _sf(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
        return default if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return default


def _ema_series(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def _ema_last(s: pd.Series, period: int) -> float:
    if len(s) < period:
        return _sf(s.iloc[-1]) if len(s) > 0 else 0.0
    return _sf(_ema_series(s, period).iloc[-1])


def _rsi(closes: pd.Series, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    v = rsi.iloc[-1]
    return round(_sf(v, 50.0), 1)


def _hhhl(highs: pd.Series, lows: pd.Series, lookback: int = 40) -> bool:
    if len(highs) < lookback:
        return False
    h = highs.iloc[-lookback:].values
    l = lows.iloc[-lookback:].values
    mid = len(h) // 2
    return (
        h[mid:].mean() > h[:mid].mean() and
        l[mid:].mean() > l[:mid].mean()
    )


def _choc(highs: pd.Series, lows: pd.Series, lookback: int = 5) -> bool:
    if len(lows) < lookback * 2:
        return False
    recent = lows.iloc[-lookback:]
    prior = lows.iloc[-lookback * 2:-lookback]
    return float(recent.min()) < float(prior.min()) * 0.99


def _tight_base(highs: pd.Series, lows: pd.Series, period: int, max_range: float) -> bool:
    if len(highs) < period:
        return False
    h = float(highs.iloc[-period:].max())
    l = float(lows.iloc[-period:].min())
    if l == 0:
        return False
    return (h - l) / l * 100 < max_range


def _volume_contracting(vols: pd.Series, waves: int, wave_size: int) -> bool:
    required = waves * wave_size
    if len(vols) < required:
        return False
    avgs = []
    for i in range(waves):
        seg = vols.iloc[-(required - i * wave_size):-(required - (i + 1) * wave_size)] if (required - (i + 1) * wave_size) > 0 else vols.iloc[-(wave_size):]
        avgs.append(float(seg.replace(0, np.nan).mean()))
    return all(avgs[i] > avgs[i + 1] for i in range(len(avgs) - 1))


def _rocket_move(closes: pd.Series, min_pct: float = 80.0, max_days: int = 56) -> bool:
    if len(closes) < max_days:
        return False
    w = closes.iloc[-max_days:]
    low = float(w.min())
    high = float(w.max())
    if low == 0:
        return False
    return (high - low) / low * 100 >= min_pct


def _correction_from_peak(closes: pd.Series, max_days: int = 56) -> float:
    if len(closes) < max_days:
        return 100.0
    w = closes.iloc[-max_days:]
    peak = float(w.max())
    ltp = float(closes.iloc[-1])
    if peak == 0:
        return 100.0
    return (peak - ltp) / peak * 100


def _wave_avg_ranges(highs: pd.Series, lows: pd.Series, waves: int, wave_size: int) -> list[float] | None:
    required = waves * wave_size
    if len(highs) < required:
        return None
    ranges = []
    for i in range(waves):
        start = -(required - i * wave_size)
        end = -(required - (i + 1) * wave_size) if (required - (i + 1) * wave_size) > 0 else None
        h_seg = highs.iloc[start:end]
        l_seg = lows.iloc[start:end]
        lo = float(l_seg.min())
        if lo == 0:
            return None
        ranges.append((float(h_seg.max()) - lo) / lo * 100)
    return ranges


def _evaluate_stock(ticker: str, df: pd.DataFrame, strategy: str) -> dict | None:
    try:
        closes = df["Close"].astype(float)
        highs = df["High"].astype(float)
        lows = df["Low"].astype(float)
        vols = df["Volume"].astype(float)

        if len(closes) < 30:
            return None

        ltp = _sf(closes.iloc[-1])
        prev = _sf(closes.iloc[-2]) if len(closes) > 1 else ltp
        if ltp == 0:
            return None

        chg_pct = round((ltp - prev) / prev * 100, 2) if prev else 0

        ema_9 = _ema_last(closes, 9)
        ema_10 = _ema_last(closes, 10)
        ema_20 = _ema_last(closes, 20)
        ema_25 = _ema_last(closes, 25)
        ema_50 = _ema_last(closes, 50)
        rsi_val = _rsi(closes)

        if strategy == "vcp":
            conds = {
                "EMA Uptrend (10>20)": ema_10 > ema_20,
                "Price > 10 EMA": ltp > ema_10,
                "Higher High/Low (40d)": _hhhl(highs, lows, 40),
                "Volume Contracting (4×15d)": _volume_contracting(vols, 4, 15),
                "Tight Base <8% (7d)": _tight_base(highs, lows, 7, 8.0),
                "No Change of Character": not _choc(highs, lows, 5),
            }
            # Bonus: wave contraction adds to confidence
            wave_ranges = _wave_avg_ranges(highs, lows, 4, 15)
            if wave_ranges:
                conds["Wave Contraction (4×)"] = all(
                    wave_ranges[i] > wave_ranges[i + 1] for i in range(len(wave_ranges) - 1)
                )

            # Risk params
            pivot_low = float(lows.iloc[-7:].min()) if len(lows) >= 7 else ltp * 0.95
            sl_pct = min((ltp - pivot_low) / ltp * 100, 7.0) if ltp > 0 else 5.0

        elif strategy == "ipo_base":
            conds = {
                "EMA Uptrend (10>20)": ema_10 > ema_20,
                "Price > 20 EMA": ltp > ema_20,
                "Higher High/Low (20d)": _hhhl(highs, lows, 20),
                "Volume Contracting (3×5d)": _volume_contracting(vols, 3, 5),
                "Tight Base <15% (15d)": _tight_base(highs, lows, 15, 15.0),
                "No Change of Character (10d)": not _choc(highs, lows, 10),
            }
            pivot_low = float(lows.iloc[-15:].min()) if len(lows) >= 15 else ltp * 0.92
            sl_pct = min((ltp - pivot_low) / ltp * 100, 8.0) if ltp > 0 else 6.0

        elif strategy == "rocket_base":
            correction = _correction_from_peak(closes, 56)
            conds = {
                "Rocket Move ≥80% (56d)": _rocket_move(closes, 80.0, 56),
                "Correction ≤20% from Peak": correction <= 20.0,
                "Full EMA Stack (9>20>50)": ema_9 > ema_20 and ema_20 > ema_50,
                "Higher High/Low (30d)": _hhhl(highs, lows, 30),
                "Volume Contracting (3×7d)": _volume_contracting(vols, 3, 7),
                "No Change of Character (10d)": not _choc(highs, lows, 10),
            }
            # SL: 10 EMA or 10% fixed, whichever is tighter
            sl_ema_pct = (ltp - ema_10) / ltp * 100 if ema_10 > 0 and ltp > 0 else 10.0
            sl_pct = min(max(sl_ema_pct, 0.5), 10.0)

        else:
            return None

        n_met = sum(1 for v in conds.values() if v)
        n_total = len(conds)
        confidence = round(n_met / n_total * 100) if n_total else 0

        if sl_pct <= 0:
            sl_pct = 3.0

        sl = round(ltp * (1 - sl_pct / 100), 2)
        tp1 = round(ltp * (1 + sl_pct * 3 / 100), 2)
        tp2 = round(ltp * (1 + sl_pct * 5 / 100), 2)

        sym = ticker.replace(".NS", "").replace(".BO", "")
        return {
            "symbol": sym,
            "ticker": ticker,
            "ltp": round(ltp, 2),
            "change_pct": chg_pct,
            "rsi": rsi_val,
            "ema_10": round(ema_10, 2),
            "ema_20": round(ema_20, 2),
            "confidence": confidence,
            "matched_conditions": [k for k, v in conds.items() if v],
            "failed_conditions": [k for k, v in conds.items() if not v],
            "sl": sl,
            "sl_pct": round(sl_pct, 2),
            "tp1": tp1,
            "tp2": tp2,
        }
    except Exception:
        return None


def _run_scan(strategy: str) -> list[dict]:
    """Download historical data and run screener scan."""
    try:
        # Download in batches of 30 to avoid rate limits
        batch_size = 30
        all_results: list[dict] = []
        universe = SCAN_UNIVERSE

        for i in range(0, len(universe), batch_size):
            batch = universe[i:i + batch_size]
            try:
                raw = yf.download(
                    batch,
                    period="150d",
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                )
            except Exception:
                continue

            for ticker in batch:
                try:
                    if len(batch) == 1:
                        df = raw
                    else:
                        if ticker not in raw.columns.get_level_values(0):
                            continue
                        df = raw[ticker]

                    df = df.dropna(subset=["Close"])
                    if len(df) < 30:
                        continue

                    result = _evaluate_stock(ticker, df, strategy)
                    if result:
                        all_results.append(result)
                except Exception:
                    continue

        return sorted(all_results, key=lambda x: -x["confidence"])
    except Exception:
        return []


def _get_or_scan(strategy: str) -> list[dict]:
    now = time.monotonic()
    if strategy in _cache:
        ts, data = _cache[strategy]
        if now - ts < CACHE_TTL:
            return data

    if strategy in _scan_running:
        # Return stale cache or empty while running
        return _cache.get(strategy, (0, []))[1]

    _scan_running.add(strategy)
    try:
        results = _run_scan(strategy)
        _cache[strategy] = (now, results)
        return results
    finally:
        _scan_running.discard(strategy)


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/results")
async def get_screener_results(
    strategy: str = Query("vcp", pattern="^(vcp|ipo_base|rocket_base)$"),
    min_confidence: int = Query(0, ge=0, le=100),
    min_price: float = Query(0.0, ge=0),
    max_price: float = Query(0.0, ge=0),
    symbol: str = Query("", description="Filter by symbol substring"),
):
    """Return cached screener results. Auto-triggers a scan if cache is cold."""
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_executor, _get_or_scan, strategy)

    # Apply filters
    filtered = [
        r for r in results
        if r["confidence"] >= min_confidence
        and (not symbol or symbol.upper() in r["symbol"].upper())
        and (min_price == 0 or r["ltp"] >= min_price)
        and (max_price == 0 or r["ltp"] <= max_price)
    ]

    is_scanning = strategy in _scan_running
    last_scan = None
    if strategy in _cache:
        ts = _cache[strategy][0]
        last_scan = datetime.fromtimestamp(
            time.time() - (time.monotonic() - ts)
        ).strftime("%H:%M:%S")

    return {
        "results": filtered,
        "total": len(filtered),
        "strategy": strategy,
        "is_scanning": is_scanning,
        "last_scan": last_scan,
        "universe_size": len(SCAN_UNIVERSE),
    }


@router.post("/scan")
async def trigger_scan(
    strategy: str = Query("vcp", pattern="^(vcp|ipo_base|rocket_base)$"),
    background_tasks: BackgroundTasks = None,
):
    """Force a fresh scan in the background."""
    if strategy in _cache:
        del _cache[strategy]

    loop = asyncio.get_event_loop()

    def _bg():
        _scan_running.add(strategy)
        try:
            results = _run_scan(strategy)
            _cache[strategy] = (time.monotonic(), results)
        finally:
            _scan_running.discard(strategy)

    loop.run_in_executor(_executor, _bg)
    return {"message": f"Scan triggered for {strategy}", "universe_size": len(SCAN_UNIVERSE)}


@router.get("/status")
async def screener_status():
    """Check which strategies have cached results and which are running."""
    out = {}
    now = time.monotonic()
    for strategy in ["vcp", "ipo_base", "rocket_base"]:
        is_running = strategy in _scan_running
        has_cache = strategy in _cache
        age_mins = round((now - _cache[strategy][0]) / 60, 1) if has_cache else None
        count = len(_cache[strategy][1]) if has_cache else 0
        out[strategy] = {
            "is_running": is_running,
            "has_cache": has_cache,
            "cached_results": count,
            "cache_age_mins": age_mins,
        }
    return out
