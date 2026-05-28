#!/usr/bin/env python3
"""
Earnings Pulse Listener
=======================
Monitors @earnings_pulse Telegram channel for new earnings cards,
extracts structured data using vision LLMs, validates numbers, and
upserts into Supabase.

Vision provider priority:
  1. NVIDIA NIM  — llama-3.2-90b-vision (free 1000 credits, best accuracy)
  2. Gemini Flash — fallback if NVIDIA fails / quota exhausted

Run ONCE to authenticate (Telethon saves session to earnings_session.session):
  python scripts/earnings_listener.py

On subsequent runs it resumes automatically.

Dependencies:
  pip install telethon httpx python-dotenv openai

Free credentials:
  Telegram API: https://my.telegram.org/apps  (API_ID + API_HASH)
  NVIDIA NIM:   https://build.nvidia.com       (NVIDIA_API_KEY → nvapi-...)
  Gemini:       https://aistudio.google.com/apikey (fallback)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

# Load .env from repo root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Configuration ─────────────────────────────────────────────────────────────
TELEGRAM_API_ID   = int(os.environ.get("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE    = os.environ.get("TELEGRAM_PHONE", "")
NVIDIA_API_KEY    = os.environ.get("NVIDIA_API_KEY", "")
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
SB_URL            = os.environ.get("SUPABASE_URL", "")
SB_KEY            = os.environ.get("SUPABASE_SERVICE_KEY", "")
CHANNEL           = "earnings_pulse"

# Need at least one vision provider
_MISSING = [k for k, v in {
    "TELEGRAM_API_ID": TELEGRAM_API_ID,
    "TELEGRAM_API_HASH": TELEGRAM_API_HASH,
    "TELEGRAM_PHONE": TELEGRAM_PHONE,
    "SUPABASE_URL": SB_URL,
    "SUPABASE_SERVICE_KEY": SB_KEY,
}.items() if not v or v == "0"]

if not NVIDIA_API_KEY and not GEMINI_API_KEY:
    _MISSING.append("NVIDIA_API_KEY or GEMINI_API_KEY")

if _MISSING:
    print(f"[Config] Missing env vars: {', '.join(_MISSING)}")
    sys.exit(1)

_SB_HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Content-Type": "application/json",
}

# ── Vision providers ──────────────────────────────────────────────────────────
# NVIDIA NIM (primary) — OpenAI-compatible, free 1000 credits
# https://build.nvidia.com → "Get API Key"
_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
_NVIDIA_MODEL = "meta/llama-3.2-11b-vision-instruct"   # 11b responds fast; 90b times out on free tier

# Gemini (fallback)
_GEMINI_MODEL = "gemini-2.0-flash"

EXTRACT_PROMPT = """You are a financial data extraction specialist for Indian stock markets.

Extract ALL data from this earnings result card image and return ONLY valid JSON.
Be precise — copy numbers exactly as shown. Do not round or estimate.

Return JSON in this exact schema (use null for missing/dash values):
{
  "company": "exact company name",
  "ticker": "NSE ticker (no exchange prefix)",
  "sector": "sector from card",
  "quarter": "Q4FY26",
  "pulse_rating": "Great|Good|Mixed|Poor",

  "sales": {
    "current": 0, "prev_q": 0, "prev_y": 0,
    "qoq_pct": 0, "yoy_pct": 0
  },
  "other_income": {
    "current": null, "prev_q": null, "prev_y": null
  },
  "op": {
    "current": 0, "prev_q": 0, "prev_y": 0,
    "qoq_pct": 0, "yoy_pct": 0
  },
  "opm": {
    "current_pct": 0, "prev_q_pct": 0, "prev_y_pct": 0,
    "qoq_bps": 0, "yoy_bps": 0
  },
  "pat": {
    "current": 0, "prev_q": 0, "prev_y": 0,
    "qoq_pct": 0, "yoy_pct": 0
  },
  "eps": {
    "current": 0, "prev_q": 0, "prev_y": 0,
    "qoq_pct": 0, "yoy_pct": 0
  },

  "cmp": 0,
  "pe_ratio": 0,
  "market_cap_cr": 0,
  "currency": "Cr",
  "filed_at": "ISO datetime string or null"
}

