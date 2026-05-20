"""
Telegram Bot — Webhook Handler
POST /api/telegram        receives updates from Telegram
GET  /api/telegram/setup  register webhook URL (call once after deploy)

Flow:
  Any message → strategy inline keyboard
  Button press → read Supabase screener_cache → send formatted results
  Scheduled alerts (multibagger_alert.py) → also push via this bot
"""
from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

router = APIRouter()

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
API_BASE     = os.getenv("SCREENER_API_URL", "https://onepiece-labs.vercel.app")

_TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

STRATEGIES = [
    ("vcp",          "📊 VCP",          "Volatility Contraction Pattern"),
    ("ipo_base",     "🆕 IPO Base",     "Post-listing consolidation"),
    ("rocket_base",  "🚀 Rocket Base",  "Post-explosive-move base"),
    ("breakout",     "💥 Breakout",     "52-week high + volume surge"),
    ("rsi_reversal", "↩️ RSI Reversal", "Oversold bounce"),
    ("golden_cross", "✨ Golden Cross", "EMA20 > EMA50 > SMA200"),
    ("multibagger",  "🌟 Multibagger",  "11-condition high-conviction"),
]

STRATEGY_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "📊 VCP",          "callback_data": "scan_vcp"},
            {"text": "🆕 IPO Base",     "callback_data": "scan_ipo_base"},
            {"text": "🚀 Rocket Base",  "callback_data": "scan_rocket_base"},
        ],
        [
            {"text": "💥 Breakout",     "callback_data": "scan_breakout"},
            {"text": "↩️ RSI Reversal", "callback_data": "scan_rsi_reversal"},
            {"text": "✨ Golden Cross", "callback_data": "scan_golden_cross"},
        ],
        [
            {"text": "🌟 Multibagger",  "callback_data": "scan_multibagger"},
            {"text": "🔥 All Strategies","callback_data": "scan_all"},
        ],
    ]
}


# ── Telegram helpers ───────────────────────────────────────────────────────────

def _tg_post(method: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_TG_BASE}/{method}",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def _send(chat_id: int | str, text: str, keyboard: dict | None = None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = keyboard
    _tg_post("sendMessage", payload)


def _answer_callback(callback_id: str) -> None:
    _tg_post("answerCallbackQuery", {"callback_query_id": callback_id})


# ── Supabase cache read ────────────────────────────────────────────────────────

