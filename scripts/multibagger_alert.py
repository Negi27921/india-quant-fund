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

    session = "🌅 Morning" if int(run_time[:2]) < 12 else "☀️ Afternoon" if int(run_time[:2]) < 17 else "🌙 Evening"
    lines = [
        f"📈 *IQF Multibagger Alert* — {session}",
        f"📅 {date.today().strftime('%d %b %Y')} | {run_time} IST",
        f"🔍 {len(results)} candidates (≥{MIN_CONFIDENCE}% conf)",
        "",
    ]
    if credit_matches:
        lines.append(f"⭐ *Credit-rated overlap:* {', '.join(sorted(credit_matches))}")
        lines.append("")

    for r in results[:10]:
        star = "⭐" if r["ticker"] in credit_matches else "•"
        lines.append(
            f"{star} *{r['ticker']}* ₹{r['ltp']:,.0f} | Conf {r['confidence']}% | RSI {r['rsi']} | SL ₹{r['sl']:,.0f}"
        )

    if len(results) > 10:
        lines.append(f"\n_...and {len(results)-10} more. Check email for full list._")

    lines += [
        "",
        "🔗 Dashboard: https://dashboard-two-plum-91.vercel.app",
        "_Not financial advice._",
    ]

    msg  = "\n".join(lines)
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            print(f"  Telegram: sent OK")
        else:
            print(f"  Telegram error: {result}")
    except Exception as e:
        print(f"  Telegram failed: {e}")


# ── Step 5: Email ─────────────────────────────────────────────────────────────

