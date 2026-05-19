"""AI Trading Journal — CRUD backed by Supabase + live price + AI coach."""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)

_TABLE = "journal_trades"


# ── Supabase storage helpers ───────────────────────────────────────────────────

def _row_to_dict(d: dict) -> dict:
    return {
        "id":              d.get("id"),
        "stockName":       d.get("stock_name"),
        "buyPrice":        float(d.get("buy_price") or 0),
        "quantity":        int(d.get("quantity") or 0),
        "entryDate":       d.get("entry_date"),
        "capitalUsed":     float(d.get("capital_used") or 0),
        "tradeType":       d.get("trade_type"),
        "status":          d.get("status"),
        "sellPrice":       float(d["sell_price"]) if d.get("sell_price") is not None else None,
        "exitDate":        d.get("exit_date"),
        "strategy":        d.get("strategy"),
        "notes":           d.get("notes"),
        "plannedStopLoss": float(d["planned_sl"]) if d.get("planned_sl") is not None else None,
        "plannedTarget":   float(d["planned_tp"]) if d.get("planned_tp") is not None else None,
        "emotionEntry":    d.get("emotion_entry"),
        "emotionExit":     d.get("emotion_exit"),
        "marketCondition": d.get("market_cond"),
        "ruleFollowed":    d.get("rule_followed"),
        "createdAt":       d.get("created_at"),
        "updatedAt":       d.get("updated_at"),
    }


def _all_trades() -> list[dict]:
    """Fetch all trades from Supabase, newest entry_date first."""
    try:
        from data.storage import supabase_db as sdb
        rows = sdb.select(_TABLE, order="-entry_date")
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def _fetch_prices_sync(symbols: list[str]) -> dict[str, float]:
    import yfinance as yf
    prices: dict[str, float] = {}
    for sym in symbols:
        for suffix in (".NS", ".BO"):
            try:
                p = float(yf.Ticker(sym + suffix).fast_info.last_price)
                if p > 0:
                    prices[sym] = p
                    break
            except Exception:
                pass
    return prices


# ── Pydantic models ────────────────────────────────────────────────────────────

class TradeRecord(BaseModel):
    id: str
    stockName: str = Field(..., min_length=1, max_length=40)
    buyPrice: float
    quantity: int
    entryDate: str
    capitalUsed: float
    tradeType: str
    status: str
    sellPrice: float | None = None
    exitDate: str | None = None
    strategy: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    plannedStopLoss: float | None = None
    plannedTarget: float | None = None
    emotionEntry: str | None = None
    emotionExit: str | None = None
    marketCondition: str | None = None
    ruleFollowed: str | None = None
    createdAt: str


class JournalChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict] | None = None
    trades: list[dict] | None = None


class JournalChatResponse(BaseModel):
    response: str
    provider: str | None = None
    latency_ms: int | None = None
    trade_count: int = 0


# ── CRUD endpoints ─────────────────────────────────────────────────────────────

@router.get("/trades")
def get_trades():
    return _all_trades()


@router.post("/trades")
def upsert_trade(body: TradeRecord):
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id":            body.id,
        "stock_name":    body.stockName,
        "buy_price":     body.buyPrice,
        "quantity":      body.quantity,
        "entry_date":    body.entryDate,
        "capital_used":  body.capitalUsed,
        "trade_type":    body.tradeType,
        "status":        body.status,
        "sell_price":    body.sellPrice,
        "exit_date":     body.exitDate,
        "strategy":      body.strategy,
        "notes":         body.notes,
        "planned_sl":    body.plannedStopLoss,
        "planned_tp":    body.plannedTarget,
        "emotion_entry": body.emotionEntry,
        "emotion_exit":  body.emotionExit,
        "market_cond":   body.marketCondition,
        "rule_followed": body.ruleFollowed,
        "created_at":    body.createdAt,
        "updated_at":    now,
    }
    try:
        from data.storage import supabase_db as sdb
        result = sdb.upsert(_TABLE, row, on_conflict="id")
        if result:
            return _row_to_dict(result[0])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _row_to_dict(row)


