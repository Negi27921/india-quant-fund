"""
Breakout Monitor — checks watchlist_items for result-day high breakouts.

Logic:
  - Fetch items with result_high set, breakout_alerted=False, result_date within 10 trading days
  - For each: fetch today's OHLCV via yfinance
  - Breakout = close > result_high AND volume > 1.5× result_volume_avg
  - On breakout: mark breakout_date in watchlist_items + send Telegram alert
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

import yfinance as yf

SUPABASE_URL   = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID", "")

_TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
_BREAKOUT_WINDOW_DAYS = 14     # calendar days to keep watching after result
_VOL_MULTIPLIER       = 1.5    # volume must be 1.5× avg to confirm


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_get(path: str) -> list:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}", headers=_sb_headers()
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  [sb_get] {path}: {e}")
        return []


def _sb_patch(path: str, body: dict) -> None:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    headers = _sb_headers()
    headers["Prefer"] = "return=minimal"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=data, headers=headers, method="PATCH"
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"  [sb_patch] {path}: {e}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def _tg_send(text: str) -> None:
    if not (BOT_TOKEN and CHAT_ID):
        return
    payload = json.dumps({
        "chat_id": CHAT_ID, "text": text,
        "parse_mode": "Markdown", "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"{_TG_BASE}/sendMessage", data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception as e:
        print(f"  [tg_send] {e}")


# ── Price / volume fetch ──────────────────────────────────────────────────────

def _fetch_today_ohlcv(ticker: str) -> dict | None:
    """Returns today's (or last session's) OHLCV for a ticker."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="3d", interval="1d", auto_adjust=True)
        if hist.empty:
            return None
        row = hist.iloc[-1]
        return {
            "date":   str(hist.index[-1].date()),
            "close":  float(row["Close"]),
            "high":   float(row["High"]),
            "volume": int(row["Volume"]),
        }
    except Exception as e:
        print(f"  [ohlcv] {ticker}: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    today = date.today()
    cutoff = (today - timedelta(days=_BREAKOUT_WINDOW_DAYS)).isoformat()

    # Fetch unalerted items with a result_high and recent result_date
    rows: list[dict] = _sb_get(
        f"watchlist_items"
        f"?breakout_alerted=eq.false"
        f"&result_high=not.is.null"
        f"&result_date=gte.{cutoff}"
        f"&select=id,symbol,ticker,company,result_date,result_high,result_volume_avg,result_rating,watchlist_id"
        f"&limit=50"
    )

    if not rows:
        print("No items to check.")
        return

    print(f"Checking {len(rows)} item(s) for breakout…")

    for item in rows:
        symbol   = item.get("symbol", "?")
        ticker   = item.get("ticker") or f"{symbol}.NS"
        company  = item.get("company") or symbol
        r_high   = float(item.get("result_high") or 0)
        r_vol    = int(item.get("result_volume_avg") or 0)
        rating   = item.get("result_rating") or "—"
        item_id  = item.get("id")

        if r_high <= 0:
            continue

        ohlcv = _fetch_today_ohlcv(ticker)
        if not ohlcv:
            print(f"  {symbol}: no price data")
            continue

        close  = ohlcv["close"]
        volume = ohlcv["volume"]

        price_break = close > r_high
        vol_break   = (r_vol <= 0) or (volume >= r_vol * _VOL_MULTIPLIER)
        is_breakout = price_break and vol_break

        vol_ratio = (volume / r_vol) if r_vol > 0 else None
        print(
            f"  {symbol}: close ₹{close:,.0f} vs high ₹{r_high:,.0f} | "
            f"vol {volume:,} vs {r_vol:,} ({f'{vol_ratio:.1f}x' if vol_ratio else 'N/A'}) | "
            f"breakout={'YES' if is_breakout else 'no'}"
        )

        if is_breakout:
            breakout_date = ohlcv["date"]

            # Mark in DB
            _sb_patch(
                f"watchlist_items?id=eq.{item_id}",
                {
                    "breakout_alerted": True,
                    "breakout_date":    breakout_date,
                }
            )

            # Build alert
            EMOJI_MAP = {"Excellent": "🚀", "Great": "🟢", "Good": "🔵"}
            emoji = EMOJI_MAP.get(rating, "⚡")
            vol_str = f"{vol_ratio:.1f}×" if vol_ratio else "N/A"

            msg = (
                f"{emoji} *BREAKOUT ALERT — {symbol}*\n\n"
                f"*{company}* broke its result-day high!\n\n"
                f"Close  : ₹{close:,.0f}  _(above ₹{r_high:,.0f} result high)_\n"
                f"Volume : {volume:,}  _({vol_str} avg)_\n"
                f"Rating : {rating}\n"
                f"Date   : {breakout_date}\n\n"
                f"🔗 [Results Dashboard](https://luffy-labs.vercel.app/results)\n"
                f"📊 [Chart](https://www.tradingview.com/chart/?symbol=NSE%3A{symbol})\n\n"
                f"_This is not financial advice_"
            )
            _tg_send(msg)
            print(f"  → Alert sent for {symbol}")


if __name__ == "__main__":
    main()
