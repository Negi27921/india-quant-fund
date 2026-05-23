"""Watchlist API — CRUD for lists & items + DeepSeek R1 stock analysis."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)

_SB_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_SB_KEY = os.getenv("SUPABASE_KEY", "").strip()
_SAFE_SYMBOL_RE = re.compile(r'^[A-Z0-9&\-\.]{1,20}$')


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_headers() -> dict[str, str]:
    return {
        "apikey": _SB_KEY,
        "Authorization": f"Bearer {_SB_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_get(path: str) -> Any:
    if not (_SB_URL and _SB_KEY):
        raise HTTPException(status_code=503, detail="Supabase credentials not configured")
    req = urllib.request.Request(f"{_SB_URL}/rest/v1/{path}", headers=_sb_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        raise HTTPException(status_code=e.code, detail=f"Supabase: {body[:200]}")


def _sb_post(path: str, body: dict, upsert: bool = False) -> Any:
    if not (_SB_URL and _SB_KEY):
        raise HTTPException(status_code=503, detail="Supabase credentials not configured")
    headers = _sb_headers()
    if upsert:
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{_SB_URL}/rest/v1/{path}", data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = r.read()
            return json.loads(resp) if resp else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        raise HTTPException(status_code=e.code, detail=f"Supabase: {body[:200]}")


def _sb_delete(path: str) -> None:
    if not (_SB_URL and _SB_KEY):
        raise HTTPException(status_code=503, detail="Supabase credentials not configured")
    req = urllib.request.Request(
        f"{_SB_URL}/rest/v1/{path}", headers=_sb_headers(), method="DELETE"
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        raise HTTPException(status_code=e.code, detail=f"Supabase: {body[:200]}")


# ── Pydantic models ───────────────────────────────────────────────────────────

class CreateWatchlistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)
    color: str = Field(default="#a78bfa", max_length=20)


class AddItemRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    ticker: str | None = Field(default=None, max_length=30)
    company: str = Field(default="", max_length=120)
    sector: str = Field(default="", max_length=80)
    industry: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=500)

    @classmethod
    def validate_symbol(cls, v: str) -> str:
        cleaned = v.strip().upper().replace(".NS", "").replace(".BO", "")
        if not _SAFE_SYMBOL_RE.match(cleaned):
            raise ValueError("Invalid symbol")
        return cleaned


class AnalyseRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    question: str = Field(default="Give me a comprehensive analysis.", min_length=1, max_length=1000)
    history: list[dict] | None = None


# ── NIM DeepSeek R1 ───────────────────────────────────────────────────────────

_WL_SYSTEM = """You are the One Piece Quant Analyst — an expert in Indian equity markets (NSE/BSE).
You analyse stocks for Indian retail investors using fundamental data, quarterly results, and technical context.

