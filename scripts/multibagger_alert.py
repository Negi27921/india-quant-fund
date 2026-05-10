"""
Thrice-daily multibagger screener + alert agent.

Schedule (GitHub Actions):
  10:30 AM IST  →  05:00 UTC  Mon–Fri
   2:00 PM IST  →  08:30 UTC  Mon–Fri
  10:00 PM IST  →  16:30 UTC  Mon–Fri

Steps:
  1. BSE credit rating upgrades (last 6 months) via BSE API
  2. Multibagger technical scan — all 2137 NSE stocks
  3. Cross-reference both results; highlight overlap
  4. Send Resend email + Telegram notification
  5. Store results in Supabase for dashboard cache
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = ZoneInfo("Asia/Kolkata")

# ── Config ────────────────────────────────────────────────────────────────────
RESEND_API_KEY   = os.getenv("RESEND_API_KEY", "")
REPORT_EMAIL     = os.getenv("REPORT_EMAIL", "negi2950@gmail.com")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY     = os.getenv("SUPABASE_KEY", "")

MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "95"))
MIN_PRICE      = float(os.getenv("MIN_PRICE", "50"))
MAX_RESULTS    = int(os.getenv("MAX_RESULTS", "30"))
RATING_DAYS    = int(os.getenv("RATING_DAYS", "180"))


# ── Universe — full 2137 NSE stocks ──────────────────────────────────────────
def _load_universe() -> list[str]:
    try:
        from api.full_universe import FULL_NSE_TICKERS
        print(f"  Loaded full universe: {len(FULL_NSE_TICKERS)} stocks")
        return FULL_NSE_TICKERS
    except ImportError:
        pass
    # Fallback: Nifty 500
    return [
        "360ONE.NS","3MINDIA.NS","ABB.NS","ACC.NS","ACMESOLAR.NS","AIAENG.NS","APLAPOLLO.NS","AUBANK.NS",
        "AWL.NS","AADHARHFC.NS","AARTIIND.NS","AAVAS.NS","ABBOTINDIA.NS","ACE.NS","ADANIENSOL.NS",
        "ADANIENT.NS","ADANIGREEN.NS","ADANIPORTS.NS","ADANIPOWER.NS","ATGL.NS","ABCAPITAL.NS","ABFRL.NS",
        "ABREL.NS","ABSLAMC.NS","AEGISLOG.NS","AFFLE.NS","AJANTPHARM.NS","ALKEM.NS","AMBER.NS",
        "AMBUJACEM.NS","ANANDRATHI.NS","ANANTRAJ.NS","ANGELONE.NS","APARINDS.NS","APOLLOHOSP.NS",
        "APOLLOTYRE.NS","APTUS.NS","ASHOKLEY.NS","ASIANPAINT.NS","ASTERDM.NS","ASTRAL.NS","ATUL.NS",
        "AUROPHARMA.NS","DMART.NS","AXISBANK.NS","BEML.NS","BLS.NS","BSE.NS","BAJAJ-AUTO.NS",
        "BAJFINANCE.NS","BAJAJFINSV.NS","BAJAJHLDNG.NS","BALKRISIND.NS","BALRAMCHIN.NS","BANDHANBNK.NS",
        "BANKBARODA.NS","BANKINDIA.NS","MAHABANK.NS","BATAINDIA.NS","BERGEPAINT.NS","BDL.NS","BEL.NS",
        "BHARATFORG.NS","BHEL.NS","BPCL.NS","BHARTIARTL.NS","BHARTIHEXA.NS","BIKAJI.NS","BIOCON.NS",
        "BSOFT.NS","BLUEDART.NS","BLUEJET.NS","BLUESTARCO.NS","BOSCHLTD.NS","BRIGADE.NS","BRITANNIA.NS",
        "CESC.NS","CGPOWER.NS","CRISIL.NS","CANFINHOME.NS","CANBK.NS","CAPLIPOINT.NS","CGCL.NS",
        "CARBORUNIV.NS","CASTROLIND.NS","CEATLTD.NS","CENTRALBK.NS","CDSL.NS","CHAMBLFERT.NS",
        "CHOLAFIN.NS","CIPLA.NS","CLEAN.NS","COALINDIA.NS","COCHINSHIP.NS","COFORGE.NS","COLPAL.NS",
        "CAMS.NS","CONCOR.NS","COROMANDEL.NS","CRAFTSMAN.NS","CROMPTON.NS","CUMMINSIND.NS","CYIENT.NS",
        "DLF.NS","DOMS.NS","DABUR.NS","DALBHARAT.NS","DATAPATTNS.NS","DEEPAKFERT.NS","DEEPAKNTR.NS",
        "DELHIVERY.NS","DIVISLAB.NS","DIXON.NS","LALPATHLAB.NS","DRREDDY.NS","EIHOTEL.NS","EICHERMOT.NS",
        "ELECON.NS","ELGIEQUIP.NS","EMAMILTD.NS","EMCURE.NS","ENDURANCE.NS","ENGINERSIN.NS","ERIS.NS",
        "ESCORTS.NS","ETERNAL.NS","EXIDEIND.NS","NYKAA.NS","FEDERALBNK.NS","FINCABLES.NS","FIVESTAR.NS",
        "FORCEMOT.NS","FORTIS.NS","GAIL.NS","GMRAIRPORT.NS","GRSE.NS","GICRE.NS","GLAND.NS","GLAXO.NS",
        "GLENMARK.NS","MEDANTA.NS","GPIL.NS","GODREJCP.NS","GODREJIND.NS","GODREJPROP.NS","GRANULES.NS",
        "GRAPHITE.NS","GRASIM.NS","GRAVITA.NS","GESHIP.NS","FLUOROCHEM.NS","HEG.NS","HBLENGINE.NS",
        "HCLTECH.NS","HDFCAMC.NS","HDFCBANK.NS","HDFCLIFE.NS","HFCL.NS","HAVELLS.NS","HEROMOTOCO.NS",
        "HINDALCO.NS","HAL.NS","HINDCOPPER.NS","HINDPETRO.NS","HINDUNILVR.NS","HINDZINC.NS","POWERINDIA.NS",
        "HOMEFIRST.NS","HONAUT.NS","HUDCO.NS","HYUNDAI.NS","ICICIBANK.NS","ICICIGI.NS","ICICIAMC.NS",
        "ICICIPRULI.NS","IDBI.NS","IDFCFIRSTB.NS","IIFL.NS","IRB.NS","IRCON.NS","ITC.NS","ITI.NS",
        "INDIAMART.NS","INDIANB.NS","IEX.NS","INDHOTEL.NS","IOC.NS","IOB.NS","IRCTC.NS","IRFC.NS",
        "IREDA.NS","IGL.NS","INDUSTOWER.NS","INDUSINDBK.NS","NAUKRI.NS","INFY.NS","INOXWIND.NS",
        "INTELLECT.NS","INDIGO.NS","IPCALAB.NS","JBCHEPHARM.NS","JKCEMENT.NS","JBMA.NS","JKTYRE.NS",
        "JSWCEMENT.NS","JSWENERGY.NS","JSWINFRA.NS","JSWSTEEL.NS","JAINREC.NS","JPPOWER.NS",
        "JINDALSAW.NS","JSL.NS","JINDALSTEL.NS","JIOFIN.NS","JUBLFOOD.NS","JUBLINGREA.NS","JUBLPHARMA.NS",
        "KPRMILL.NS","KEI.NS","KPITTECH.NS","KAJARIACER.NS","KPIL.NS","KALYANKJIL.NS","KARURVYSYA.NS",
        "KAYNES.NS","KEC.NS","KFINTECH.NS","KIRLOSENG.NS","KOTAKBANK.NS","KIMS.NS","LTF.NS","LTTS.NS",
        "LGEINDIA.NS","LICHSGFIN.NS","LTFOODS.NS","LT.NS","LATENTVIEW.NS","LAURUSLABS.NS","THELEELA.NS",
        "LEMONTREE.NS","LICI.NS","LINDEINDIA.NS","LLOYDSME.NS","LODHA.NS","LUPIN.NS","MRF.NS","MGL.NS",
        "M&MFIN.NS","M&M.NS","MANAPPURAM.NS","MRPL.NS","MANKIND.NS","MARICO.NS","MARUTI.NS","MFSL.NS",
        "MAXHEALTH.NS","MAZDOCK.NS","MINDACORP.NS","MSUMI.NS","MOTILALOFS.NS","MPHASIS.NS","MCX.NS",
        "MUTHOOTFIN.NS","NATCOPHARM.NS","NBCC.NS","NCC.NS","NHPC.NS","NLCINDIA.NS","NMDC.NS","NTPC.NS",
        "NH.NS","NATIONALUM.NS","NAVINFLUOR.NS","NESTLEIND.NS","NETWEB.NS","NEULANDLAB.NS","NEWGEN.NS",
        "NAM-INDIA.NS","NUVAMA.NS","NUVOCO.NS","OBEROIRLTY.NS","ONGC.NS","OIL.NS","OLECTRA.NS",
        "OFSS.NS","POLICYBZR.NS","PCBL.NS","PGEL.NS","PIIND.NS","PNBHOUSING.NS","PVRINOX.NS","PAGEIND.NS",
        "PARADEEP.NS","PATANJALI.NS","PERSISTENT.NS","PETRONET.NS","PFIZER.NS","PHOENIXLTD.NS",
        "PIDILITIND.NS","PIRAMALFIN.NS","POLYMED.NS","POLYCAB.NS","POONAWALLA.NS","PFC.NS","POWERGRID.NS",
        "PRESTIGE.NS","PNB.NS","RRKABEL.NS","RBLBANK.NS","RECLTD.NS","RHIM.NS","RITES.NS","RADICO.NS",
        "RVNL.NS","RAILTEL.NS","RAINBOW.NS","RKFORGE.NS","REDINGTON.NS","RELIANCE.NS","RPOWER.NS",
        "SBFC.NS","SBICARD.NS","SBILIFE.NS","SJVN.NS","SRF.NS","MOTHERSON.NS","SAPPHIRE.NS","SARDAEN.NS",
        "SAREGAMA.NS","SCHAEFFLER.NS","SHREECEM.NS","SHRIRAMFIN.NS","SHYAMMETL.NS","SIEMENS.NS",
        "SOBHA.NS","SOLARINDS.NS","SONACOMS.NS","SONATSOFTW.NS","STARHEALTH.NS","SBIN.NS","SAIL.NS",
        "SUMICHEM.NS","SUNPHARMA.NS","SUNTV.NS","SUNDARMFIN.NS","SUPREMEIND.NS","SUZLON.NS","SWIGGY.NS",
        "SYNGENE.NS","SYRMA.NS","TBOTEK.NS","TVSMOTOR.NS","TATACAP.NS","TATACHEM.NS","TATACOMM.NS",
        "TCS.NS","TATACONSUM.NS","TATAELXSI.NS","TATAINVEST.NS","TATAPOWER.NS","TATASTEEL.NS","TATATECH.NS",
        "TECHM.NS","TECHNOE.NS","TEGA.NS","TEJASNET.NS","NIACL.NS","RAMCOCEM.NS","THERMAX.NS",
        "TIMKEN.NS","TITAGARH.NS","TITAN.NS","TORNTPHARM.NS","TORNTPOWER.NS","TARIL.NS","TRENT.NS",
        "TRIDENT.NS","TRITURBINE.NS","TIINDIA.NS","UCOBANK.NS","UNOMINDA.NS","UPL.NS","UTIAMC.NS",
        "ULTRACEMCO.NS","UNIONBANK.NS","UBL.NS","UNITDSPR.NS","USHAMART.NS","VTL.NS","VBL.NS","VEDL.NS",
        "VOLTAS.NS","WAAREEENER.NS","WELCORP.NS","WELSPUNLIV.NS","WIPRO.NS","WOCKPHARMA.NS","YESBANK.NS",
        "ZFCVINDIA.NS","ZEEL.NS","ZENSARTECH.NS","ZYDUSLIFE.NS","ZYDUSWELL.NS","ECLERX.NS",
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sf(v, d=0.0):
    try:
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return d


def _ema(s: pd.Series, p: int) -> float:
    if len(s) < 2:
        return _sf(s.iloc[-1]) if len(s) else 0.0
    return _sf(s.ewm(span=p, adjust=False).mean().iloc[-1])


def _rsi(closes: pd.Series, p: int = 14) -> float:
    if len(closes) < p + 1:
        return 50.0
    d = closes.diff()
    gain = d.clip(lower=0).rolling(p).mean()
    loss = (-d.clip(upper=0)).rolling(p).mean()
    rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-9)
    return _sf(100 - 100 / (1 + rs), 50.0)


# ── Step 1: BSE Credit Rating Upgrades ────────────────────────────────────────

def fetch_bse_credit_upgrades(days_back: int = 180) -> list[dict]:
    today     = date.today()
    from_date = today - timedelta(days=days_back)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://www.bseindia.com/",
        "Origin":  "https://www.bseindia.com",
        "Accept":  "application/json",
    }
    upgrade_kws = ["upgrade", "upgraded", "positive outlook", "aa+", "aaa", "a1+", "upgraded to", "reaffirmed"]
    results = []

    for cat, subcat in [("-1", "Credit+Rating"), ("40", "")]:
        url = (
            "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
            f"?strPrevDate={from_date.strftime('%Y%m%d')}"
            f"&strToDate={today.strftime('%Y%m%d')}"
            f"&strCat={cat}&strType=C&strScrip=&strSearch=Y"
            + (f"&subcategory={subcat}" if subcat else "")
        )
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            rows = data if isinstance(data, list) else data.get("Table", data.get("table", []))
            for row in rows:
                headline = (row.get("HEADLINE") or row.get("headline") or "").lower()
                if any(kw in headline for kw in upgrade_kws):
                    results.append({
                        "company":  row.get("SLONGNAME") or row.get("scrip_cd") or "",
                        "headline": row.get("HEADLINE") or "",
                        "date":     row.get("DT_TM") or row.get("NEWS_DT") or "",
                        "scrip":    str(row.get("SCRIP_CD") or ""),
                    })
            if results:
                break  # Got results from first endpoint — done
        except Exception as e:
            print(f"  BSE endpoint {cat} failed: {e}")

    # Deduplicate by company+date
    seen = set()
    deduped = []
    for r in results:
        key = (r["company"][:20], str(r["date"])[:10])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    print(f"  BSE: {len(deduped)} credit rating events found")
    return deduped


# ── Step 2: Multibagger Technical Screen ──────────────────────────────────────

def _screen_batch(tickers: list[str]) -> list[dict]:
    results = []
    try:
        raw = yf.download(
            tickers, period="260d", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False, threads=True,
        )
    except Exception:
        return results

    for ticker in tickers:
        try:
            df = raw[ticker] if len(tickers) > 1 else raw
            df = df.dropna(subset=["Close"])
            if len(df) < 50:
                continue

            closes  = df["Close"]
            volumes = df["Volume"]
            ltp     = _sf(closes.iloc[-1])
            if ltp < MIN_PRICE:
                continue

            ema9   = _ema(closes, 9)
            ema20  = _ema(closes, 20)
            ema50  = _ema(closes, 50)
            sma200 = _sf(closes.tail(200).mean()) if len(closes) >= 200 else 0.0
            rsi    = _rsi(closes)

            low_90d   = _sf(closes.tail(90).min())
            high_52w  = _sf(closes.tail(252).max() if len(closes) >= 252 else closes.max())
            low_52w   = _sf(closes.tail(252).min() if len(closes) >= 252 else closes.min())
            sma200_30 = _sf(closes.iloc[-230]) if len(closes) >= 230 else sma200
            sma200_sl = ((sma200 - sma200_30) / (sma200_30 + 1e-9)) * 100 if sma200_30 else 0.0

            avg_vol_3  = _sf(volumes.tail(3).mean())
            avg_vol_5  = _sf(volumes.tail(5).mean())
            avg_vol_20 = _sf(volumes.tail(20).mean())

            rng_52w   = high_52w - low_52w
            rng_20d   = _sf(closes.tail(20).max() - closes.tail(20).min())
            base_pct  = (rng_20d / rng_52w * 100) if rng_52w > 0 else 100.0
            from_52h  = (high_52w - ltp) / high_52w * 100 if high_52w > 0 else 100.0
            from_90l  = (ltp - low_90d) / low_90d * 100 if low_90d > 0 else 0.0
            from_e50  = (ltp - ema50) / ltp * 100 if ltp > 0 else 0.0

            conds = {
                "EMA Stack (9>20>50)":       ema9 > ema20 > ema50 and ema50 > 0,
                "Price > SMA200":            ltp > sma200 and sma200 > 0,
                "SMA200 Slope ↑ (>0.3%)":   sma200_sl > 0.3,
                "RSI 55–78":                 55 <= rsi <= 78,
                "Recovered ≥15% from 90dL":  from_90l >= 15.0,
                "Within 40% of 52W High":    from_52h <= 40.0,
                "Base Forming <30%":         base_pct < 30.0,
                "Inst Accum (5d>20d vol)":   avg_vol_20 > 0 and avg_vol_5 > avg_vol_20 * 1.1,
                "Vol Re-entry (3d≥1.5×20d)": avg_vol_20 > 0 and avg_vol_3 >= avg_vol_20 * 1.5,
                "Not Extended (<20%EMA50)":  abs(from_e50) <= 20.0,
                "Liquidity (>75k vol)":      avg_vol_20 >= 75_000,
            }

            passed = [k for k, v in conds.items() if v]
            failed = [k for k, v in conds.items() if not v]
            conf   = round(len(passed) / len(conds) * 100)

            if conf < MIN_CONFIDENCE:
                continue

            sl_pct = min(max(abs(from_e50) if from_e50 > 0 else 8.0, 3.0), 15.0)
            sl  = round(ltp * (1 - sl_pct / 100), 2)
            tp1 = round(ltp * 1.15, 2)
            tp2 = round(ltp * 1.30, 2)

            results.append({
                "ticker":   ticker.replace(".NS", ""),
                "ltp":      round(ltp, 2),
                "rsi":      round(rsi, 1),
                "ema9":     round(ema9, 2),
                "ema20":    round(ema20, 2),
                "ema50":    round(ema50, 2),
                "sma200":   round(sma200, 2),
                "sma200_slope": round(sma200_sl, 2),
                "base_pct": round(base_pct, 1),
                "from_52h": round(from_52h, 1),
                "from_90l": round(from_90l, 1),
                "confidence": conf,
                "passed":   passed,
                "failed":   failed,
                "sl":       sl,
                "sl_pct":   round(sl_pct, 1),
                "tp1":      tp1,
                "tp2":      tp2,
            })
        except Exception:
            pass

    return results


def run_technical_screen(universe: list[str]) -> list[dict]:
    print(f"  Screening {len(universe)} stocks (min confidence ≥ {MIN_CONFIDENCE}%)...")
    batch_size = 50
    batches    = [universe[i:i+batch_size] for i in range(0, len(universe), batch_size)]
    all_results: list[dict] = []

    with ThreadPoolExecutor(max_workers=min(20, len(batches))) as pool:
        futures = {pool.submit(_screen_batch, b): b for b in batches}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                res = future.result(timeout=120)
                all_results.extend(res)
                if res:
                    print(f"  [{done}/{len(batches)}] +{len(res)} hits | total {len(all_results)}")
            except Exception as e:
                print(f"  Batch {done} error: {e}")

    return sorted(all_results, key=lambda x: -x["confidence"])[:MAX_RESULTS]


# ── Step 3: Supabase cache ────────────────────────────────────────────────────

def _supabase_store(results: list[dict], rating_events: list[dict]) -> None:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        from datetime import datetime
        now_ist = datetime.now(IST).isoformat()
        sb.table("screener_cache").upsert({
            "strategy":    "multibagger",
            "universe":    "full",
            "scanned_at":  now_ist,
            "results":     json.dumps(results),
            "meta":        json.dumps({"rating_events": rating_events[:20]}),
            "is_scanning": False,
        }, on_conflict="strategy,universe").execute()
        print("  Stored results in Supabase screener_cache")
    except Exception as e:
        print(f"  Supabase store failed: {e}")


# ── Step 4: Telegram ──────────────────────────────────────────────────────────

def send_telegram(results: list[dict], credit_matches: set[str], run_time: str) -> None:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("  Telegram not configured — skipping")
        return

    hour = int(run_time[:2])
    session = "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"
    today   = date.today().strftime("%-d %b %Y")

    # Header
    lines = [
        f"🏴‍☠️ *ONE PIECE QUANT · Multibagger · {session}*",
        f"_{today}  {run_time} IST · {len(results)} hits / {_UNIVERSE_SIZE:,} stocks_",
        "",
    ]

    if results:
        # Monospace-aligned table in a code block
        rows = []
        for r in results[:15]:
            tag    = "★" if r["ticker"] in credit_matches else " "
            ticker = r["ticker"][:10].ljust(10)
            ltp    = f"{r['ltp']:,.0f}".rjust(7)
            conf   = f"{r['confidence']}%".rjust(4)
            rsi    = f"{r['rsi']}".rjust(3)
            sl_pct = f"{r['sl_pct']}%".rjust(4)
            rows.append(f"{tag}{ticker}{ltp}  {conf}  {rsi}  {sl_pct}")

        header = " TICKER       LTP    CF  RSI   SL"
        sep    = "─" * len(header)
        table  = "\n".join([header, sep] + rows)
        lines += [f"```\n{table}\n```", ""]

        if len(results) > 15:
            lines.append(f"_+{len(results)-15} more in email_\n")

    else:
        lines.append("_No candidates above the confidence threshold today._\n")

    if credit_matches:
        lines.append(f"★ *Credit upgrade overlap:* {', '.join(sorted(credit_matches))}\n")

    lines += [
        "[📊 Dashboard](https://luffy-labs.vercel.app)  ·  _Not financial advice_",
    ]

    msg  = "\n".join(lines)
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "curl/8.4.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            print(f"  Telegram: sent OK")
        else:
            print(f"  Telegram error: {result}")
            _send_failure_alert_email(f"Telegram sendMessage error: {result.get('description', str(result))}")
    except Exception as e:
        print(f"  Telegram failed: {e}")
        _send_failure_alert_email(f"Telegram exception: {e}")


# ── Step 5: Email ─────────────────────────────────────────────────────────────

def build_email(results: list[dict], rating_events: list[dict], credit_matches: set[str], run_time: str) -> str:
    hour    = int(run_time[:2])
    session = "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"
    today   = date.today().strftime("%-d %b %Y")

    # ── Candidates table rows ─────────────────────────────────────────────────
    def _conf_badge(c: int) -> str:
        col = "#00ff41" if c >= 97 else "#7dff7d" if c >= 95 else "#f59e0b"
        return f'<span style="color:{col};font-weight:700">{c}%</span>'

    def _signals(passed: list) -> str:
        short = {
            "EMA Stack (9>20>50)":       "EMA stack",
            "Price > SMA200":            "Above SMA200",
            "SMA200 Slope ↑ (>0.3%)":   "SMA200↑",
            "RSI 55–78":                 "RSI zone",
            "Recovered ≥15% from 90dL":  "Recovered",
            "Within 40% of 52W High":    "Near 52Wh",
            "Base Forming <30%":         "Base",
            "Inst Accum (5d>20d vol)":   "Accum",
            "Vol Re-entry (3d≥1.5×20d)":"Vol surge",
            "Not Extended (<20%EMA50)":  "Not ext.",
            "Liquidity (>75k vol)":      "Liquid",
        }
        return " · ".join(short.get(p, p) for p in passed[:4])

    rows_html = ""
    for r in results:
        is_star  = r["ticker"] in credit_matches
        star_td  = '<td style="padding:8px 6px;color:#f59e0b;font-size:14px">★</td>' if is_star else '<td style="padding:8px 6px"></td>'
        t_color  = "#f59e0b" if is_star else "#00ff41"
        rows_html += f"""
        <tr style="border-bottom:1px solid #ffffff08">
          {star_td}
          <td style="padding:8px 6px;font-weight:700;color:{t_color};letter-spacing:.04em">{r['ticker']}</td>
          <td style="padding:8px 6px;color:#e8ffe8">₹{r['ltp']:,.0f}</td>
          <td style="padding:8px 6px">{_conf_badge(r['confidence'])}</td>
          <td style="padding:8px 6px;color:#aaa">{r['rsi']}</td>
          <td style="padding:8px 6px;color:#ff6b6b">₹{r['sl']:,.0f}<span style="color:#555;font-size:10px"> -{r['sl_pct']}%</span></td>
          <td style="padding:8px 6px;color:#00cc88">₹{r['tp1']:,.0f} <span style="color:#555">·</span> ₹{r['tp2']:,.0f}</td>
          <td style="padding:8px 6px;font-size:10px;color:#556655">{_signals(r.get('passed', []))}</td>
        </tr>"""

    empty_row = f"<tr><td colspan='8' style='padding:20px;color:#334433;text-align:center'>No candidates above {MIN_CONFIDENCE}% confidence today</td></tr>"

    # ── BSE credit upgrades ───────────────────────────────────────────────────
    rating_rows = ""
    for evt in (rating_events[:12] if rating_events else []):
        rating_rows += f"""
        <tr style="border-bottom:1px solid #ffffff06">
          <td style="padding:6px;color:#f59e0b;font-weight:600">{str(evt.get('company',''))[:30]}</td>
          <td style="padding:6px;color:#aaa;font-size:11px">{str(evt.get('headline',''))[:70]}</td>
          <td style="padding:6px;color:#556655;font-size:11px">{str(evt.get('date',''))[:10]}</td>
        </tr>"""
    if not rating_rows:
        rating_rows = "<tr><td colspan='3' style='padding:12px;color:#334433'>No BSE credit upgrades found today</td></tr>"

    # ── Credit overlap callout ────────────────────────────────────────────────
    overlap_html = ""
    if credit_matches:
        tickers_html = " ".join(
            f'<span style="display:inline-block;background:#f59e0b18;border:1px solid #f59e0b40;color:#f59e0b;'
            f'padding:2px 8px;border-radius:3px;margin:2px;font-size:11px">{t}</span>'
            for t in sorted(credit_matches)
        )
        overlap_html = f"""
        <div style="margin:16px 0;padding:12px 16px;background:#1a1200;border-left:3px solid #f59e0b">
          <span style="color:#f59e0b;font-size:11px;font-weight:700;letter-spacing:.1em">HIGHEST CONVICTION — CREDIT UPGRADE OVERLAP</span><br>
          <div style="margin-top:6px">{tickers_html}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#060d06;font-family:'SF Mono',Monaco,monospace;color:#c8e8c8">