def _read_cache(strategy: str) -> tuple[list[dict], str | None]:
    """Returns (results, scanned_at_iso) from Supabase screener_cache. Fast < 1s."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return [], None
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/screener_cache"
            f"?strategy=eq.{strategy}&select=results,scanned_at&limit=1"
        )
        req = urllib.request.Request(
            url,
            headers={
                "apikey":         SUPABASE_KEY,
                "Authorization":  f"Bearer {SUPABASE_KEY}",
                "Content-Type":   "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            rows = json.loads(resp.read())
        if not rows:
            return [], None
        row = rows[0]
        raw = row.get("results")
        results = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return results, row.get("scanned_at")
    except Exception:
        return [], None


def _cache_age_mins(scanned_at: str | None) -> float | None:
    if not scanned_at:
        return None
    try:
        dt = datetime.fromisoformat(scanned_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return None


# ── Screener trigger (fire-and-forget) ────────────────────────────────────────

def _trigger_scan(strategy: str) -> None:
    try:
        url = f"{API_BASE}/api/screener/scan?strategy={strategy}&universe=nifty500"
        req = urllib.request.Request(
            url, data=b"", method="POST",
            headers={"User-Agent": "curl/8.4.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as _:
            pass
    except Exception:
        pass


# ── Message formatters ─────────────────────────────────────────────────────────

def _strategy_label(strategy: str) -> str:
    for s, label, _ in STRATEGIES:
        if s == strategy:
            return label
    return strategy.upper()


def _format_results(strategy: str, results: list[dict], scanned_at: str | None) -> str:
    label = _strategy_label(strategy)
    age   = _cache_age_mins(scanned_at)
    age_str = f"_{int(age)}m ago_" if age is not None else "_no cache_"

    if not results:
        return (
            f"{label} — *No candidates*\n\n"
            f"No stocks above the confidence threshold. {age_str}\n"
            "_Scans run 3× daily: 10:30 AM · 2 PM · 10 PM IST_"
        )

    lines = [f"{label} — *{len(results)} candidates* {age_str}", ""]

    for r in results[:12]:
        ticker = r.get("ticker") or r.get("symbol", "?")
        ltp    = r.get("ltp", 0)
        conf   = r.get("confidence", 0)
        rsi    = r.get("rsi", "—")
        sl     = r.get("sl") or r.get("stop_loss", 0)
        tp1    = r.get("tp1") or r.get("target1", 0)
        conf_icon = "🟢" if conf >= 95 else "🟡"
        line = f"{conf_icon} *{ticker}* ₹{ltp:,.0f} | {conf}% | RSI {rsi}"
        if sl:
            line += f" | SL ₹{sl:,.0f}"
        lines.append(line)

    if len(results) > 12:
        lines.append(f"\n_...+{len(results) - 12} more in dashboard/email_")

    lines += ["", "🔗 [Dashboard](https://dashboard-two-plum-91.vercel.app)", "_Not financial advice_"]
    return "\n".join(lines)


def _format_all_summary(all_data: list[tuple[str, list[dict], str | None]]) -> str:
    lines = ["📊 *One Piece — All Strategy Scan Summary*", ""]
    for strategy, results, scanned_at in all_data:
        label = _strategy_label(strategy)
        age   = _cache_age_mins(scanned_at)
        age_str = f"({int(age)}m ago)" if age is not None else "(no cache)"
        count = len(results)
        if count == 0:
            lines.append(f"{label}: _no candidates_ {age_str}")
        else:
            top = results[0]
            top_ticker = top.get("ticker") or top.get("symbol", "?")
            top_conf   = top.get("confidence", 0)
            lines.append(f"{label}: *{count} hits* · top: {top_ticker} {top_conf}% {age_str}")
    lines += [
        "",
        "_Tap a strategy button for full details._",
        "🔗 [Dashboard](https://dashboard-two-plum-91.vercel.app)",
    ]
    return "\n".join(lines)


# ── Business logic ─────────────────────────────────────────────────────────────

async def _handle_strategy(chat_id: int | str, strategy: str) -> None:
    if strategy == "all":
        # Read all 7 strategies concurrently
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, _read_cache, s)
            for s, _, _ in STRATEGIES
        ]
        cache_results = await asyncio.gather(*tasks)
        all_data = [
            (STRATEGIES[i][0], cache_results[i][0], cache_results[i][1])
            for i in range(len(STRATEGIES))
        ]
        summary = _format_all_summary(all_data)
        _send(chat_id, summary, STRATEGY_KEYBOARD)
        return

    # Single strategy
    loop = asyncio.get_event_loop()
    results, scanned_at = await loop.run_in_executor(None, _read_cache, strategy)

    age = _cache_age_mins(scanned_at)
    if age is None or age > 240:
        _send(chat_id, f"🔄 *No fresh cache for {_strategy_label(strategy)}* — triggering scan...\n_Results will be ready in ~2 minutes. Run again to fetch._")
        await loop.run_in_executor(None, _trigger_scan, strategy)
        return

    msg = _format_results(strategy, results, scanned_at)
    _send(chat_id, msg, STRATEGY_KEYBOARD)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("")
async def telegram_webhook(request: Request):
    """Receives all updates from Telegram."""
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=200)

    # ── Callback query (inline button press) ─────────────────────────────────
    if cq := body.get("callback_query"):
        chat_id = cq["message"]["chat"]["id"]
        data    = cq.get("data", "")
        _answer_callback(cq["id"])

        if data.startswith("scan_"):
            await _handle_strategy(chat_id, data[5:])

        return Response(status_code=200)

    # ── Regular message ───────────────────────────────────────────────────────
    message = body.get("message", {})
    if not message:
        return Response(status_code=200)

    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return Response(status_code=200)

    _send(
        chat_id,
        "👋 *ONE PIECE Quant Terminal*\n\nWhich screen would you like to run?",
        STRATEGY_KEYBOARD,
    )
    return Response(status_code=200)


@router.get("/setup")
async def setup_webhook(request: Request):
    """Register the webhook URL with Telegram. Call once after deployment."""
    base    = str(request.base_url).rstrip("/")
    wh_url  = f"{base}/api/telegram"
    result  = _tg_post("setWebhook", {
        "url":             wh_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    })
    return {"webhook_url": wh_url, "telegram_response": result}


@router.get("/info")
async def webhook_info():
    """Check current webhook registration status."""
    result = _tg_post("getWebhookInfo", {})
    return result