@router.delete("/trades/{trade_id}")
def delete_trade(trade_id: str):
    if not trade_id or len(trade_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid trade id")
    try:
        from data.storage import supabase_db as sdb
        sdb.delete(_TABLE, {"id": trade_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "id": trade_id}


# ── Live price endpoint ────────────────────────────────────────────────────────

@router.get("/prices")
async def get_live_prices(symbols: str = ""):
    names = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not names:
        return {}

    def _fetch(name: str) -> tuple[str, float | None]:
        import yfinance as yf
        for suffix in (".NS", ".BO"):
            try:
                p = float(yf.Ticker(name + suffix).fast_info.last_price)
                if p > 0:
                    return name, round(p, 2)
            except Exception:
                pass
        return name, None

    loop = asyncio.get_running_loop()
    from concurrent.futures import ThreadPoolExecutor as TPE
    with TPE(max_workers=min(len(names), 10)) as pool:
        tasks = [loop.run_in_executor(pool, _fetch, n) for n in names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return {
        name: price
        for item in results
        if not isinstance(item, Exception)
        for name, price in [item]
    }


# ── Portfolio endpoints (Journal = Live Portfolio) ─────────────────────────────

@router.get("/positions")
async def journal_positions():
    """Open journal trades as portfolio positions with live CMPs."""
    def _compute():
        trades = _all_trades()
        open_trades = [t for t in trades if t.get("status") == "Open"]
        if not open_trades:
            return []
        symbols = list({t["stockName"] for t in open_trades})
        prices = _fetch_prices_sync(symbols)
        total_value = sum(
            prices.get(t["stockName"], t["buyPrice"]) * t["quantity"]
            for t in open_trades
        )
        result = []
        for t in open_trades:
            sym = t["stockName"]
            buy = float(t["buyPrice"])
            qty = int(t["quantity"])
            cmp = prices.get(sym, buy)
            unrealized = (cmp - buy) * qty
            ed = t.get("entryDate") or ""
            try:
                days_held = (date.today() - date.fromisoformat(ed[:10])).days
            except Exception:
                days_held = 0
            pos_value = cmp * qty
            result.append({
                "ticker":         sym,
                "name":           sym,
                "quantity":       qty,
                "avg_buy_price":  buy,
                "current_price":  round(cmp, 2),
                "unrealized_pnl": round(unrealized, 2),
                "pnl_pct":        round((cmp - buy) / buy * 100, 2) if buy > 0 else 0.0,
                "weight":         round(pos_value / total_value * 100, 2) if total_value > 0 else 0.0,
                "sector":         "",
                "strategy":       t.get("strategy") or "",
                "buy_date":       ed,
                "days_held":      days_held,
                "notes":          t.get("notes") or "",
            })
        return result

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _compute)


@router.get("/summary")
async def journal_summary():
    """NAV, Day P&L, drawdown — computed from journal trades + live prices."""
    def _compute():
        trades = _all_trades()
        if not trades:
            return {
                "nav": 0, "total_invested": 0, "realized_pnl": 0,
                "unrealized_pnl": 0, "day_pnl": 0, "day_pnl_pct": 0,
                "drawdown": 0, "open_positions": 0, "total_trades": 0,
            }
        open_trades = [t for t in trades if t.get("status") == "Open"]
        closed_trades = [
            t for t in trades
            if t.get("status") == "Closed" and t.get("sellPrice") is not None
        ]
        realized_pnl = sum(
            (float(t["sellPrice"]) - float(t["buyPrice"])) * int(t["quantity"])
            for t in closed_trades
        )
        today = date.today().isoformat()
        today_realized = sum(
            (float(t["sellPrice"]) - float(t["buyPrice"])) * int(t["quantity"])
            for t in closed_trades
            if (t.get("exitDate") or "")[:10] == today
        )
        total_invested = sum(float(t["buyPrice"]) * int(t["quantity"]) for t in open_trades)
        symbols = list({t["stockName"] for t in open_trades})
        prices = _fetch_prices_sync(symbols) if symbols else {}
        unrealized_pnl = sum(
            (prices.get(t["stockName"], float(t["buyPrice"])) - float(t["buyPrice"])) * int(t["quantity"])
            for t in open_trades
        )
        open_value = sum(
            prices.get(t["stockName"], float(t["buyPrice"])) * int(t["quantity"])
            for t in open_trades
        )
        nav = open_value + realized_pnl
        day_pnl = today_realized + unrealized_pnl
        nav_prev = nav - day_pnl if nav - day_pnl > 0 else (nav if nav > 0 else 1)
        day_pnl_pct = day_pnl / nav_prev * 100

        # Max drawdown from closed-trade equity curve
        daily: dict[str, float] = defaultdict(float)
        for t in closed_trades:
            ed = (t.get("exitDate") or "")[:10]
            if ed:
                daily[ed] += (float(t["sellPrice"]) - float(t["buyPrice"])) * int(t["quantity"])
        equity = peak = max_dd = 0.0
        for d in sorted(daily.keys()):
            equity += daily[d]
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak * 100)

        return {
            "nav":            round(nav, 2),
            "total_invested": round(total_invested, 2),
            "realized_pnl":   round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "day_pnl":        round(day_pnl, 2),
            "day_pnl_pct":    round(day_pnl_pct, 4),
            "drawdown":       round(max_dd, 4),
            "open_positions": len(open_trades),
            "total_trades":   len(trades),
        }

    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(_executor, _compute), timeout=20.0)
    except asyncio.TimeoutError:
        return {"nav": 0, "total_invested": 0, "realized_pnl": 0, "unrealized_pnl": 0,
                "day_pnl": 0, "day_pnl_pct": 0, "drawdown": 0, "open_positions": 0, "total_trades": 0}