def build_email(results: list[dict], rating_events: list[dict], credit_matches: set[str], run_time: str) -> str:
    session = "MORNING (10:30 AM IST)" if int(run_time[:2]) < 12 else (
        "AFTERNOON (2:00 PM IST)" if int(run_time[:2]) < 17 else "EVENING (10:00 PM IST)"
    )

    rows_html = ""
    for r in results:
        star     = "⭐ " if r["ticker"] in credit_matches else ""
        conf_col = "#00ff41" if r["confidence"] >= 95 else "#f59e0b"
        rows_html += f"""
        <tr style="border-bottom:1px solid #00ff4110">
          <td style="padding:6px 4px;font-weight:700;color:#00ff41">{star}{r['ticker']}</td>
          <td style="padding:6px 4px">₹{r['ltp']:,.2f}</td>
          <td style="padding:6px 4px;color:{conf_col};font-weight:700">{r['confidence']}%</td>
          <td style="padding:6px 4px">{r['rsi']}</td>
          <td style="padding:6px 4px;color:#ff6644">₹{r['sl']:,.2f} ({r['sl_pct']}%)</td>
          <td style="padding:6px 4px;color:#00cc44">₹{r['tp1']:,.2f} / ₹{r['tp2']:,.2f}</td>
          <td style="padding:6px 4px;font-size:10px;color:#888">{", ".join(r["passed"][:3])}</td>
        </tr>"""

    rating_html = ""
    for evt in (rating_events[:15] if rating_events else []):
        rating_html += f"""
        <tr style="border-bottom:1px solid #00ff4108">
          <td style="padding:4px;color:#f59e0b">{str(evt.get('company',''))[:35]}</td>
          <td style="padding:4px;font-size:11px">{str(evt.get('headline',''))[:65]}</td>
          <td style="padding:4px;font-size:11px;color:#888">{str(evt.get('date',''))[:10]}</td>
        </tr>"""
    if not rating_html:
        rating_html = "<tr><td colspan='3' style='padding:8px;color:#444'>No upgrades via BSE API today</td></tr>"

    return f"""<!DOCTYPE html><html><body style="font-family:monospace;background:#050e05;color:#e8ffe8;padding:24px">
<div style="max-width:760px;margin:0 auto">

<h1 style="color:#00ff41;letter-spacing:.1em;border-bottom:1px solid #00ff4130;padding-bottom:10px;font-size:18px">
  📈 ONE PIECE QUANT TERMINAL
  <span style="display:block;font-size:12px;color:#00aa28;margin-top:4px">
    Multibagger Alert — {session} · {date.today().strftime('%d %b %Y')} · {run_time} IST
  </span>
</h1>

<p style="color:#00aa28;font-size:13px">
  <strong style="color:#00ff41">{len(results)}</strong> stocks passed all multibagger criteria
  (confidence ≥{MIN_CONFIDENCE}% from {_UNIVERSE_SIZE:,} stock universe).
  {"<strong style='color:#f59e0b'>⭐ "+str(len(credit_matches))+" also have BSE credit upgrades — highest conviction.</strong>" if credit_matches else ""}
</p>

<h2 style="color:#00e535;font-size:12px;letter-spacing:.18em;margin-top:20px">MULTIBAGGER CANDIDATES</h2>
<table style="width:100%;border-collapse:collapse;font-size:12px">
  <thead>
    <tr style="color:#00aa28;border-bottom:1px solid #00ff4130">
      <th style="text-align:left;padding:6px 4px">Ticker</th>
      <th style="text-align:left;padding:6px 4px">LTP</th>
      <th style="text-align:left;padding:6px 4px">Conf</th>
      <th style="text-align:left;padding:6px 4px">RSI</th>
      <th style="text-align:left;padding:6px 4px">Stop Loss</th>
      <th style="text-align:left;padding:6px 4px">TP1 / TP2</th>
      <th style="text-align:left;padding:6px 4px">Top Signals</th>
    </tr>
  </thead>
  <tbody>{rows_html if rows_html else "<tr><td colspan='7' style='padding:12px;color:#555'>No candidates above {MIN_CONFIDENCE}% confidence today</td></tr>"}</tbody>
</table>
<p style="font-size:10px;color:#555;margin-top:4px">⭐ = BSE credit rating upgrade in last 6 months. Validate on Screener.in before acting.</p>

<h2 style="color:#00e535;font-size:12px;letter-spacing:.18em;margin-top:24px">BSE CREDIT RATING UPGRADES (LAST 6M)</h2>
<table style="width:100%;border-collapse:collapse;font-size:12px">
  <thead>
    <tr style="color:#00aa28;border-bottom:1px solid #00ff4130">
      <th style="text-align:left;padding:4px">Company</th>
      <th style="text-align:left;padding:4px">BSE Headline</th>
      <th style="text-align:left;padding:4px">Date</th>
    </tr>
  </thead>
  <tbody>{rating_html}</tbody>
</table>

<div style="margin-top:24px;padding:14px;background:#0a1a0a;border:1px solid #00ff4120;font-size:11px">
  <strong style="color:#f59e0b">Manual Validation Checklist (for ⭐ stocks):</strong>
  <ol style="color:#888;margin:8px 0;padding-left:20px;line-height:2">
    <li>Run Screener.in fundamental query (pasted below) — look for YOY sales growth &gt;20%</li>
    <li>Verify order book ≥ 2.5× TTM revenue in latest concall / investor presentation on BSE</li>
    <li>Confirm credit rating upgrade letter on bseindia.com → Announcements → Credit Rating</li>
    <li>Check promoter holding trend — should be stable or increasing</li>
  </ol>
</div>

<div style="margin-top:12px;padding:12px;background:#0a0a18;border:1px solid #f59e0b30;font-size:10px;color:#666">
  <strong style="color:#f59e0b">Screener.in Query (copy-paste at screener.in/screens/new):</strong><br><br>
  <code style="color:#aaa;line-height:1.9;white-space:pre-wrap">YOY Quarterly sales growth > 20 AND Sales growth > 20 AND OPM > 12 AND OPM last year &lt; OPM AND Debt to equity &lt; 0.5 AND Return on equity > 15 AND Market Capitalization > 500 AND Market Capitalization &lt; 30000 AND Cash from operations last year > 0 AND Promoter holding > 30 AND Change in promoter holding > -5 AND PEG Ratio &lt; 1.5 AND Current ratio > 1.5</code>
</div>

<div style="margin-top:12px;padding:12px;background:#0a0a18;border:1px solid #00ff4120;font-size:10px;color:#666">
  <strong style="color:#00e535">ChartInk Scanner (chartink.com/screener):</strong><br><br>
  <code style="color:#aaa;line-height:1.9;white-space:pre-wrap">( ( [Daily EMA ( [Close] ,9)] &gt; [Daily EMA ( [Close] ,20)] ) AND ( [Daily EMA ( [Close] ,20)] &gt; [Daily EMA ( [Close] ,50)] ) AND ( [Daily EMA ( [Close] ,50)] &gt; [Daily SMA ( [Close] ,200)] ) AND ( [Daily RSI ( [Close] ,14)] &gt; 55 ) AND ( [Daily RSI ( [Close] ,14)] &lt; 78 ) AND ( [Daily Volume] &gt; 1.5 * [20 day average volume] ) AND ( [Daily Close] &gt; [20 day high] ) AND ( [Daily Market cap] &gt; 500 ) )</code>
</div>

<p style="font-size:9px;color:#003311;border-top:1px solid #00ff4108;padding-top:10px;margin-top:20px">
  Auto-generated · ONE PIECE Quant Terminal · {run_time} IST · {date.today()} · Not financial advice.
</p>
</div></body></html>"""


def send_email(html: str, subject: str) -> bool:
    if not RESEND_API_KEY:
        print("  RESEND_API_KEY not set — email skipped")
        return False
    try:
        payload = json.dumps({
            "from":    "IQF Alerts <onboarding@resend.dev>",
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
        print(f"  Email failed: {e.code} {e.read().decode()}")
        return False
    except Exception as e:
        print(f"  Email failed: {e}")
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