Rules:
- Be specific with numbers — cite the data provided
- Use **bold** for key metrics and bullet points for structure
- Max 400 words, information-dense
- Flag risks clearly on both sides
- Reference Indian market context (SEBI, NSE/BSE norms, sector dynamics)
- End with "Key Takeaways" (2-3 bullets)
- This is not financial advice
"""


def _nim_analyse(symbol: str, question: str, context: str, history: list[dict] | None) -> str:
    import requests as _req
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        raise ValueError("NVIDIA_API_KEY not set")
    model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-r1").strip()

    user_msg = f"Stock: {symbol}\n\n{context}\n\nQuestion: {question}"
    messages: list[dict] = [{"role": "system", "content": _WL_SYSTEM}]
    if history:
        for turn in history[-6:]:  # keep last 6 turns for context
            messages.append({"role": turn.get("role", "user"), "content": str(turn.get("content", ""))})
    messages.append({"role": "user", "content": user_msg})

    r = _req.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 900, "stream": False},
        timeout=20,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    if "<think>" in content and "</think>" in content:
        after = content.split("</think>", 1)[-1].strip()
        if after:
            content = after
    return content


def _build_stock_context(symbol: str) -> str:
    """Pull quarterly results + basic price context for the AI prompt."""
    lines: list[str] = []

    # Quarterly results from Supabase
    try:
        safe_sym = symbol.upper().replace("'", "")
        rows = _sb_get(
            f"quarterly_results?symbol=eq.{safe_sym}&order=report_date.desc&limit=4&select=*"
        )
        if isinstance(rows, list) and rows:
            lines.append("=== RECENT QUARTERLY RESULTS ===")
            for row in rows:
                m = row.get("metrics") or {}
                rev = m.get("sales") or m.get("revenue") or {}
                pat = m.get("pat") or {}
                eps = m.get("eps") or {}
                rv = rev.get("q3") or rev.get("q1") or 0
                pv = pat.get("q3") or pat.get("q1") or 0
                ev = eps.get("q3") or eps.get("q1") or 0

                def _p(v: Any) -> str:
                    if v is None: return "—"
                    return f"{'+'if float(v)>0 else ''}{float(v):.1f}%"

                lines.append(
                    f"{row.get('quarter','?')} | Revenue: ₹{rv:,.0f}Cr YoY:{_p(rev.get('yoy'))} QoQ:{_p(rev.get('qoq'))}"
                    f" | PAT: ₹{pv:,.0f}Cr YoY:{_p(pat.get('yoy'))} | EPS: ₹{ev:.1f}"
                    f" | Rating: {row.get('rating','?')} | CMP: ₹{row.get('cmp') or '—'}"
                )
                if row.get("insight"):
                    lines.append(f"  AI insight: {row['insight']}")
    except Exception:
        pass

    # Watchlist items metadata (result high, breakout, sector)
    try:
        rows2 = _sb_get(
            f"watchlist_items?symbol=eq.{symbol.upper()}&select=result_date,result_high,breakout_date,result_rating,sector,industry&limit=1"
        )
        if isinstance(rows2, list) and rows2:
            wi = rows2[0]
            parts = [
                f"Result day high: ₹{wi.get('result_high','—')}",
                f"Result date: {wi.get('result_date','—')}",
                f"Breakout: {'Yes on ' + wi['breakout_date'] if wi.get('breakout_date') else 'Not yet'}",
            ]
            if wi.get("sector"):
                parts.append(f"Sector: {wi['sector']}")
            if wi.get("industry"):
                parts.append(f"Industry: {wi['industry']}")
            lines.append("\n" + " | ".join(parts))
    except Exception:
        pass

    # Universe data (sector, market cap, exchange)
    try:
        rows3 = _sb_get(
            f"stock_universe?symbol=eq.{symbol.upper()}&select=sector,industry,market_cap_cr,exchange,last_price&limit=1"
        )
        if isinstance(rows3, list) and rows3:
            u = rows3[0]
            lines.append(
                f"Universe: {u.get('exchange','—')} | Sector: {u.get('sector','—')} | "
                f"Industry: {u.get('industry','—')} | Market Cap: ₹{u.get('market_cap_cr',0):,.0f} Cr"
            )
    except Exception:
        pass

    return "\n".join(lines) if lines else "No historical data available for this stock."


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def watchlist_health() -> dict:
    """Quick DB connectivity check — useful for diagnosing blank watchlist page."""
    if not (_SB_URL and _SB_KEY):
        return {"ok": False, "error": "SUPABASE_URL or SUPABASE_KEY not set in env"}
    try:
        rows = _sb_get("watchlists?select=id,name,type&order=created_at.asc")
        return {
            "ok":         True,
            "watchlists": len(rows) if isinstance(rows, list) else 0,
            "names":      [r.get("name") for r in rows] if isinstance(rows, list) else [],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("")
async def list_watchlists() -> list[dict]:
    """List all watchlists ordered by created_at."""
    rows = _sb_get("watchlists?order=created_at.asc&select=*")
    return rows if isinstance(rows, list) else []


@router.post("")
async def create_watchlist(body: CreateWatchlistRequest) -> dict:
    """Create a new manual watchlist."""
    try:
        result = _sb_post("watchlists", {
            "name": body.name,
            "description": body.description,
            "color": body.color,
            "type": "manual",
        })
        rows = result if isinstance(result, list) else [result]
        return rows[0] if rows else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{watchlist_id}")
async def delete_watchlist(watchlist_id: str) -> dict:
    """Delete a watchlist (not allowed for auto_results or quarterly_results types)."""
    AUTO_WL_ID = "aaaaaaaa-0000-0000-0000-000000000001"
    if watchlist_id == AUTO_WL_ID:
        raise HTTPException(status_code=403, detail="Cannot delete auto-results watchlist")
    try:
        rows = _sb_get(f"watchlists?id=eq.{watchlist_id}&select=type&limit=1")
        if isinstance(rows, list) and rows:
            wl_type = rows[0].get("type", "manual")
            if wl_type in ("auto_results", "quarterly_results"):
                raise HTTPException(status_code=403, detail=f"Cannot delete {wl_type} watchlist")
        _sb_delete(f"watchlists?id=eq.{watchlist_id}")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{watchlist_id}/items")
async def get_watchlist_items(watchlist_id: str) -> list[dict]:
    """Get all stocks in a watchlist."""
    try:
        rows = _sb_get(
            f"watchlist_items?watchlist_id=eq.{watchlist_id}"
            f"&order=added_at.desc&select=*"
        )
        return rows if isinstance(rows, list) else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{watchlist_id}/items")
async def add_watchlist_item(watchlist_id: str, body: AddItemRequest) -> dict:
    """Add a stock to a watchlist."""
    symbol = body.symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    if not _SAFE_SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol")
    try:
        result = _sb_post(
            "watchlist_items",
            {
                "watchlist_id": watchlist_id,
                "symbol": symbol,
                "ticker": body.ticker or f"{symbol}.NS",
                "company": body.company,
                "sector": body.sector,
                "industry": body.industry,
                "notes": body.notes,
                "added_reason": "manual",
            },
            upsert=True,
        )
        rows = result if isinstance(result, list) else [result]
        return rows[0] if rows else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{watchlist_id}/items/{symbol}")
async def remove_watchlist_item(watchlist_id: str, symbol: str) -> dict:
    """Remove a stock from a watchlist."""
    safe = symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    try:
        _sb_delete(f"watchlist_items?watchlist_id=eq.{watchlist_id}&symbol=eq.{safe}")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyse")
async def analyse_stock(body: AnalyseRequest) -> dict:
    """AI analysis for a stock using NVIDIA NIM DeepSeek R1."""
    import asyncio
    symbol = body.symbol.strip().upper().replace(".NS", "").replace(".BO", "")
    if not _SAFE_SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol")

    loop = asyncio.get_event_loop()

    context = await loop.run_in_executor(_executor, _build_stock_context, symbol)

    try:
        reply = await loop.run_in_executor(
            _executor, _nim_analyse, symbol, body.question, context, body.history
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI error: {e}")

    return {"symbol": symbol, "response": reply, "provider": "nvidia-nim/deepseek-r1"}