Rules:
- OPM shown as "9.2%" → opm.current_pct = 9.2
- OPM change shown as "-61 bps" → opm.qoq_bps = -61
- Growth % shown as "22%" → qoq_pct = 22  (NOT 0.22)
- Market cap "17.9K Cr" → market_cap_cr = 17900
- "-" cell means null
- Ticker from the chip/badge like [FINCABLES] → "FINCABLES"
"""


def _parse_json_from_text(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


def _compress_image(image_bytes: bytes, max_kb: int = 800) -> bytes:
    """Compress image if > max_kb to stay within API payload limits."""
    if len(image_bytes) <= max_kb * 1024:
        return image_bytes
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        quality = 75
        while quality >= 30:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= max_kb * 1024:
                print(f"  [Image] Compressed {len(image_bytes)//1024}KB → {buf.tell()//1024}KB (q={quality})")
                return buf.getvalue()
            quality -= 15
        # Last resort: resize
        buf = io.BytesIO()
        img.thumbnail((1024, 1024))
        img.save(buf, format="JPEG", quality=60)
        return buf.getvalue()
    except ImportError:
        return image_bytes  # Pillow not installed, send as-is


async def _extract_nvidia(image_bytes: bytes) -> Optional[dict]:
    """NVIDIA NIM llama-3.2-11b-vision — primary provider."""
    if not NVIDIA_API_KEY:
        return None
    import base64
    image_bytes = _compress_image(image_bytes)
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": _NVIDIA_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",      "text": EXTRACT_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "temperature": 0,
        "max_tokens": 1024,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            f"{_NVIDIA_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
    if r.status_code != 200:
        print(f"  [NVIDIA] HTTP {r.status_code}: {r.text[:300]}")
        return None
    text = r.json()["choices"][0]["message"]["content"]
    data = _parse_json_from_text(text)
    if data:
        print(f"  [NVIDIA] {data.get('ticker')} {data.get('quarter')} — {data.get('pulse_rating')}")
    return data


async def _extract_gemini(image_bytes: bytes) -> Optional[dict]:
    """Gemini Flash — fallback provider."""
    if not GEMINI_API_KEY:
        return None
    import base64
    try:
        from google import genai as _gai
        client = _gai.Client(api_key=GEMINI_API_KEY)
        import google.genai.types as _gtypes
        resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[
                EXTRACT_PROMPT,
                _gtypes.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
            ],
        )
        data = _parse_json_from_text(resp.text)
        if data:
            print(f"  [Gemini] {data.get('ticker')} {data.get('quarter')} — {data.get('pulse_rating')}")
        return data
    except Exception as e:
        print(f"  [Gemini] Error: {e}")
        return None


async def extract_from_image(image_bytes: bytes) -> Optional[dict]:
    """Try NVIDIA first, fall back to Gemini only if quota is not exhausted."""
    # Primary: NVIDIA NIM
    if NVIDIA_API_KEY:
        try:
            data = await _extract_nvidia(image_bytes)
            if data and data.get("ticker"):
                return data
        except Exception as e:
            print(f"  [NVIDIA] Exception: {type(e).__name__}: {e}")

    # Fallback: Gemini (skip silently if quota is dead)
    if GEMINI_API_KEY:
        try:
            data = await _extract_gemini(image_bytes)
            if data and data.get("ticker"):
                return data
        except Exception as e:
            err = str(e)
            if "RESOURCE_EXHAUSTED" in err or "limit: 0" in err:
                pass  # Quota dead — skip silently
            else:
                print(f"  [Gemini] Error: {e}")

    return None  # Not every channel message is an earnings card — skip quietly


# ── Validation ────────────────────────────────────────────────────────────────

def _safe_pct(new: float, old: float) -> Optional[float]:
    if old and old != 0:
        return round((new - old) / abs(old) * 100, 1)
    return None


def validate_and_score(data: dict) -> tuple[dict, float]:
    """
    Cross-check numbers for internal consistency.
    Auto-corrects obvious OCR errors.
    Returns (corrected_data, confidence 0.0–1.0).
    """
    score = 1.0

    try:
        sales = (data.get("sales") or {}).get("current")
        op    = (data.get("op")    or {}).get("current")
        opm_c = (data.get("opm")   or {}).get("current_pct")
        if sales and op and opm_c is not None:
            computed = round((op / sales) * 100, 1)
            if abs(computed - opm_c) > 0.6:
                print(f"  [Validate] OPM claimed {opm_c}% → correcting to {computed}%")
                data["opm"]["current_pct"] = computed
                score -= 0.08
    except (KeyError, TypeError, ZeroDivisionError):
        score -= 0.05

    for metric in ("sales", "op", "pat", "eps"):
        try:
            m = data.get(metric) or {}
            curr        = m.get("current")
            prev_q      = m.get("prev_q")
            prev_y      = m.get("prev_y")
            claimed_qoq = m.get("qoq_pct")
            claimed_yoy = m.get("yoy_pct")

            comp_qoq = _safe_pct(curr, prev_q)
            comp_yoy = _safe_pct(curr, prev_y)

            if comp_qoq is not None and claimed_qoq is not None and abs(comp_qoq - claimed_qoq) > 1.5:
                print(f"  [Validate] {metric} QoQ claimed {claimed_qoq}% → correcting to {comp_qoq}%")
                data[metric]["qoq_pct"] = comp_qoq
                score -= 0.04

            if comp_yoy is not None and claimed_yoy is not None and abs(comp_yoy - claimed_yoy) > 1.5:
                print(f"  [Validate] {metric} YoY claimed {claimed_yoy}% → correcting to {comp_yoy}%")
                data[metric]["yoy_pct"] = comp_yoy
                score -= 0.04
        except (KeyError, TypeError):
            score -= 0.02

    return data, max(0.0, min(1.0, score))


def compute_pulse_rating(data: dict) -> str:
    """Recompute Pulse Rating from extracted financials."""
    try:
        sales_yoy = (data.get("sales") or {}).get("yoy_pct") or 0
        pat_yoy   = (data.get("pat")   or {}).get("yoy_pct") or 0
        opm_yoy   = (data.get("opm")   or {}).get("yoy_bps") or 0
        eps_yoy   = (data.get("eps")   or {}).get("yoy_pct") or 0

        pts = 0
        # Revenue
        if sales_yoy >= 20:   pts += 3
        elif sales_yoy >= 10: pts += 2
        elif sales_yoy >= 0:  pts += 1
        else:                 pts -= 1
        # PAT (highest weight)
        if pat_yoy >= 20:   pts += 4
        elif pat_yoy >= 10: pts += 3
        elif pat_yoy >= 0:  pts += 1
        else:               pts -= 2
        # Margins
        pts += 1 if opm_yoy >= 0 else -1
        # EPS
        if eps_yoy >= 15:  pts += 2
        elif eps_yoy >= 5: pts += 1
        elif eps_yoy < 0:  pts -= 1

        if pts >= 8:   return "Great"
        elif pts >= 5: return "Good"
        elif pts >= 2: return "Mixed"
        else:          return "Poor"
    except Exception:
        return "Mixed"


# ── BSE XBRL Fallback ─────────────────────────────────────────────────────────

async def _bse_scrip_code(ticker: str, client: httpx.AsyncClient) -> Optional[str]:
    """Resolve NSE ticker → BSE scrip code."""
    try:
        r = await client.get(
            f"https://api.bseindia.com/BseIndiaAPI/api/fetchsymbol/w?Type=EQ&Grpcd=&scripcode=&Scrip={ticker}",
            timeout=8,
        )
        data = r.json()
        if data and isinstance(data, list) and data[0].get("scripcode"):
            return str(data[0]["scripcode"])
    except Exception:
        pass
    return None


async def fetch_bse_quarterly(ticker: str) -> Optional[dict]:
    """
    Fetch the most recent quarterly P&L from BSE.
    Returns partial dict that can patch low-confidence Gemini data.
    """
    bse_hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.bseindia.com/",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(headers=bse_hdrs, follow_redirects=True, timeout=12) as client:
        code = await _bse_scrip_code(ticker, client)
        if not code:
            print(f"  [BSE] Scrip code not found for {ticker}")
            return None

        try:
            # BSE quarterly standalone P&L
            url = (
                f"https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w"
                f"?scripcode={code}&flag=C"
            )
            r = await client.get(url)
            payload = r.json()

            # BSE returns different structures — handle the most common one
            qtrs = payload.get("Quarters") or payload.get("quarterly") or []
            if not qtrs or not isinstance(qtrs, list) or len(qtrs) < 3:
                print(f"  [BSE] Insufficient quarterly data for {ticker}")
                return None

            # Latest = qtrs[0], prev_q = qtrs[1], prev_y = qtrs[4] (same Q prev yr)
            def _v(q: dict, key: str) -> Optional[float]:
                val = q.get(key) or q.get(key.lower())
                try:
                    return float(val) if val not in (None, "", "-") else None
                except (ValueError, TypeError):
                    return None

            curr   = qtrs[0]
            prev_q = qtrs[1]
            prev_y = qtrs[4] if len(qtrs) > 4 else None

            net_sales_curr = _v(curr, "NetSales") or _v(curr, "TotalRevenue")
            pat_curr       = _v(curr, "PAT")       or _v(curr, "NetProfit")
            op_curr        = _v(curr, "EBITDA")    or _v(curr, "OperatingProfit")

            if not net_sales_curr:
                return None

            result: dict = {}
            if net_sales_curr:
                result["sales"] = {
                    "current": net_sales_curr,
                    "prev_q":  _v(prev_q, "NetSales"),
                    "prev_y":  _v(prev_y, "NetSales") if prev_y else None,
                }
            if pat_curr:
                result["pat"] = {
                    "current": pat_curr,
                    "prev_q":  _v(prev_q, "PAT"),
                    "prev_y":  _v(prev_y, "PAT") if prev_y else None,
                }
            if op_curr:
                result["op"] = {
                    "current": op_curr,
                    "prev_q":  _v(prev_q, "EBITDA"),
                    "prev_y":  _v(prev_y, "EBITDA") if prev_y else None,
                }

            print(f"  [BSE] Fetched quarterly data for {ticker} ({code})")
            return result

        except Exception as e:
            print(f"  [BSE] Error fetching {ticker}: {e}")
            return None


# ── Supabase Writer ───────────────────────────────────────────────────────────

def _parse_market_cap(raw) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).replace("Cr", "").replace(",", "").strip()
    if "K" in s.upper():
        s = s.upper().replace("K", "")
        try:
            return float(s) * 1000
        except ValueError:
            return None
    if "L" in s.upper():
        s = s.upper().replace("L", "")
        try:
            return float(s) * 100000
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


async def upsert_earnings(data: dict, confidence: float, source: str,
                          msg_id: Optional[int] = None) -> bool:
    rating = data.get("pulse_rating") or compute_pulse_rating(data)

    row: dict = {
        "ticker":  (data.get("ticker") or "").upper().strip(),
        "company": data.get("company"),
        "sector":  data.get("sector"),
        "quarter": data.get("quarter"),

        # use `or {}` so explicit null values from JSON don't crash .get()
        "sales_cr":        (data.get("sales")        or {}).get("current"),
        "sales_prev_q_cr": (data.get("sales")        or {}).get("prev_q"),
        "sales_prev_y_cr": (data.get("sales")        or {}).get("prev_y"),
        "sales_qoq_pct":   (data.get("sales")        or {}).get("qoq_pct"),
        "sales_yoy_pct":   (data.get("sales")        or {}).get("yoy_pct"),

        "other_income_cr":        (data.get("other_income") or {}).get("current"),
        "other_income_prev_q_cr": (data.get("other_income") or {}).get("prev_q"),
        "other_income_prev_y_cr": (data.get("other_income") or {}).get("prev_y"),

        "op_cr":        (data.get("op")  or {}).get("current"),
        "op_prev_q_cr": (data.get("op")  or {}).get("prev_q"),
        "op_prev_y_cr": (data.get("op")  or {}).get("prev_y"),
        "op_qoq_pct":   (data.get("op")  or {}).get("qoq_pct"),
        "op_yoy_pct":   (data.get("op")  or {}).get("yoy_pct"),

        "opm_pct":        (data.get("opm") or {}).get("current_pct"),
        "opm_prev_q_pct": (data.get("opm") or {}).get("prev_q_pct"),
        "opm_prev_y_pct": (data.get("opm") or {}).get("prev_y_pct"),
        "opm_qoq_bps":    (data.get("opm") or {}).get("qoq_bps"),
        "opm_yoy_bps":    (data.get("opm") or {}).get("yoy_bps"),

        "pat_cr":        (data.get("pat") or {}).get("current"),
        "pat_prev_q_cr": (data.get("pat") or {}).get("prev_q"),
        "pat_prev_y_cr": (data.get("pat") or {}).get("prev_y"),
        "pat_qoq_pct":   (data.get("pat") or {}).get("qoq_pct"),
        "pat_yoy_pct":   (data.get("pat") or {}).get("yoy_pct"),

        "eps":         (data.get("eps") or {}).get("current"),
        "eps_prev_q":  (data.get("eps") or {}).get("prev_q"),
        "eps_prev_y":  (data.get("eps") or {}).get("prev_y"),
        "eps_qoq_pct": (data.get("eps") or {}).get("qoq_pct"),
        "eps_yoy_pct": (data.get("eps") or {}).get("yoy_pct"),

        "cmp":           data.get("cmp"),
        "pe_ratio":      data.get("pe_ratio"),
        "market_cap_cr": _parse_market_cap(data.get("market_cap_cr")),

        "pulse_rating":     rating,
        "source":           source,
        "confidence_score": round(confidence, 4),
        "telegram_msg_id":  msg_id,
        "filed_at": data.get("filed_at") or datetime.utcnow().isoformat(),
    }

    # Strip None values — don't overwrite existing valid data with nulls
    row = {k: v for k, v in row.items() if v is not None}

    if not row.get("ticker"):
        print("  [Supabase] Skipping — no ticker extracted")
        return False

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SB_URL}/rest/v1/earnings_results",
            headers={
                **_SB_HEADERS,
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=row,
            timeout=10,
        )
        if r.status_code in (200, 201):
            print(f"  [Supabase] ✓ Saved {row['ticker']} {row.get('quarter')} "
                  f"[{rating}] confidence={confidence:.0%} source={source}")
            return True
        print(f"  [Supabase] ✗ {r.status_code}: {r.text[:300]}")
        return False


# ── Historical Backfill ───────────────────────────────────────────────────────

async def backfill_history(n_messages: int = 200):
    """
    Process the last N messages from the channel to backfill historical cards.
    Run once manually: python scripts/earnings_listener.py --backfill 500
    """
    try:
        from telethon import TelegramClient
        from telethon.tl.types import MessageMediaPhoto
    except ImportError:
        print("Install: pip install telethon")
        return

    print(f"[Backfill] Processing last {n_messages} messages from @{CHANNEL}...")
    client = TelegramClient("earnings_session", TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start(phone=TELEGRAM_PHONE)

    count = 0
    async for msg in client.iter_messages(CHANNEL, limit=n_messages):
        if not msg.media or not isinstance(msg.media, MessageMediaPhoto):
            continue
        print(f"\n[Backfill] msg_id={msg.id} date={msg.date.strftime('%Y-%m-%d')}")
        image_bytes = await client.download_media(msg.media, bytes)
        data = await extract_from_image(image_bytes)
        if not data or not data.get("ticker"):
            continue
        data, confidence = validate_and_score(data)
        if confidence < 0.82:
            bse_data = await fetch_bse_quarterly(data["ticker"])
            if bse_data:
                for key, val in bse_data.items():
                    if key in data and isinstance(data[key], dict) and isinstance(val, dict):
                        data[key].update({k: v for k, v in val.items() if v is not None})
                data, confidence = validate_and_score(data)
        await upsert_earnings(data, confidence, "telegram_ocr", msg.id)
        count += 1
        await asyncio.sleep(2.0)  # NVIDIA free tier: ~30 RPM, 2s gap keeps us safe

    print(f"\n[Backfill] Done — processed {count} earnings cards")
    await client.disconnect()


# ── Live Listener ─────────────────────────────────────────────────────────────

async def live_listener():
    """Main loop — listens for new messages in real time."""
    try:
        from telethon import TelegramClient, events
        from telethon.tl.types import MessageMediaPhoto
    except ImportError:
        print("Install: pip install telethon google-generativeai httpx python-dotenv")
        sys.exit(1)

    print(f"[Listener] Connecting to Telegram...")
    client = TelegramClient("earnings_session", TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start(phone=TELEGRAM_PHONE)
    me = await client.get_me()
    print(f"[Listener] Logged in as {me.first_name} (+{me.phone}) ✓")

    @client.on(events.NewMessage(chats=CHANNEL))
    async def on_message(event):
        msg = event.message
        if not msg.media or not isinstance(msg.media, MessageMediaPhoto):
            return

        print(f"\n[Listener] New earnings card — msg_id={msg.id} "
              f"time={datetime.utcnow().strftime('%H:%M:%S')}")

        image_bytes = await client.download_media(msg.media, bytes)
        data = await extract_from_image(image_bytes)
        if not data or not data.get("ticker"):
            print("  [Listener] No ticker found — skipping")
            return

        data, confidence = validate_and_score(data)

        # BSE fallback when confidence is borderline
        if confidence < 0.85:
            print(f"  [Listener] Confidence {confidence:.0%} < 85% → BSE fallback")
            bse_data = await fetch_bse_quarterly(data["ticker"])
            if bse_data:
                for key, val in bse_data.items():
                    if key in data and isinstance(data[key], dict) and isinstance(val, dict):
                        data[key].update({k: v for k, v in val.items() if v is not None})
                data, confidence = validate_and_score(data)
                print(f"  [Listener] After BSE merge: confidence={confidence:.0%}")

        source = "bse_xbrl" if confidence < 0.85 else "telegram_ocr"
        await upsert_earnings(data, confidence, source, msg.id)

    print(f"[Listener] Watching @{CHANNEL} for new earnings cards...")
    print("[Listener] Press Ctrl+C to stop\n")
    await client.run_until_disconnected()


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--backfill" in sys.argv:
        try:
            idx = sys.argv.index("--backfill")
            n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 200
        except (ValueError, IndexError):
            n = 200
        asyncio.run(backfill_history(n))
    else:
        asyncio.run(live_listener())