<div style="max-width:780px;margin:0 auto;padding:24px 16px">

  <!-- Header -->
  <div style="border-bottom:1px solid #00ff4120;padding-bottom:16px;margin-bottom:20px">
    <div style="color:#00ff41;font-size:13px;font-weight:700;letter-spacing:.2em">ONE PIECE QUANT TERMINAL</div>
    <div style="margin-top:4px;font-size:22px;font-weight:700;color:#e8ffe8">Multibagger Alert</div>
    <div style="margin-top:4px;color:#556655;font-size:12px">{session} · {today} · {run_time} IST</div>
  </div>

  <!-- Stats bar -->
  <div style="display:flex;gap:24px;margin-bottom:20px;flex-wrap:wrap">
    <div><div style="color:#00ff41;font-size:28px;font-weight:700;line-height:1">{len(results)}</div>
         <div style="color:#556655;font-size:11px;margin-top:2px">CANDIDATES</div></div>
    <div><div style="color:#e8ffe8;font-size:28px;font-weight:700;line-height:1">{_UNIVERSE_SIZE:,}</div>
         <div style="color:#556655;font-size:11px;margin-top:2px">STOCKS SCANNED</div></div>
    <div><div style="color:#e8ffe8;font-size:28px;font-weight:700;line-height:1">{MIN_CONFIDENCE}%</div>
         <div style="color:#556655;font-size:11px;margin-top:2px">MIN CONFIDENCE</div></div>
    {f'<div><div style="color:#f59e0b;font-size:28px;font-weight:700;line-height:1">{len(credit_matches)}</div><div style="color:#556655;font-size:11px;margin-top:2px">CREDIT UPGRADES</div></div>' if credit_matches else ""}
  </div>

  {overlap_html}

  <!-- Candidates table -->
  <div style="color:#00ff41;font-size:10px;font-weight:700;letter-spacing:.18em;margin-bottom:8px">MULTIBAGGER CANDIDATES</div>
  <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead>
      <tr style="border-bottom:1px solid #00ff4120;color:#445544;font-size:10px;letter-spacing:.08em">
        <th style="padding:6px;width:16px"></th>
        <th style="text-align:left;padding:6px">TICKER</th>
        <th style="text-align:left;padding:6px">PRICE</th>
        <th style="text-align:left;padding:6px">CONF</th>
        <th style="text-align:left;padding:6px">RSI</th>
        <th style="text-align:left;padding:6px">STOP LOSS</th>
        <th style="text-align:left;padding:6px">TP1 · TP2</th>
        <th style="text-align:left;padding:6px">SIGNALS</th>
      </tr>
    </thead>
    <tbody>
      {rows_html if rows_html else empty_row}
    </tbody>
  </table>
  {'<p style="font-size:10px;color:#334433;margin-top:6px">★ BSE credit rating upgrade in last 6 months</p>' if credit_matches else ""}

  <!-- BSE Credit Upgrades -->
  <div style="color:#00ff41;font-size:10px;font-weight:700;letter-spacing:.18em;margin:28px 0 8px">BSE CREDIT RATING UPGRADES · LAST 6M</div>
  <table style="width:100%;border-collapse:collapse;font-size:11px">
    <thead>
      <tr style="border-bottom:1px solid #00ff4115;color:#445544;font-size:10px;letter-spacing:.08em">
        <th style="text-align:left;padding:6px">COMPANY</th>
        <th style="text-align:left;padding:6px">HEADLINE</th>
        <th style="text-align:left;padding:6px">DATE</th>
      </tr>
    </thead>
    <tbody>{rating_rows}</tbody>
  </table>

  <!-- Footer -->
  <div style="margin-top:28px;padding-top:14px;border-top:1px solid #ffffff08;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
    <a href="https://luffy-labs.vercel.app" style="color:#00ff41;text-decoration:none;font-size:11px;font-weight:700">→ Open Dashboard</a>
    <span style="color:#334433;font-size:10px">Not financial advice · {today} · One Piece Quant Terminal</span>
  </div>