@router.get("/pnl-calendar")
async def journal_pnl_calendar(year: int | None = None):
    """Daily P&L from closed journal trades grouped by exit date."""
    def _compute():
        trades = _all_trades()
        closed = [
            t for t in trades
            if t.get("status") == "Closed"
            and t.get("sellPrice") is not None
            and t.get("exitDate")
        ]
        daily: dict[str, float] = defaultdict(float)
        for t in closed:
            ed = (t["exitDate"] or "")[:10]
            if not ed:
                continue
            if year and not ed.startswith(str(year)):
                continue
            daily[ed] += (float(t["sellPrice"]) - float(t["buyPrice"])) * int(t["quantity"])
        result, running = [], 0.0
        for d in sorted(daily.keys()):
            pnl = daily[d]
            running += pnl
            result.append({
                "date":            d,
                "pnl":             round(pnl, 2),
                "pnl_pct":         0.0,
                "portfolio_value": round(running, 2),
            })
        return result

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _compute)


# ── AI system prompt ───────────────────────────────────────────────────────────

JOURNAL_SYSTEM_PROMPT = """You are my Personal AI Trading Journal, Portfolio Manager, and Performance Coach.

You combine the mindset and decision standards of:
- A professional trader
- A portfolio manager
- A performance analyst
- A risk manager
- A trading psychologist

Your mission is to record, organize, analyze, and improve my trading and investment performance across swing trading and long-term investing.

You are not just a summarizer. You are a performance improvement system.

---
CORE OPERATING PRINCIPLES
---

1. Never hallucinate.
2. Never invent prices, dates, trade details, or conclusions.
3. Never assume missing information.
4. If required data is missing, ask before analyzing.
5. If live price is needed for an open trade, clearly say: "Live price not available."
6. Be practical, direct, and performance-focused.
7. Prioritize profitability, discipline, and repeatable execution.
8. Separate facts, interpretations, and coaching.
9. Do not sugarcoat mistakes.
10. Improve me like a serious trader, not like a casual user.

---
CALCULATION RULES
---

For closed trades:
P&L = (Sell Price - Buy Price) × Quantity
P&L % = ((Sell Price - Buy Price) / Buy Price) × 100

For open trades, only if valid latest price is available:
Unrealized P&L = (Current Price - Buy Price) × Quantity

Portfolio metrics must include:
- Total Capital
- Total Invested (open positions)
- Total Realized P&L
- Total P&L %
- Win Rate
- Average Profit / Average Loss
- Profit Factor
- Risk-Reward Ratio
- Expectancy per trade (if enough data)

If a metric cannot be calculated reliably, say so clearly.

---
MANDATORY OUTPUT FORMAT (for full analysis)
---

## 📊 Portfolio Summary
## 📈 Trade Log (table)
Use 🟢 profit / 🔴 loss / ⚪ open
## 📉 Equity Curve Insight
## 📊 Open Positions
## 🧠 Performance Analysis
## 🧠 Psychology Analysis (evidence-based only)
## 🔍 Pattern Recognition
## ⚠️ Critical Mistakes (blunt, ranked by severity)
## 🚀 Action Plan
## 📊 Risk Management
## 🧾 Coach's Verdict
## 🔬 System Quality Check
Judge: Real edge / Weak edge / No proven edge yet
Base ONLY on actual results, expectancy, repeatability. No optimism without evidence.

---
COACHING STYLE
---

Tone: Professional, sharp, honest, practical.
Do NOT: give generic motivation, praise weak discipline, hide mistakes.
Do: tell the truth, coach like someone serious about mastering trading.
"""


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _fmt_trades(trades: list[dict]) -> str:
    if not trades:
        return "No trades recorded yet."
    # Summarize for large datasets to avoid token limits
    if len(trades) > 30:
        closed = [t for t in trades if t.get("status") == "Closed"]
        open_t = [t for t in trades if t.get("status") == "Open"]
        summary = f"Total trades: {len(trades)} ({len(open_t)} open, {len(closed)} closed). "
        summary += f"Recent 20 trades + all open positions below.\n\n"
        subset = open_t + closed[-20:]
    else:
        subset = trades
        summary = ""
    return summary + "Trade journal data (JSON):\n" + json.dumps(subset, indent=2, ensure_ascii=False, default=str)


