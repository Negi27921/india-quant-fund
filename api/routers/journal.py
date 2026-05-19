"""AI Trading Journal — CRUD storage + performance coach AI."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)

# ── SQLite storage ─────────────────────────────────────────────────────────────
# Defaults to /tmp (ephemeral on Vercel but works across warm invocations).
# Set JOURNAL_DB_PATH env var to a persistent path (e.g. ./data/journal.db)
# for local dev or long-running servers.
_JOURNAL_DB = os.getenv("JOURNAL_DB_PATH", "/tmp/iqf_journal.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS journal_trades (
    id            TEXT PRIMARY KEY,
    stock_name    TEXT NOT NULL,
    buy_price     REAL NOT NULL,
    quantity      INTEGER NOT NULL,
    entry_date    TEXT NOT NULL,
    capital_used  REAL NOT NULL,
    trade_type    TEXT NOT NULL,
    status        TEXT NOT NULL,
    sell_price    REAL,
    exit_date     TEXT,
    strategy      TEXT,
    notes         TEXT,
    planned_sl    REAL,
    planned_tp    REAL,
    emotion_entry TEXT,
    emotion_exit  TEXT,
    market_cond   TEXT,
    rule_followed TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
)
"""


def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_JOURNAL_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # Re-map snake_case DB columns → camelCase for the frontend
    return {
        "id":              d["id"],
        "stockName":       d["stock_name"],
        "buyPrice":        d["buy_price"],
        "quantity":        d["quantity"],
        "entryDate":       d["entry_date"],
        "capitalUsed":     d["capital_used"],
        "tradeType":       d["trade_type"],
        "status":          d["status"],
        "sellPrice":       d["sell_price"],
        "exitDate":        d["exit_date"],
        "strategy":        d["strategy"],
        "notes":           d["notes"],
        "plannedStopLoss": d["planned_sl"],
        "plannedTarget":   d["planned_tp"],
        "emotionEntry":    d["emotion_entry"],
        "emotionExit":     d["emotion_exit"],
        "marketCondition": d["market_cond"],
        "ruleFollowed":    d["rule_followed"],
        "createdAt":       d["created_at"],
        "updatedAt":       d["updated_at"],
    }


# ── Pydantic models ────────────────────────────────────────────────────────────

class TradeRecord(BaseModel):
    id: str
    stockName: str = Field(..., min_length=1, max_length=40)
    buyPrice: float
    quantity: int
    entryDate: str
    capitalUsed: float
    tradeType: str  # "Swing" | "Investment"
    status: str     # "Open" | "Closed"
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
    trades: list[dict] | None = None  # Frontend passes localStorage trades directly


class JournalChatResponse(BaseModel):
    response: str
    provider: str | None = None
    latency_ms: int | None = None
    trade_count: int = 0


# ── CRUD endpoints ─────────────────────────────────────────────────────────────

@router.get("/trades")
def get_trades():
    """Return all stored journal trades, newest entry date first."""
    conn = _open_db()
    try:
        rows = conn.execute(
            "SELECT * FROM journal_trades ORDER BY entry_date DESC, created_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/trades")
