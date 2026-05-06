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

# ── Full NSE universe (~2137 stocks) ─────────────────────────────────────────
# For practical scanning we default to nifty500; use universe=full to scan all.
# Full list is fetched dynamically from NSE at scan time if needed.
# We seed FULL_UNIVERSE with SCAN_UNIVERSE; the _run_scan logic can extend this
# further from a live NSE equity list if available.
FULL_UNIVERSE: list[str] = list(SCAN_UNIVERSE)  # extended at runtime if desired


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

        elif strategy == "breakout":
            # 52-week high breakout with volume confirmation
            high_52w = float(closes.iloc[-252:].max()) if len(closes) >= 252 else float(closes.max())
            near_high = (high_52w - ltp) / high_52w * 100 < 3.0  # within 3% of 52w high
            vol_surge = float(vols.iloc[-1]) > float(vols.iloc[-20:].mean()) * 1.8
            conds = {
                "Near 52W High (<3%)": near_high,
                "Volume Surge (1.8x avg)": vol_surge,
                "EMA Uptrend (20>50)": ema_20 > ema_50,
                "Price > 20 EMA": ltp > ema_20,
                "RSI 50-75": 50 <= rsi_val <= 75,
                "HHHL (20d)": _hhhl(highs, lows, 20),
            }
            sl_pct = min((ltp - float(lows.iloc[-10:].min())) / ltp * 100, 8.0)

        elif strategy == "rsi_reversal":
            # RSI oversold recovery with volume surge
            rsi_prev = _rsi(closes.iloc[:-3])  # RSI 3 bars ago
            vol_surge = float(vols.iloc[-3:].mean()) > float(vols.iloc[-20:].mean()) * 1.5
            conds = {
                "RSI Recovered (30→50)": rsi_val >= 35 and rsi_prev < 35,
                "Price > 20 EMA": ltp > ema_20,
                "Volume Surge (1.5x)": vol_surge,
                "EMA Uptrend (10>20)": ema_10 > ema_20,
                "HHHL (20d)": _hhhl(highs, lows, 20),
                "No CHOC (5d)": not _choc(highs, lows, 5),
            }
            sl_pct = min(abs(ltp - float(lows.iloc[-5:].min())) / ltp * 100, 6.0)

        elif strategy == "golden_cross":
            # Golden cross: EMA20>EMA50>SMA200 full stack
            sma_200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else 0
            ema_20_prev = float(_ema_series(closes.iloc[:-5], 20).iloc[-1]) if len(closes) > 25 else ema_20
            ema_50_prev = float(_ema_series(closes.iloc[:-5], 50).iloc[-1]) if len(closes) > 55 else ema_50
            fresh_cross = ema_20 > ema_50 and ema_20_prev <= ema_50_prev
            conds = {
                "EMA20 > EMA50 (Golden Cross)": ema_20 > ema_50,
                "Fresh Cross (<5d)": fresh_cross,
                "Price > SMA 200": ltp > sma_200 if sma_200 > 0 else ltp > ema_50,
                "Volume Surge on Cross": float(vols.iloc[-5:].mean()) > float(vols.iloc[-20:].mean()) * 1.2,
                "RSI 45-70": 45 <= rsi_val <= 70,
                "Price > EMA20": ltp > ema_20,
            }
            sl_pct = min((ltp - float(lows.iloc[-15:].min())) / ltp * 100, 8.0)

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


def _run_scan(strategy: str, universe_name: str = "nifty500") -> list[dict]:
    """Download historical data and run screener scan."""
    try:
        # Download in batches of 30 to avoid rate limits
        batch_size = 30
        all_results: list[dict] = []
        universe = FULL_UNIVERSE if universe_name == "full" else SCAN_UNIVERSE

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


def _get_or_scan(strategy: str, universe_name: str = "nifty500") -> list[dict]:
    cache_key = f"{strategy}_{universe_name}"
    now = time.monotonic()
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return data

    if cache_key in _scan_running:
        # Return stale cache or empty while running
        return _cache.get(cache_key, (0, []))[1]

    _scan_running.add(cache_key)
    try:
        results = _run_scan(strategy, universe_name)
        _cache[cache_key] = (now, results)
        return results
    finally:
        _scan_running.discard(cache_key)


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/results")
async def get_screener_results(
    strategy: str = Query("vcp", pattern="^(vcp|ipo_base|rocket_base|breakout|rsi_reversal|golden_cross)$"),
    min_confidence: int = Query(0, ge=0, le=100),
    min_price: float = Query(0.0, ge=0),
    max_price: float = Query(0.0, ge=0),
    symbol: str = Query("", description="Filter by symbol substring"),
    universe: str = Query("nifty500", pattern="^(nifty500|full)$"),
):
    """Return cached screener results. Auto-triggers a scan if cache is cold."""
    loop = asyncio.get_event_loop()
    cache_key = f"{strategy}_{universe}"
    results = await loop.run_in_executor(_executor, _get_or_scan, strategy, universe)

    # Apply filters
    filtered = [
        r for r in results
        if r["confidence"] >= min_confidence
        and (not symbol or symbol.upper() in r["symbol"].upper())
        and (min_price == 0 or r["ltp"] >= min_price)
        and (max_price == 0 or r["ltp"] <= max_price)
    ]

    is_scanning = cache_key in _scan_running
    last_scan = None
    if cache_key in _cache:
        ts = _cache[cache_key][0]
        last_scan = datetime.fromtimestamp(
            time.time() - (time.monotonic() - ts)
        ).strftime("%H:%M:%S")

    active_universe = FULL_UNIVERSE if universe == "full" else SCAN_UNIVERSE
    return {
        "results": filtered,
        "total": len(filtered),
        "strategy": strategy,
        "universe": universe,
        "is_scanning": is_scanning,
        "last_scan": last_scan,
        "universe_size": len(active_universe),
    }


@router.post("/scan")
async def trigger_scan(
    strategy: str = Query("vcp", pattern="^(vcp|ipo_base|rocket_base|breakout|rsi_reversal|golden_cross)$"),
    universe: str = Query("nifty500", pattern="^(nifty500|full)$"),
    background_tasks: BackgroundTasks = None,
):
    """Force a fresh scan in the background."""
    cache_key = f"{strategy}_{universe}"
    if cache_key in _cache:
        del _cache[cache_key]

    loop = asyncio.get_event_loop()

    def _bg():
        _scan_running.add(cache_key)
        try:
            results = _run_scan(strategy, universe)
            _cache[cache_key] = (time.monotonic(), results)
        finally:
            _scan_running.discard(cache_key)

    loop.run_in_executor(_executor, _bg)
    active_universe = FULL_UNIVERSE if universe == "full" else SCAN_UNIVERSE
    return {"message": f"Scan triggered for {strategy}", "universe": universe, "universe_size": len(active_universe)}


@router.get("/status")
async def screener_status():
    """Check which strategies have cached results and which are running."""
    out = {}
    now = time.monotonic()
    all_strategies = ["vcp", "ipo_base", "rocket_base", "breakout", "rsi_reversal", "golden_cross"]
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