def _groq(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    import requests as _req
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    messages = [{"role": "system", "content": system}]
    for t in (history or []):
        messages.append({"role": t.get("role", "user"), "content": t.get("content", "")})
    messages.append({"role": "user", "content": user_msg})
    r = _req.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 2000},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    import requests as _req
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    contents: list[dict] = []
    for t in (history or []):
        role = t.get("role", "user")
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": t.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": user_msg}]})
    r = _req.post(
        url,
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2000},
        },
        timeout=22,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _openrouter(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    import requests as _req
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENROUTER_API_KEY not set")
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001").strip()
    messages = [{"role": "system", "content": system}]
    for t in (history or []):
        messages.append({"role": t.get("role", "user"), "content": t.get("content", "")})
    messages.append({"role": "user", "content": user_msg})
    r = _req.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://luffy-labs.vercel.app",
        },
        json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 2000},
        timeout=22,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _llm(system: str, user_msg: str, history: list[dict] | None = None) -> tuple[str, str, int]:
    # Groq is fastest (1-3s) → Gemini → OpenRouter as fallbacks
    chain = [
        ("groq",       _groq),
        ("gemini",     _gemini),
        ("openrouter", _openrouter),
    ]
    errors: list[str] = []
    for name, fn in chain:
        try:
            t0 = time.monotonic()
            result = fn(system, user_msg, history)
            ms = int((time.monotonic() - t0) * 1000)
            if result and result.strip():
                return result.strip(), name, ms
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:60]}")
    return (
        f"AI Coach is temporarily unavailable. Errors: {'; '.join(errors[:2])}. "
        "Please ensure GROQ_API_KEY is set in Vercel environment variables.",
        "none",
        0,
    )


# ── AI chat endpoint ───────────────────────────────────────────────────────────

@router.post("/chat", response_model=JournalChatResponse)
async def journal_chat(body: JournalChatRequest):
    loop = asyncio.get_running_loop()

    def _fetch_and_chat():
        trades = body.trades[:200] if body.trades else _all_trades()
        trade_ctx = _fmt_trades(trades)
        user_msg = f"{trade_ctx}\n\n---\n\nUser request: {body.message.strip()}"
        history = (body.history or [])[-6:] if body.history else None
        reply, provider, latency_ms = _llm(JOURNAL_SYSTEM_PROMPT, user_msg, history)
        return reply, provider, latency_ms, len(trades)

    try:
        reply, provider, latency_ms, trade_count = await asyncio.wait_for(
            loop.run_in_executor(_executor, _fetch_and_chat),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        reply = "The analysis timed out. Try asking about fewer trades or a specific section (e.g. 'Show my open positions' or 'What are my critical mistakes?')."
        provider = "timeout"
        latency_ms = 55000
        trade_count = 0

    return JournalChatResponse(
        response=reply,
        provider=provider,
        latency_ms=latency_ms,
        trade_count=trade_count,
    )