</div>
</body></html>"""


def _send_failure_alert_email(error_msg: str) -> None:
    """Send email alert when Telegram fails — silent fallback."""
    if not RESEND_API_KEY:
        return
    payload = json.dumps({
        "from":    "One Piece Quant <onboarding@resend.dev>",
        "to":      [REPORT_EMAIL],
        "subject": f"⚠️ OPQ Telegram Delivery Failed · {date.today()}",
        "html":    f"<p style='font-family:monospace'>Telegram notification failed: {error_msg}</p>",
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            print("  Failure alert email sent")
    except Exception:
        pass  # Both channels failed — log only


def _send_failure_alert_telegram(error_msg: str) -> None:
    """Send Telegram alert when email fails — silent fallback."""
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return
    msg  = f"⚠️ *OPQ Email Delivery Failed*\n`{error_msg[:200]}`"
    body = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
    req  = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


def send_email(html: str, subject: str) -> bool:
    if not RESEND_API_KEY:
        print("  RESEND_API_KEY not set — email skipped")
        return False
    try:
        payload = json.dumps({
            "from":    "One Piece Quant <onboarding@resend.dev>",
            "to":      [REPORT_EMAIL],
            "subject": subject,
            "html":    html,
        }).encode()
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization":  f"Bearer {RESEND_API_KEY}",
                "Content-Type":   "application/json",
                "User-Agent":     "curl/8.4.0",
                "Accept":         "*/*",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            res = json.loads(resp.read())
        print(f"  Email sent → {REPORT_EMAIL} (id={res.get('id')})")
        return True
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"  Email failed: {e.code} {body_text}")
        _send_failure_alert_telegram(f"HTTP {e.code}: {body_text[:150]}")
        return False
    except Exception as e:
        print(f"  Email failed: {e}")
        _send_failure_alert_telegram(str(e))
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

_UNIVERSE_SIZE = 0  # filled at runtime

def main():
    global _UNIVERSE_SIZE
    from datetime import datetime
    now = datetime.now(IST)
    run_time = now.strftime("%H:%M")

    print("=" * 60)
    print(f"  IQF Multibagger Alert Agent  —  {date.today()}  {run_time} IST")
    print("=" * 60)

    universe = _load_universe()
    _UNIVERSE_SIZE = len(universe)

    # 1. Credit rating check
    print("\n[1/5] BSE credit rating upgrades...")
    t0 = time.time()
    rating_events = fetch_bse_credit_upgrades(RATING_DAYS)
    print(f"      {time.time()-t0:.1f}s")

    # 2. Technical screen
    print("\n[2/5] Multibagger technical scan...")
    t1 = time.time()
    results = run_technical_screen(universe)
    print(f"      {time.time()-t1:.1f}s | {len(results)} candidates ≥{MIN_CONFIDENCE}%")

    # 3. Cross-reference
    print("\n[3/5] Cross-referencing...")
    upgraded_names = {r["company"].lower() for r in rating_events}
    credit_matches: set[str] = set()
    for r in results:
        base = r["ticker"].lower()
        for name in upgraded_names:
            if base[:5] in name or name[:5] in base:
                credit_matches.add(r["ticker"])
                break
    print(f"      {len(credit_matches)} stocks in both screens: {credit_matches or 'none'}")

    # 4. Supabase cache
    print("\n[4/5] Caching to Supabase...")
    _supabase_store(results, rating_events)

    # 5. Notifications
    print("\n[5/5] Sending notifications...")
    session_label = "Morning" if int(run_time[:2]) < 12 else ("Afternoon" if int(run_time[:2]) < 17 else "Evening")
    subject = (
        f"📈 IQF Multibagger Alert [{session_label}] — "
        f"{len(results)} candidates"
        + (f" | ⭐ {len(credit_matches)} credit-rated" if credit_matches else "")
        + f" · {date.today()}"
    )
    html = build_email(results, rating_events, credit_matches, run_time)
    send_email(html, subject)
    send_telegram(results, credit_matches, run_time)

    print("\n" + "=" * 60)
    print(f"  Done. {len(results)} candidates found.")
    print("=" * 60)


if __name__ == "__main__":
    main()