def upsert_trade(body: TradeRecord):
    """Create or update a trade (upserted by id)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _open_db()
    try:
        conn.execute(
            """
            INSERT INTO journal_trades
                (id, stock_name, buy_price, quantity, entry_date, capital_used,
                 trade_type, status, sell_price, exit_date, strategy, notes,
                 planned_sl, planned_tp, emotion_entry, emotion_exit, market_cond,
                 rule_followed, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                stock_name    = excluded.stock_name,
                buy_price     = excluded.buy_price,
                quantity      = excluded.quantity,
                entry_date    = excluded.entry_date,
                capital_used  = excluded.capital_used,
                trade_type    = excluded.trade_type,
                status        = excluded.status,
                sell_price    = excluded.sell_price,
                exit_date     = excluded.exit_date,
                strategy      = excluded.strategy,
                notes         = excluded.notes,
                planned_sl    = excluded.planned_sl,
                planned_tp    = excluded.planned_tp,
                emotion_entry = excluded.emotion_entry,
                emotion_exit  = excluded.emotion_exit,
                market_cond   = excluded.market_cond,
                rule_followed = excluded.rule_followed,
                updated_at    = excluded.updated_at
            """,
            (
                body.id, body.stockName, body.buyPrice, body.quantity,
                body.entryDate, body.capitalUsed, body.tradeType, body.status,
                body.sellPrice, body.exitDate, body.strategy, body.notes,
                body.plannedStopLoss, body.plannedTarget,
                body.emotionEntry, body.emotionExit, body.marketCondition,
                body.ruleFollowed, body.createdAt, now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM journal_trades WHERE id = ?", (body.id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


@router.delete("/trades/{trade_id}")
def delete_trade(trade_id: str):
    """Delete a trade by id."""
    if not trade_id or len(trade_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid trade id")
    conn = _open_db()
    try:
        conn.execute("DELETE FROM journal_trades WHERE id = ?", (trade_id,))
        conn.commit()
        return {"ok": True, "id": trade_id}
    finally:
        conn.close()


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
        return "No trades recorded yet. The user has not logged any trades."
    return "Trade journal data (JSON):\n" + json.dumps(trades, indent=2, ensure_ascii=False, default=str)


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
        json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 1200},
        timeout=6,
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
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
        },
        timeout=7,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _llm(system: str, user_msg: str, history: list[dict] | None = None) -> tuple[str, str, int]:
    preferred = os.getenv("LLM_PROVIDER", "gemini").lower()
    chain = [("gemini", _gemini), ("groq", _groq)] if preferred == "gemini" else [("groq", _groq), ("gemini", _gemini)]
    last_err = ""
    for name, fn in chain:
        try:
            t0 = time.monotonic()
            result = fn(system, user_msg, history)
            ms = int((time.monotonic() - t0) * 1000)
            if result and result.strip():
                return result.strip(), name, ms
        except Exception as exc:
            last_err = f"{name}: {exc}"
    return (
        "Temporary AI issue. Please try again in a moment.",
        f"none:{last_err[:80]}",
        0,
    )


# ── AI chat endpoint ───────────────────────────────────────────────────────────

@router.post("/chat", response_model=JournalChatResponse)
async def journal_chat(body: JournalChatRequest):
    """
    AI coach endpoint. Reads trades from DB (not from request body),
    so the AI always has the full picture regardless of what the frontend sends.
    """
    loop = asyncio.get_running_loop()

    def _fetch_trades_and_chat():
        # Prefer trades passed directly from the frontend (avoids empty /tmp DB on cold start)
        if body.trades:
            trades = body.trades[:200]
        else:
            conn = _open_db()
            try:
                rows = conn.execute(
                    "SELECT * FROM journal_trades ORDER BY entry_date ASC, created_at ASC"
                ).fetchall()
                trades = [_row_to_dict(r) for r in rows]
            finally:
                conn.close()

        trade_ctx = _fmt_trades(trades)
        user_msg = f"{trade_ctx}\n\n---\n\nUser request: {body.message.strip()}"
        history = (body.history or [])[-6:] if body.history else None
        reply, provider, latency_ms = _llm(JOURNAL_SYSTEM_PROMPT, user_msg, history)
        return reply, provider, latency_ms, len(trades)

    try:
        reply, provider, latency_ms, trade_count = await asyncio.wait_for(
            loop.run_in_executor(_executor, _fetch_trades_and_chat),
            timeout=14.0,
        )
    except asyncio.TimeoutError:
        reply = "The analysis timed out. Try asking for one section at a time (e.g. 'Show my Psychology Analysis' or 'What are my critical mistakes?')."
        provider = "timeout"
        latency_ms = 8000
        trade_count = 0

    return JournalChatResponse(
        response=reply,
        provider=provider,
        latency_ms=latency_ms,
        trade_count=trade_count,
    )
