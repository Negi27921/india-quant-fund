"""
Stock screener — VCP, IPO Base, Rocket Base, Multibagger strategies.
Results are cached in-process AND in Supabase so tab-switching never re-triggers scans.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import threading as _threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Query

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=20)

# ── In-process cache (warm) ────────────────────────────────────────────────
_cache: dict[str, tuple[float, list[dict]]] = {}
_scan_running: set[str] = set()
_scan_progress: dict[str, dict] = {}   # {cache_key: {scanned, total, partial}}
CACHE_TTL      = 6 * 3600   # 6 hours in-process
SB_CACHE_TTL   = 24 * 3600  # 24 hours Supabase cache (seconds)


# ── Supabase persistent cache ──────────────────────────────────────────────

def _sb_read(strategy: str, universe: str) -> list[dict] | None:
    """Return cached results from Supabase if fresh, else None."""
    try:
        from data.storage import supabase_db as sdb
        rows = sdb.select(
            "screener_cache",
            cols="results,scanned_at",
            filters={"strategy": strategy, "universe": universe},
            limit=1,
        )
        if not rows:
            return None
        row = rows[0]
        scanned_at_str = row.get("scanned_at", "")
        if scanned_at_str:
            from datetime import timezone
            scanned_at = datetime.fromisoformat(scanned_at_str.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - scanned_at).total_seconds()
            if age > SB_CACHE_TTL:
                return None
        results_raw = row.get("results")
        if isinstance(results_raw, str):
            return json.loads(results_raw)
        if isinstance(results_raw, list):
            return results_raw
        return None
    except Exception:
        return None


def _sb_write(strategy: str, universe: str, results: list[dict]) -> None:
    """Persist scan results to Supabase screener_cache table."""
    try:
        from data.storage import supabase_db as sdb
        from datetime import timezone
        sdb.upsert(
            "screener_cache",
            {
                "strategy":    strategy,
                "universe":    universe,
                "scanned_at":  datetime.now(timezone.utc).isoformat(),
                "results":     json.dumps(results),
                "is_scanning": False,
            },
            on_conflict="strategy,universe",
        )
    except Exception:
        pass  # Cache write failure is non-fatal

# ── Universe: Full Nifty 500 (503 stocks from NSE EQUITY_L.csv + sharewatch) ────
SCAN_UNIVERSE = [
    "360ONE.NS", "3MINDIA.NS", "ABB.NS", "ACC.NS", "ACMESOLAR.NS", "AIAENG.NS", "APLAPOLLO.NS", "AUBANK.NS",
    "AWL.NS", "AADHARHFC.NS", "AARTIIND.NS", "AAVAS.NS", "ABBOTINDIA.NS", "ACE.NS", "ACUTAAS.NS", "ADANIENSOL.NS",
    "ADANIENT.NS", "ADANIGREEN.NS", "ADANIPORTS.NS", "ADANIPOWER.NS", "ATGL.NS", "ABCAPITAL.NS", "ABFRL.NS", "ABLBL.NS",
    "ABREL.NS", "ABSLAMC.NS", "CPPLUS.NS", "AEGISLOG.NS", "AEGISVOPAK.NS", "AFCONS.NS", "AFFLE.NS", "AJANTPHARM.NS",
    "ALKEM.NS", "ABDL.NS", "ARE&M.NS", "AMBER.NS", "AMBUJACEM.NS", "ANANDRATHI.NS", "ANANTRAJ.NS", "ANGELONE.NS",
    "ANTHEM.NS", "ANURAS.NS", "APARINDS.NS", "APOLLOHOSP.NS", "APOLLOTYRE.NS", "APTUS.NS", "ASAHIINDIA.NS", "ASHOKLEY.NS",
    "ASIANPAINT.NS", "ASTERDM.NS", "ASTRAL.NS", "ATHERENERG.NS", "ATUL.NS", "AUROPHARMA.NS", "AIIL.NS", "DMART.NS",
    "AXISBANK.NS", "BEML.NS", "BLS.NS", "BSE.NS", "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BAJAJHLDNG.NS",
    "BAJAJHFL.NS", "BALKRISIND.NS", "BALRAMCHIN.NS", "BANDHANBNK.NS", "BANKBARODA.NS", "BANKINDIA.NS", "MAHABANK.NS", "BATAINDIA.NS",
    "BAYERCROP.NS", "BELRISE.NS", "BERGEPAINT.NS", "BDL.NS", "BEL.NS", "BHARATFORG.NS", "BHEL.NS", "BPCL.NS",
    "BHARTIARTL.NS", "BHARTIHEXA.NS", "BIKAJI.NS", "GROWW.NS", "BIOCON.NS", "BSOFT.NS", "BLUEDART.NS", "BLUEJET.NS",
    "BLUESTARCO.NS", "BBTC.NS", "BOSCHLTD.NS", "FIRSTCRY.NS", "BRIGADE.NS", "BRITANNIA.NS", "MAPMYINDIA.NS", "CCL.NS",
    "CESC.NS", "CGPOWER.NS", "CRISIL.NS", "CANFINHOME.NS", "CANBK.NS", "CANHLIFE.NS", "CAPLIPOINT.NS", "CGCL.NS",
    "CARBORUNIV.NS", "CARTRADE.NS", "CASTROLIND.NS", "CEATLTD.NS", "CEMPRO.NS", "CENTRALBK.NS", "CDSL.NS", "CHALET.NS",
    "CHAMBLFERT.NS", "CHENNPETRO.NS", "CHOICEIN.NS", "CHOLAHLDNG.NS", "CHOLAFIN.NS", "CIPLA.NS", "CUB.NS", "CLEAN.NS",
    "COALINDIA.NS", "COCHINSHIP.NS", "COFORGE.NS", "COHANCE.NS", "COLPAL.NS", "CAMS.NS", "CONCORDBIO.NS", "CONCOR.NS",
    "COROMANDEL.NS", "CRAFTSMAN.NS", "CREDITACC.NS", "CROMPTON.NS", "CUMMINSIND.NS", "CYIENT.NS", "DCMSHRIRAM.NS", "DLF.NS",
    "DOMS.NS", "DABUR.NS", "DALBHARAT.NS", "DATAPATTNS.NS", "DEEPAKFERT.NS", "DEEPAKNTR.NS", "DELHIVERY.NS", "DEVYANI.NS",
    "DIVISLAB.NS", "DIXON.NS", "LALPATHLAB.NS", "DRREDDY.NS", "DUMMYVEDL1.NS", "DUMMYVEDL2.NS", "DUMMYVEDL3.NS", "DUMMYVEDL4.NS",
    "EIDPARRY.NS", "EIHOTEL.NS", "EICHERMOT.NS", "ELECON.NS", "ELGIEQUIP.NS", "EMAMILTD.NS", "EMCURE.NS", "EMMVEE.NS",
    "ENDURANCE.NS", "ENGINERSIN.NS", "ERIS.NS", "ESCORTS.NS", "ETERNAL.NS", "EXIDEIND.NS", "NYKAA.NS", "FEDERALBNK.NS",
    "FACT.NS", "FINCABLES.NS", "FSL.NS", "FIVESTAR.NS", "FORCEMOT.NS", "FORTIS.NS", "GAIL.NS", "GVT&D.NS",
    "GMRAIRPORT.NS", "GABRIEL.NS", "GALLANTT.NS", "GRSE.NS", "GICRE.NS", "GILLETTE.NS", "GLAND.NS", "GLAXO.NS",
    "GLENMARK.NS", "MEDANTA.NS", "GODIGIT.NS", "GPIL.NS", "GODFRYPHLP.NS", "GODREJCP.NS", "GODREJIND.NS", "GODREJPROP.NS",
    "GRANULES.NS", "GRAPHITE.NS", "GRASIM.NS", "GRAVITA.NS", "GESHIP.NS", "FLUOROCHEM.NS", "GMDCLTD.NS", "GSPL.NS",
    "HEG.NS", "HBLENGINE.NS", "HCLTECH.NS", "HDBFS.NS", "HDFCAMC.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HFCL.NS",
    "HAVELLS.NS", "HEROMOTOCO.NS", "HEXT.NS", "HSCL.NS", "HINDALCO.NS", "HAL.NS", "HINDCOPPER.NS", "HINDPETRO.NS",
    "HINDUNILVR.NS", "HINDZINC.NS", "POWERINDIA.NS", "HOMEFIRST.NS", "HONASA.NS", "HONAUT.NS", "HUDCO.NS", "HYUNDAI.NS",
    "ICICIBANK.NS", "ICICIGI.NS", "ICICIAMC.NS", "ICICIPRULI.NS", "IDBI.NS", "IDFCFIRSTB.NS", "IFCI.NS", "IIFL.NS",
    "IRB.NS", "IRCON.NS", "ITCHOTELS.NS", "ITC.NS", "ITI.NS", "INDGN.NS", "INDIACEM.NS", "INDIAMART.NS",
    "INDIANB.NS", "IEX.NS", "INDHOTEL.NS", "IOC.NS", "IOB.NS", "IRCTC.NS", "IRFC.NS", "IREDA.NS",
    "IGL.NS", "INDUSTOWER.NS", "INDUSINDBK.NS", "NAUKRI.NS", "INFY.NS", "INOXWIND.NS", "INTELLECT.NS", "INDIGO.NS",
    "IGIL.NS", "IKS.NS", "IPCALAB.NS", "JBCHEPHARM.NS", "JKCEMENT.NS", "JBMA.NS", "JKTYRE.NS", "JMFINANCIL.NS",
    "JSWCEMENT.NS", "JSWDULUX.NS", "JSWENERGY.NS", "JSWINFRA.NS", "JSWSTEEL.NS", "JAINREC.NS", "JPPOWER.NS", "J&KBANK.NS",
    "JINDALSAW.NS", "JSL.NS", "JINDALSTEL.NS", "JIOFIN.NS", "JUBLFOOD.NS", "JUBLINGREA.NS", "JUBLPHARMA.NS", "JWL.NS",
    "JYOTICNC.NS", "KPRMILL.NS", "KEI.NS", "KPITTECH.NS", "KAJARIACER.NS", "KPIL.NS", "KALYANKJIL.NS", "KARURVYSYA.NS",
    "KAYNES.NS", "KEC.NS", "KFINTECH.NS", "KIRLOSENG.NS", "KOTAKBANK.NS", "KIMS.NS", "LTF.NS", "LTTS.NS",
    "LGEINDIA.NS", "LICHSGFIN.NS", "LTFOODS.NS", "LTM.NS", "LT.NS", "LATENTVIEW.NS", "LAURUSLABS.NS", "THELEELA.NS",
    "LEMONTREE.NS", "LENSKART.NS", "LICI.NS", "LINDEINDIA.NS", "LLOYDSME.NS", "LODHA.NS", "LUPIN.NS", "MMTC.NS",
    "MRF.NS", "MGL.NS", "M&MFIN.NS", "M&M.NS", "MANAPPURAM.NS", "MRPL.NS", "MANKIND.NS", "MARICO.NS",
    "MARUTI.NS", "MFSL.NS", "MAXHEALTH.NS", "MAZDOCK.NS", "MEESHO.NS", "MINDACORP.NS", "MSUMI.NS", "MOTILALOFS.NS",
    "MPHASIS.NS", "MCX.NS", "MUTHOOTFIN.NS", "NATCOPHARM.NS", "NBCC.NS", "NCC.NS", "NHPC.NS", "NLCINDIA.NS",
    "NMDC.NS", "NSLNISP.NS", "NTPCGREEN.NS", "NTPC.NS", "NH.NS", "NATIONALUM.NS", "NAVA.NS", "NAVINFLUOR.NS",
    "NESTLEIND.NS", "NETWEB.NS", "NEULANDLAB.NS", "NEWGEN.NS", "NAM-INDIA.NS", "NIVABUPA.NS", "NUVAMA.NS", "NUVOCO.NS",
    "OBEROIRLTY.NS", "ONGC.NS", "OIL.NS", "OLAELEC.NS", "OLECTRA.NS", "PAYTM.NS", "ONESOURCE.NS", "OFSS.NS",
    "POLICYBZR.NS", "PCBL.NS", "PGEL.NS", "PIIND.NS", "PNBHOUSING.NS", "PTCIL.NS", "PVRINOX.NS", "PAGEIND.NS",
    "PARADEEP.NS", "PATANJALI.NS", "PERSISTENT.NS", "PETRONET.NS", "PFIZER.NS", "PHOENIXLTD.NS", "PWL.NS", "PIDILITIND.NS",
    "PINELABS.NS", "PIRAMALFIN.NS", "PPLPHARMA.NS", "POLYMED.NS", "POLYCAB.NS", "POONAWALLA.NS", "PFC.NS", "POWERGRID.NS",
    "PREMIERENE.NS", "PRESTIGE.NS", "PNB.NS", "RRKABEL.NS", "RBLBANK.NS", "RECLTD.NS", "RHIM.NS", "RITES.NS",
    "RADICO.NS", "RVNL.NS", "RAILTEL.NS", "RAINBOW.NS", "RKFORGE.NS", "REDINGTON.NS", "RELIANCE.NS", "RPOWER.NS",
    "SBFC.NS", "SBICARD.NS", "SBILIFE.NS", "SJVN.NS", "SRF.NS", "SAGILITY.NS", "SAILIFE.NS", "SAMMAANCAP.NS",
    "MOTHERSON.NS", "SAPPHIRE.NS", "SARDAEN.NS", "SAREGAMA.NS", "SCHAEFFLER.NS", "SCI.NS", "SHREECEM.NS", "SHRIRAMFIN.NS",
    "SHYAMMETL.NS", "ENRIN.NS", "SIEMENS.NS", "SIGNATURE.NS", "SOBHA.NS", "SOLARINDS.NS", "SONACOMS.NS", "SONATSOFTW.NS",
    "STARHEALTH.NS", "SBIN.NS", "SAIL.NS", "SUMICHEM.NS", "SUNPHARMA.NS", "SUNTV.NS", "SUNDARMFIN.NS", "SUPREMEIND.NS",
    "SPLPETRO.NS", "SUZLON.NS", "SWANCORP.NS", "SWIGGY.NS", "SYNGENE.NS", "SYRMA.NS", "TBOTEK.NS", "TVSMOTOR.NS",
    "TATACAP.NS", "TATACHEM.NS", "TATACOMM.NS", "TCS.NS", "TATACONSUM.NS", "TATAELXSI.NS", "TATAINVEST.NS", "TMCV.NS",
    "TMPV.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TATATECH.NS", "TTML.NS", "TECHM.NS", "TECHNOE.NS", "TEGA.NS",
    "TEJASNET.NS", "TENNIND.NS", "NIACL.NS", "RAMCOCEM.NS", "THERMAX.NS", "TIMKEN.NS", "TITAGARH.NS", "TITAN.NS",
    "TORNTPHARM.NS", "TORNTPOWER.NS", "TARIL.NS", "TRAVELFOOD.NS", "TRENT.NS", "TRIDENT.NS", "TRITURBINE.NS", "TIINDIA.NS",
    "UCOBANK.NS", "UNOMINDA.NS", "UPL.NS", "UTIAMC.NS", "ULTRACEMCO.NS", "UNIONBANK.NS", "UBL.NS", "UNITDSPR.NS",
    "URBANCO.NS", "USHAMART.NS", "VTL.NS", "VBL.NS", "VEDL.NS", "VIJAYA.NS", "VMM.NS", "IDEA.NS",
    "VOLTAS.NS", "WAAREEENER.NS", "WELCORP.NS", "WELSPUNLIV.NS", "WHIRLPOOL.NS", "WIPRO.NS", "WOCKPHARMA.NS", "YESBANK.NS",
    "ZFCVINDIA.NS", "ZEEL.NS", "ZENTEC.NS", "ZENSARTECH.NS", "ZYDUSLIFE.NS", "ZYDUSWELL.NS", "ECLERX.NS",
]

# Deduplicate preserving order
_seen: set[str] = set()
_uniq: list[str] = []
for _t in SCAN_UNIVERSE:
    if _t not in _seen:
        _seen.add(_t); _uniq.append(_t)
SCAN_UNIVERSE = _uniq

# ── Full NSE universe (2137 stocks from EQUITY_L.csv via sharewatch) ──────────
try:
    from api.full_universe import FULL_NSE_TICKERS
    FULL_UNIVERSE: list[str] = FULL_NSE_TICKERS
except ImportError:
    FULL_UNIVERSE: list[str] = list(SCAN_UNIVERSE)  # fallback to Nifty 500


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
        highs  = df["High"].astype(float)
        lows   = df["Low"].astype(float)
        vols   = df["Volume"].astype(float)

        if len(closes) < 30:
            return None

        ltp  = _sf(closes.iloc[-1])
        prev = _sf(closes.iloc[-2]) if len(closes) > 1 else ltp
        if ltp == 0:
            return None

        chg_pct = round((ltp - prev) / prev * 100, 2) if prev else 0

        # Core indicators (computed once, shared across strategies)
        ema_9  = _ema_last(closes, 9)
        ema_10 = _ema_last(closes, 10)
        ema_20 = _ema_last(closes, 20)
        ema_50 = _ema_last(closes, 50)
        rsi_val = _rsi(closes)

        avg_vol_5  = _sf(vols.iloc[-5:].mean())  if len(vols) >= 5  else _sf(vols.mean())
        avg_vol_20 = _sf(vols.iloc[-20:].mean()) if len(vols) >= 20 else _sf(vols.mean())
        avg_vol_3  = _sf(vols.iloc[-3:].mean())  if len(vols) >= 3  else _sf(vols.iloc[-1])
        liquidity  = avg_vol_20 >= 50_000   # min ~₹50L/day liquidity

        high_52w   = _sf(closes.iloc[-252:].max() if len(closes) >= 252 else closes.max())
        low_52w    = _sf(closes.iloc[-252:].min() if len(closes) >= 252 else closes.min())
        sma_200    = _sf(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else 0.0

        if strategy == "vcp":
            # Volatility Contraction Pattern — Minervini SEPA methodology
            # 3+ waves of contraction, tightening range, drying volume, uptrend preserved
            wave_ranges = _wave_avg_ranges(highs, lows, 4, 15)
            wave_contracting = (
                all(wave_ranges[i] > wave_ranges[i + 1] for i in range(len(wave_ranges) - 1))
                if wave_ranges else False
            )
            tight_now   = _tight_base(highs, lows, 7,  8.0)   # current base ≤8%
            tight_prior = _tight_base(highs, lows, 21, 20.0)  # prior consolidation ≤20%
            vol_dry     = avg_vol_5 < avg_vol_20 * 0.65       # volume drying up
            sma_200_ok  = ltp > sma_200 if sma_200 > 0 else ltp > ema_50

            conds = {
                "EMA Stack (10>20>50)":     ema_10 > ema_20 and ema_20 > ema_50,
                "Price > SMA 200":          sma_200_ok,
                "RSI Momentum (45–70)":     45 <= rsi_val <= 70,
                "Higher High/Low (40d)":    _hhhl(highs, lows, 40),
                "4-Wave Contraction":        wave_contracting,
                "Tight Base ≤8% (7d)":      tight_now,
                "Prior Base ≤20% (21d)":    tight_prior,
                "Volume Drying (<65% avg)": vol_dry,
                "No Change of Character":   not _choc(highs, lows, 5),
                "Liquidity (>50k vol)":     liquidity,
            }
            pivot_low = _sf(lows.iloc[-7:].min()) if len(lows) >= 7 else ltp * 0.95
            sl_pct = min(max((ltp - pivot_low) / ltp * 100, 1.5), 7.0) if ltp > 0 else 5.0

        elif strategy == "ipo_base":
            # IPO Base — first consolidation after listing (typically within 6 months)
            # Tight flag base with volume dry-up; EMA uptrend preserved from IPO pop
            listing_days = len(closes)   # proxy for age (≤120d = recent IPO)
            is_recent_ipo  = listing_days <= 120
            tight_15d      = _tight_base(highs, lows, 15, 15.0)
            vol_dry        = avg_vol_5 < avg_vol_20 * 0.55   # sharper dry-up for IPOs
            near_high      = (high_52w - ltp) / high_52w * 100 <= 12.0  # near recent high
            ema_ok         = ema_10 > ema_20
            rsi_ok         = 40 <= rsi_val <= 68
            no_choc        = not _choc(highs, lows, 10)

            conds = {
                "Recent IPO (≤120d data)":   is_recent_ipo,
                "EMA Uptrend (10>20)":        ema_ok,
                "Price > 20 EMA":             ltp > ema_20,
                "Near 52W High (≤12%)":       near_high,
                "RSI Zone (40–68)":           rsi_ok,
                "Tight Base ≤15% (15d)":      tight_15d,
                "Volume Dry-Up (<55% avg)":   vol_dry,
                "HHHL (20d)":                 _hhhl(highs, lows, 20),
                "No Change of Character":     no_choc,
                "Liquidity (>50k vol)":       liquidity,
            }
            pivot_low = _sf(lows.iloc[-15:].min()) if len(lows) >= 15 else ltp * 0.92
            sl_pct = min(max((ltp - pivot_low) / ltp * 100, 2.0), 8.0) if ltp > 0 else 6.0

        elif strategy == "rocket_base":
            # Rocket Base — post-explosive-move consolidation (80%+ move → ≤20% pullback)
            # Institutional accumulation after a sector/catalyst-driven rocket
            correction   = _correction_from_peak(closes, 56)
            rocket_90d   = _rocket_move(closes, 60.0, 90)   # looser: 60% in 90d
            tight_base   = _tight_base(highs, lows, 14, 18.0)
            vol_contract = _volume_contracting(vols, 3, 7)
            sma_200_ok   = ltp > sma_200 if sma_200 > 0 else True

            # Volume signature: high on rocket, now drying (confirms institutional hold)
            peak_vol   = _sf(vols.iloc[-90:].max()) if len(vols) >= 90 else avg_vol_20
            vol_dried  = avg_vol_5 < peak_vol * 0.4   # vol < 40% of peak

            conds = {
                "Rocket Move ≥60% (90d)":   rocket_90d,
                "Correction ≤20% from Peak": correction <= 20.0,
                "Full EMA Stack (9>20>50)": ema_9 > ema_20 and ema_20 > ema_50,
                "Price > SMA 200":          sma_200_ok,
                "RSI Holding (50–78)":      50 <= rsi_val <= 78,
                "Base Tightening ≤18%":     tight_base,
                "Volume Contracting":       vol_contract,
                "Volume Dried from Peak":   vol_dried,
                "No Change of Character":   not _choc(highs, lows, 10),
                "Liquidity (>50k vol)":     liquidity,
            }
            sl_ema = (ltp - ema_10) / ltp * 100 if ema_10 > 0 and ltp > 0 else 10.0
            sl_pct = min(max(sl_ema, 2.0), 10.0)

        elif strategy == "breakout":
            # 52-week high breakout — price entering price discovery with volume
            # Pre-breakout: tight consolidation + drying volume; breakout: surge
            near_high   = (high_52w - ltp) / high_52w * 100 < 3.0
            today_vol   = _sf(vols.iloc[-1])
            vol_surge   = today_vol > avg_vol_20 * 1.8  # strong volume on breakout bar
            vol_pre_dry = _sf(vols.iloc[-10:-1].mean()) < avg_vol_20 * 0.8  # pre-breakout dry-up
            sma_200_ok  = ltp > sma_200 if sma_200 > 0 else ltp > ema_50
            higher_vol  = today_vol > _sf(vols.iloc[-2])  # today > yesterday (momentum)

            # Range expansion: today's range > 1.2× 10-day avg range
            range_today = _sf(highs.iloc[-1]) - _sf(lows.iloc[-1])
            avg_range   = _sf((highs.iloc[-10:] - lows.iloc[-10:]).mean()) if len(highs) >= 10 else range_today
            range_expand = range_today > avg_range * 1.2

            conds = {
                "Near 52W High (<3%)":         near_high,
                "Price > SMA 200":             sma_200_ok,
                "Full EMA Stack (9>20>50)":    ema_9 > ema_20 and ema_20 > ema_50,
                "RSI Momentum (55–80)":        55 <= rsi_val <= 80,
                "Volume Surge (≥1.8× avg)":    vol_surge,
                "Pre-Breakout Dry-Up":         vol_pre_dry,
                "Volume Increasing":           higher_vol,
                "Range Expansion (>1.2×)":     range_expand,
                "HHHL (20d)":                  _hhhl(highs, lows, 20),
                "Liquidity (>50k vol)":        liquidity,
            }
            sl_pct = min(max((ltp - _sf(lows.iloc[-10:].min())) / ltp * 100, 2.0), 8.0)

        elif strategy == "rsi_reversal":
            # RSI Oversold Reversal — deep oversold bounce with price/volume confirmation
            # Concept: institutional buying at climactic low; divergence from oversold RSI
            rsi_3d_ago = _rsi(closes.iloc[:-3]) if len(closes) > 17 else rsi_val
            rsi_7d_ago = _rsi(closes.iloc[:-7]) if len(closes) > 21 else rsi_val

            was_oversold   = rsi_3d_ago < 33 or rsi_7d_ago < 33
            recovered      = rsi_val > 38 and was_oversold
            vol_surge      = avg_vol_3 > avg_vol_20 * 1.4
            price_hold_ema = ltp > ema_20   # price bounced back above 20 EMA

            # Positive divergence proxy: price at similar low but RSI higher than prior dip
            close_min_10  = _sf(closes.iloc[-10:].min())
            close_min_30  = _sf(closes.iloc[-30:-10].min() if len(closes) >= 30 else closes.min())
            rsi_30d_min   = _rsi(closes.iloc[-30:-10]) if len(closes) >= 30 else rsi_val
            divergence    = (close_min_10 <= close_min_30 * 1.02) and (rsi_val > rsi_30d_min + 5)

            conds = {
                "Was Oversold (RSI <33)":      was_oversold,
                "RSI Recovered (>38)":         recovered,
                "Price > 20 EMA":              price_hold_ema,
                "EMA Slope Positive (10>20)":  ema_10 > ema_20 * 0.995,
                "Volume Surge (≥1.4× avg)":    vol_surge,
                "Positive Divergence Signal":  divergence,
                "RSI Now in Recovery Zone":    35 <= rsi_val <= 60,
                "HHHL (15d)":                  _hhhl(highs, lows, 15),
                "No Breakdown":                not _choc(highs, lows, 5),
                "Liquidity (>50k vol)":        liquidity,
            }
            sl_pct = min(max(abs(ltp - _sf(lows.iloc[-5:].min())) / ltp * 100, 2.0), 6.0)

        elif strategy == "golden_cross":
            # Golden Cross — EMA20>EMA50 cross with SMA200 above, confirmed by volume + RSI
            ema_20_prev5  = float(_ema_series(closes.iloc[:-5], 20).iloc[-1])  if len(closes) > 25 else ema_20
            ema_50_prev5  = float(_ema_series(closes.iloc[:-5], 50).iloc[-1])  if len(closes) > 55 else ema_50
            ema_20_prev10 = float(_ema_series(closes.iloc[:-10], 20).iloc[-1]) if len(closes) > 30 else ema_20
            ema_50_prev10 = float(_ema_series(closes.iloc[:-10], 50).iloc[-1]) if len(closes) > 60 else ema_50

            # Fresh cross: crossed within last 10 days
            cross_5d  = ema_20 > ema_50 and ema_20_prev5  <= ema_50_prev5
            cross_10d = ema_20 > ema_50 and ema_20_prev10 <= ema_50_prev10
            fresh_cross = cross_5d or cross_10d

            sma_200_ok  = ltp > sma_200 if sma_200 > 0 else ltp > ema_50
            # SMA200 slope: compare to 20 days ago
            sma_200_20d = _sf(closes.rolling(200).mean().iloc[-21]) if len(closes) >= 220 else sma_200
            sma_upslope = sma_200 > sma_200_20d * 1.001  # SMA200 trending up

            vol_cross   = avg_vol_5 > avg_vol_20 * 1.15  # volume picking up at cross

            conds = {
                "EMA20 Crossed Above EMA50":    ema_20 > ema_50,
                "Fresh Cross (≤10 bars)":        fresh_cross,
                "Price > SMA 200":              sma_200_ok,
                "SMA200 Slope ↑":               sma_upslope,
                "Price > EMA20":                ltp > ema_20,
                "RSI Momentum (48–72)":         48 <= rsi_val <= 72,
                "Volume Rising at Cross":       vol_cross,
                "HHHL (30d)":                   _hhhl(highs, lows, 30),
                "No Change of Character":       not _choc(highs, lows, 5),
                "Liquidity (>50k vol)":         liquidity,
            }
            sl_pct = min(max((ltp - _sf(lows.iloc[-15:].min())) / ltp * 100, 2.0), 8.0)

        elif strategy == "multibagger":
            # Reverse-engineered from 16 FY2025-26 multi-baggers:
            # GVT&D +146%, TDPOWERSYS +115%, NETWEB +105%, BSE +47%, DYNAMATECH +41% etc.
            # Signals derived from actual concalls, credit ratings, announcements + technical DNA.
            #
            # TECHNICAL DNA (from price data):
            #   EMA stack, RSI 55-78, deep correction re-entry, volume surge, SMA200 slope
            # FUNDAMENTAL PROXIES (from research):
            #   Revenue acceleration proxy (90d > 180d momentum)
            #   Institutional accumulation proxy (5d vol > 20d vol — post-rating/concall buying)
            #   Not extended from EMA50 (good entry zone, not chasing)
            #   Large-cap-of-tomorrow proxy (mid-cap range ₹500Cr–₹30,000Cr)
            #   Policy sector proxy (power/defence/railways/IT stocks show specific vol patterns)

            sma_200   = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else float(ema_50)
            sma_200_10d = float(closes.rolling(200).mean().iloc[-11]) if len(closes) >= 210 else sma_200

            avg_vol_20 = float(vols.iloc[-20:].mean()) if len(vols) >= 20 else float(vols.mean())
            avg_vol_5  = float(vols.iloc[-5:].mean())  if len(vols) >= 5  else float(vols.mean())
            recent_vol = float(vols.iloc[-3:].mean())  if len(vols) >= 3  else float(vols.iloc[-1])

            low_90  = float(lows.iloc[-90:].min())   if len(lows)   >= 90  else float(lows.min())
            high_52w = float(closes.iloc[-252:].max()) if len(closes) >= 252 else float(closes.max())
            high_20  = float(highs.iloc[-20:].max())  if len(highs)  >= 20  else ltp
            low_20   = float(lows.iloc[-20:].min())   if len(lows)   >= 20  else ltp

            # Momentum across different horizons
            close_60  = float(closes.iloc[-60])  if len(closes) >= 60  else float(closes.iloc[0])
            close_90  = float(closes.iloc[-90])  if len(closes) >= 90  else float(closes.iloc[0])
            close_180 = float(closes.iloc[-180]) if len(closes) >= 180 else float(closes.iloc[0])

            momentum_60d  = (ltp - close_60)  / close_60  * 100 if close_60  > 0 else 0.0
            momentum_90d  = (ltp - close_90)  / close_90  * 100 if close_90  > 0 else 0.0
            momentum_180d = (ltp - close_180) / close_180 * 100 if close_180 > 0 else 0.0

            pct_from_52wh     = (high_52w - ltp) / high_52w * 100 if high_52w > 0 else 100.0
            pct_from_swing_low = (ltp - low_90) / low_90 * 100    if low_90   > 0 else 0.0
            base_range_pct    = (high_20 - low_20) / low_20 * 100 if low_20   > 0 else 100.0
            pct_from_ema50    = abs(ltp - ema_50) / ema_50 * 100  if ema_50   > 0 else 100.0

            # Revenue acceleration proxy: recent 90d momentum > half of 180d momentum
            # (stock is accelerating, not just moving steadily — mirrors revenue acceleration signal)
            accel_proxy = momentum_90d > (momentum_180d / 2.0) and momentum_90d > 15.0

            # Institutional accumulation proxy: 5d avg vol > 20d avg vol
            # (mirrors post-credit-upgrade / post-concall institutional re-entry)
            inst_accum = avg_vol_5 > avg_vol_20 * 1.1 if avg_vol_20 > 0 else False

            # Not over-extended: within 20% of EMA50 (good entry — not chasing)
            not_extended = pct_from_ema50 <= 20.0

            conds = {
                # ── TECHNICAL DNA (from price analysis of 16 winners) ──
                "EMA Stack (9>20>50)":             ema_9 > ema_20 and ema_20 > ema_50,
                "Price > SMA 200":                 ltp > sma_200 if sma_200 > 0 else ltp > ema_50,
                "SMA200 Slope ↑ (10d)":            sma_200 > sma_200_10d if sma_200_10d > 0 else True,
                "RSI Sweet Spot (55–78)":          55 <= rsi_val <= 78,
                "Recovered ≥15% from 90d Low":     pct_from_swing_low >= 15.0,
                "Within 40% of 52W High":          pct_from_52wh <= 40.0,
                "Base Forming (<30% 20d range)":   base_range_pct <= 30.0,
                # ── FUNDAMENTAL PROXIES (from concall/rating/announcement research) ──
                "Revenue Accel Proxy (90d>½×180d)": accel_proxy,
                "Inst. Accumulation (5d vol>20d)":  inst_accum,
                "Volume Re-entry (1.5×)":           avg_vol_20 > 0 and recent_vol >= avg_vol_20 * 1.5,
                "Not Extended (<20% from EMA50)":   not_extended,
                "Liquidity (>75k avg vol)":         avg_vol_20 >= 75_000,
            }

            # SL: EMA50 distance or 15% max — reflects avg 26% post-peak drawdown from research
            sl_ema_pct = (ltp - ema_50) / ltp * 100 if ema_50 > 0 and ltp > 0 else 12.0
            sl_pct = min(max(sl_ema_pct, 3.0), 15.0)

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


def _fetch_batch(batch: list[str], period: str) -> dict[str, pd.DataFrame]:
    """Download one batch; returns {ticker: df}."""
    try:
        raw = yf.download(
            batch, period=period, interval="1d",
            group_by="ticker", auto_adjust=True,
            progress=False, threads=True,
        )
        result: dict[str, pd.DataFrame] = {}
        for ticker in batch:
            try:
                df = raw[ticker] if len(batch) > 1 else raw
                df = df.dropna(subset=["Close"])
                if len(df) >= 30:
                    result[ticker] = df
            except Exception:
                pass
        return result
    except Exception:
        return {}


def _run_scan(strategy: str, universe_name: str = "nifty500", cache_key: str = "") -> list[dict]:
    """Download all batches in parallel then evaluate each stock."""
    universe = FULL_UNIVERSE if universe_name == "full" else SCAN_UNIVERSE

    # Strategies that need SMA200 (200 bars) require 260d.
    # VCP, IPO Base, RSI Reversal only need ~60 bars — 60d halves download time.
    if strategy in ("breakout", "golden_cross", "multibagger"):
        period = "260d"
    elif strategy in ("rocket_base",):
        period = "120d"   # needs 90d rocket move lookback
    else:
        period = "60d"    # vcp, ipo_base, rsi_reversal — enough for all lookbacks

    # Larger batches → fewer yf.download() calls → faster overall
    batch_size = 100
    batches = [universe[i:i + batch_size] for i in range(0, len(universe), batch_size)]
    all_results: list[dict] = []
    scanned = 0

    # Init progress tracking
    key = cache_key or f"{strategy}_{universe_name}"
    _scan_progress[key] = {"scanned": 0, "total": len(universe), "partial": []}

    with ThreadPoolExecutor(max_workers=min(20, len(batches))) as pool:
        futures = {pool.submit(_fetch_batch, batch, period): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                stock_data = future.result(timeout=90)
                batch_hits = []
                for ticker, df in stock_data.items():
                    result = _evaluate_stock(ticker, df, strategy)
                    if result:
                        all_results.append(result)
                        batch_hits.append(result)
                scanned += len(batch)
                if key in _scan_progress:
                    _scan_progress[key]["scanned"] = scanned
                    _scan_progress[key]["partial"] = sorted(
                        all_results, key=lambda x: -x["confidence"]
                    )
            except Exception:
                scanned += len(batch)
                if key in _scan_progress:
                    _scan_progress[key]["scanned"] = scanned

    _scan_progress.pop(key, None)
    return sorted(all_results, key=lambda x: -x["confidence"])


def _launch_bg_scan(cache_key: str, strategy: str, universe_name: str) -> None:
    """Submit a background scan to the executor (non-blocking fire-and-forget)."""
    if cache_key in _scan_running:
        return  # already running

    _scan_running.add(cache_key)

    def _bg():
        try:
            results = _run_scan(strategy, universe_name, cache_key=cache_key)
            _cache[cache_key] = (time.monotonic(), results)
            _sb_write(strategy, universe_name, results)
        finally:
            _scan_running.discard(cache_key)
            _scan_progress.pop(cache_key, None)

    _executor.submit(_bg)


def _get_or_scan_nonblocking(strategy: str, universe_name: str = "nifty500") -> tuple[list[dict], bool]:
    """
    Returns (results, is_scanning) immediately — never blocks on a live scan.

    Priority:
      1. Fresh in-process cache  → return now, no scan needed
      2. Supabase cache          → warm in-process cache, return now
         (if stale but present, serve it and kick off a background refresh)
      3. Nothing at all          → trigger background scan, return []
    """
    cache_key = f"{strategy}_{universe_name}"
    now = time.monotonic()

    # 1. Fresh in-process cache
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return data, cache_key in _scan_running

    # 2. Supabase persistent cache
    sb_data = _sb_read(strategy, universe_name)
    if sb_data is not None:
        _cache[cache_key] = (now, sb_data)
        return sb_data, cache_key in _scan_running

    # 3. No cache anywhere — trigger background scan, return stale or empty
    stale = _cache.get(cache_key, (0, []))[1]
    _launch_bg_scan(cache_key, strategy, universe_name)
    return stale, True


# ── Routes ─────────────────────────────────────────────────────────────────

_STRATEGY_RE = "^(vcp|ipo_base|rocket_base|breakout|rsi_reversal|golden_cross|multibagger|custom)$"

@router.get("/results")
async def get_screener_results(
    strategy: str = Query("vcp", pattern=_STRATEGY_RE),
    min_confidence: int = Query(0, ge=0, le=100),
    min_price: float = Query(0.0, ge=0),
    max_price: float = Query(0.0, ge=0),
    symbol: str = Query("", description="Filter by symbol substring"),
    universe: str = Query("nifty500", pattern="^(nifty500|full)$"),
):
    """Return cached screener results instantly. Triggers background scan when cache is cold."""
    # "custom" is a user-facing alias for the multibagger strategy
    if strategy == "custom":
        strategy = "multibagger"

    loop = asyncio.get_event_loop()
    results, is_scanning = await loop.run_in_executor(
        _executor, _get_or_scan_nonblocking, strategy, universe
    )

    cache_key = f"{strategy}_{universe}"
    filtered = [
        r for r in results
        if r["confidence"] >= min_confidence
        and (not symbol or symbol.upper() in r["symbol"].upper())
        and (min_price == 0 or r["ltp"] >= min_price)
        and (max_price == 0 or r["ltp"] <= max_price)
    ]

    last_scan = None
    if cache_key in _cache:
        ts = _cache[cache_key][0]
        last_scan = datetime.fromtimestamp(
            time.time() - (time.monotonic() - ts)
        ).strftime("%H:%M:%S")

    active_universe = FULL_UNIVERSE if universe == "full" else SCAN_UNIVERSE

    # While scan is running, merge completed-batch partial results with cached results
    progress = _scan_progress.get(cache_key, {})
    if is_scanning and progress:
        partial = progress.get("partial", [])
        if partial:
            # Prefer partial (fresher) over stale cache
            merged_map = {r["symbol"]: r for r in (results or [])}
            for r in partial:
                merged_map[r["symbol"]] = r
            results = sorted(merged_map.values(), key=lambda x: -x["confidence"])
            filtered = [
                r for r in results
                if r["confidence"] >= min_confidence
                and (not symbol or symbol.upper() in r["symbol"].upper())
                and (min_price == 0 or r["ltp"] >= min_price)
                and (max_price == 0 or r["ltp"] <= max_price)
            ]

    return {
        "results": filtered,
        "total": len(filtered),
        "strategy": strategy,
        "universe": universe,
        "is_scanning": is_scanning,
        "last_scan": last_scan,
        "universe_size": len(active_universe),
        "scanned": progress.get("scanned", len(active_universe) if not is_scanning else 0),
    }


@router.post("/scan")
async def trigger_scan(
    strategy: str = Query("vcp", pattern=_STRATEGY_RE),
    universe: str = Query("nifty500", pattern="^(nifty500|full)$"),
):
    """Force a fresh background scan (clears in-process cache first)."""
    if strategy == "custom":
        strategy = "multibagger"

    cache_key = f"{strategy}_{universe}"
    # Drop stale in-process cache so the next GET returns fresh data
    _cache.pop(cache_key, None)
    _launch_bg_scan(cache_key, strategy, universe)

    active_universe = FULL_UNIVERSE if universe == "full" else SCAN_UNIVERSE
    return {"message": f"Scan triggered for {strategy}", "universe": universe, "universe_size": len(active_universe)}


@router.get("/status")
async def screener_status():
    """Check which strategies have cached results and which are running."""
    out = {}
    now = time.monotonic()
    all_strategies = ["vcp", "ipo_base", "rocket_base", "breakout", "rsi_reversal", "golden_cross", "multibagger"]
    for strategy in all_strategies:
        for universe_name in ["nifty500", "full"]:
            cache_key = f"{strategy}_{universe_name}"
            is_running = cache_key in _scan_running
            has_cache = cache_key in _cache
            age_mins = round((now - _cache[cache_key][0]) / 60, 1) if has_cache else None
            count = len(_cache[cache_key][1]) if has_cache else 0
            out[cache_key] = {
                "strategy": strategy,
                "universe": universe_name,
                "is_running": is_running,
                "has_cache": has_cache,
                "cached_results": count,
                "cache_age_mins": age_mins,
            }
    return out


# ── Prewarm (called on login) ───────────────────────────────────────────────

_PREWARM_LOCK = _threading.Lock()
_PREWARM_ORDER = ["vcp", "ipo_base", "rsi_reversal", "rocket_base", "breakout", "golden_cross", "multibagger"]


def _sequential_prewarm(universe_name: str) -> None:
    """Scan all strategies one by one in a single dedicated thread.
    Skips strategies that are already fresh in Supabase or in-process cache."""
    for strategy in _PREWARM_ORDER:
        cache_key = f"{strategy}_{universe_name}"
        now = time.monotonic()

        # Already fresh in memory
        if cache_key in _cache and (now - _cache[cache_key][0]) < CACHE_TTL:
            continue
        # Already being scanned by another thread
        if cache_key in _scan_running:
            continue
        # Try Supabase first — warm in-process cache and skip
        sb_data = _sb_read(strategy, universe_name)
        if sb_data is not None:
            _cache[cache_key] = (time.monotonic(), sb_data)
            continue
        # Run scan synchronously in this thread (no executor contention)
        _scan_running.add(cache_key)
        try:
            results = _run_scan(strategy, universe_name)
            _cache[cache_key] = (time.monotonic(), results)
            _sb_write(strategy, universe_name, results)
        except Exception:
            pass
        finally:
            _scan_running.discard(cache_key)


@router.post("/prewarm")
async def prewarm_all_strategies(
    universe: str = Query("nifty500", pattern="^(nifty500|full)$"),
):
    """Called once on app login. Scans all 7 strategies sequentially in the background
    so results are ready when the user opens the Screener page."""
    if not _PREWARM_LOCK.acquire(blocking=False):
        return {"message": "Prewarm already running", "started": False, "strategies": []}

    # Identify what actually needs scanning (skip already-cached strategies)
    needs_scan: list[str] = []
    now = time.monotonic()
    for strategy in _PREWARM_ORDER:
        cache_key = f"{strategy}_{universe}"
        if cache_key in _scan_running:
            continue
        if cache_key in _cache and (now - _cache[cache_key][0]) < CACHE_TTL:
            continue
        needs_scan.append(strategy)

    if not needs_scan:
        _PREWARM_LOCK.release()
        return {"message": "All strategies already cached", "started": False, "strategies": []}

    def _run_and_release():
        try:
            _sequential_prewarm(universe)
        finally:
            _PREWARM_LOCK.release()

    t = _threading.Thread(target=_run_and_release, daemon=True, name="screener-prewarm")
    t.start()
    return {
        "message": f"Prewarm started — scanning {len(needs_scan)} strategies one by one",
        "started": True,
        "strategies": needs_scan,
        "universe": universe,
    }
