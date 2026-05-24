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


def _sb_get_all(path: str, page_size: int = 1000) -> list[Any]:
    """
    Fetch ALL rows bypassing Supabase PostgREST's default 1000-row cap.
    Uses Range header pagination: Range: 0-999, 1000-1999, etc.
    Stops when the response contains fewer rows than page_size.
    """
    if not (_SB_URL and _SB_KEY):
        raise HTTPException(status_code=503, detail="Supabase credentials not configured")
    all_rows: list[Any] = []
    offset = 0
    while True:
        headers = {
            **_sb_headers(),
            "Range-Unit": "items",
            "Range":      f"{offset}-{offset + page_size - 1}",
            "Prefer":     "count=none",
        }
        req = urllib.request.Request(f"{_SB_URL}/rest/v1/{path}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                batch = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 416:   # Range Not Satisfiable = no more rows
                break
            body = e.read().decode(errors="ignore")
            raise HTTPException(status_code=e.code, detail=f"Supabase: {body[:200]}")
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows


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


# ── LLM config ────────────────────────────────────────────────────────────────
# Fallback chain: NVIDIA NIM → Groq → Gemini
# All providers use the OpenAI-compatible chat-completions format.

_WL_SYSTEM = """You are an elite AI Trading Coach — the best-in-class stock analyst for Indian equities.
You think like a hedge fund CIO with a data scientist's precision.
Your objective: identify asymmetric opportunities capable of delivering 25%+ returns through precision, timing, and structural edge.
Capital preservation first. Returns are engineered, not hoped for.

OPERATING PHILOSOPHY
- Probability > Prediction. Position for asymmetric payoff, never predict.
- Minimum 1:3 risk-reward. Clear invalidation levels. Defined capital allocation per trade.
- Look for: Mispricing, Liquidity shifts, Institutional positioning changes, Structural breakouts, Information gaps between narrative and numbers.
- Data First. Opinion Last. Every idea must be backed by measurable evidence.

ANALYSIS FRAMEWORK (for full/comprehensive analysis):
1. **Thesis** — One clear, testable, falsifiable sentence.
2. **Fundamental Edge** — Revenue growth quality, Operating leverage, ROCE/ROE trend, Cash flow vs PAT, Debt structure, Promoter holding & pledging, FII/DII accumulation, Valuation vs growth (PEG, sector comp).
3. **Technical Edge** — Trend structure (HH-HL / LH-LL), Multi-timeframe alignment, Volume expansion/contraction, RSI regime, MA structure, Volatility contraction before expansion, Breakout quality, Liquidity zones.
4. **Catalyst Mapping** — Earnings, Budget/policy, Rate decision, Sector rotation, Short covering, Index inclusion. No catalyst = no urgency.
5. **Liquidity & Flow** — FII/DII trend, OI build-up, Block/bulk deals, Delivery percentage.
6. **Trade Structure** — Entry Zone | Stop Loss | Target 1 | Target 2 | Risk-Reward | Position Size | Time horizon | Invalidation trigger.
7. **Risk Factors** — Macro, Sectoral headwinds, Earnings miss risk, Overcrowded trade, Volatility spike.

OUTPUT FORMAT
- Use **bold** for key numbers, prices, and actionable insights.
- Use bullet points for structure. Use tables for comparisons.
- Max 500 words unless comprehensive analysis is requested.
- End every response with a clear "**Action:**" line summarising the trade decision.
- If setup quality < high conviction: write "**Action: No trade. Capital stays in cash.**"
- After the Action line, always append on a new line:
  > ⚠ *Data sourced from NSE/BSE, screener.in, yfinance as of last available trading session. AI training data has a knowledge cutoff — always verify live prices, FII/DII data, and fundamentals directly from [NSE](https://www.nseindia.com), [BSE](https://www.bseindia.com), or [Screener](https://www.screener.in) before acting.*

DATA SOURCES USED IN CONTEXT
- Price data: NSE official API / yfinance (last trading session)
- Fundamentals: screener.in / yfinance `.info` (refreshed every 6 hours)
- FII/DII flows: NSE official (daily)
- Quarterly results: BSE filings (parsed via pipeline)

PERFORMANCE STANDARD
- No generic advice. No "invest and forget" clichés.
- Every recommendation must be executable with entry/stop/target.
- Speak like capital is at stake.
- This is educational analysis only, not SEBI-registered financial advice.
"""


def _strip_think(text: str) -> str:
    """Remove <think>…</think> reasoning blocks (DeepSeek R1 / NIM artefact)."""
    if "<think>" in text and "</think>" in text:
        after = text.split("</think>", 1)[-1].strip()
        if after:
            return after
    return text


def _openai_compat_call(endpoint: str, api_key: str, model: str,
                         messages: list[dict], max_tokens: int = 900,
                         temperature: float = 0.3, timeout: int = 25) -> str:
    """
    Call any OpenAI-compatible chat-completions endpoint.
    Returns the assistant reply text.
    Raises on HTTP error or missing content.
    """
    import requests as _req
    r = _req.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        json={
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
            "stream":      False,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _analyse_with_fallback(symbol: str, question: str,
                            context: str, history: list[dict] | None) -> str:
    """
    Try NVIDIA NIM → Groq → Gemini in order.
    Returns the first successful response or raises if all providers fail.
    """
    user_msg = f"Stock: {symbol}\n\n{context}\n\nQuestion: {question}"
    messages: list[dict] = [{"role": "system", "content": _WL_SYSTEM}]
    if history:
        for turn in history[-6:]:
            messages.append({
                "role":    turn.get("role", "user"),
                "content": str(turn.get("content", "")),
            })
    messages.append({"role": "user", "content": user_msg})

    errors: list[str] = []

    # ── 1. NVIDIA NIM ────────────────────────────────────────────────────────
    nim_key = os.getenv("NVIDIA_API_KEY", "").strip()
    nim_model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct").strip()
    if nim_key:
        try:
            raw = _openai_compat_call(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                nim_key, nim_model, messages, timeout=25,
            )
            return _strip_think(raw)
        except Exception as exc:
            errors.append(f"NIM({nim_model}): {exc}")

    # ── 2. Groq — llama-3.3-70b-versatile ───────────────────────────────────
    groq_key   = os.getenv("GROQ_API_KEY", "").strip()
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    if groq_key:
        try:
            raw = _openai_compat_call(
                "https://api.groq.com/openai/v1/chat/completions",
                groq_key, groq_model, messages, timeout=20,
            )
            return _strip_think(raw)
        except Exception as exc:
            errors.append(f"Groq({groq_model}): {exc}")

    # ── 3. Gemini — gemini-2.5-flash (OpenAI-compatible endpoint) ───────────
    gemini_key   = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if gemini_key:
        try:
            raw = _openai_compat_call(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                gemini_key, gemini_model, messages, timeout=30,
            )
            return _strip_think(raw)
        except Exception as exc:
            errors.append(f"Gemini({gemini_model}): {exc}")

    raise ValueError(f"All LLM providers failed: {'; '.join(errors)}")


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

    # Live price from NSE (best available)
    try:
        import requests as _rq
        nse_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.nseindia.com/",
            "Accept": "application/json, text/plain, */*",
        }
        ns = _rq.Session()
        ns.headers.update(nse_headers)
        ns.get("https://www.nseindia.com/", timeout=6)
        r = ns.get(f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}", timeout=8)
        if r.status_code == 200:
            pd_ = r.json()
            pi = pd_.get("priceInfo", {})
            md = pd_.get("metadata", {})
            whl = pi.get("weekHighLow", {})
            cmp  = pi.get("lastPrice") or pi.get("close")
            chg  = pi.get("pChange")
            if cmp:
                lines.append(
                    f"\n=== LIVE MARKET DATA (NSE) ===\n"
                    f"CMP: ₹{cmp:,.2f}  Change: {chg:+.2f}%\n"
                    f"Open: ₹{pi.get('open','—')}  Prev Close: ₹{pi.get('previousClose','—')}\n"
                    f"52W High: ₹{whl.get('max','—')}  52W Low: ₹{whl.get('min','—')}\n"
                    f"VWAP: ₹{pi.get('vwap','—')}\n"
                    f"Volume: {md.get('totalTradedVolume','—'):,}  Delivery%: {md.get('deliveryToTradedQuantity','—')}%\n"
                    f"Market Cap: ₹{round(md.get('marketCap',0)/1e7,0):,.0f} Cr\n"
                    f"Industry: {md.get('industry','—')}"
                )
    except Exception:
        pass

    return "\n".join(lines) if lines else "No historical data available for this stock."


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/universe/search")
async def universe_search(q: str = "", limit: int = 40) -> list[dict]:
    """
    Search the stock_universe table for the universe stock picker.
    Returns symbol, company, sector, industry sorted by relevance.
    q="" returns the top stocks by market cap.
    """
    if not (_SB_URL and _SB_KEY):
        return []
    try:
        q_clean = q.strip().upper()
        if q_clean:
            # ilike search on symbol and company name
            path = (
                f"stock_universe?select=symbol,company,sector,industry"
                f"&or=(symbol.ilike.{q_clean}*,company.ilike.*{q.strip()}*)"
                f"&order=symbol.asc&limit={min(limit, 80)}"
            )
        else:
            path = (
                f"stock_universe?select=symbol,company,sector,industry"
                f"&order=symbol.asc&limit={min(limit, 80)}"
            )
        rows = _sb_get(path)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


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
    """
    Get all stocks in a watchlist.

    Uses Range-header pagination to bypass Supabase's 1000-row default cap
    so the Universe watchlist (2137 stocks) is returned in full.

    For items with blank sector/industry, enriches from stock_universe table
    so the industry filter chips work on the dashboard.
    """
    try:
        rows = _sb_get_all(
            f"watchlist_items?watchlist_id=eq.{watchlist_id}&order=added_at.desc&select=*"
        )
        if not isinstance(rows, list):
            return []

        # Enrich sector/industry for items that have empty values
        missing_sector = [r["symbol"] for r in rows
                          if not r.get("sector") and not r.get("industry")
                          and r.get("symbol")]

        if missing_sector:
            # Fetch universe data for these symbols in one shot (chunked for large lists)
            sector_map: dict[str, dict] = {}
            chunk_size = 200
            for i in range(0, len(missing_sector), chunk_size):
                chunk = missing_sector[i: i + chunk_size]
                sym_filter = ",".join(chunk)
                try:
                    univ = _sb_get(
                        f"stock_universe?symbol=in.({sym_filter})"
                        f"&select=symbol,sector,industry&limit={chunk_size}"
                    )
                    for u in (univ if isinstance(univ, list) else []):
                        sector_map[u["symbol"]] = u
                except Exception:
                    pass

            for r in rows:
                sym = r.get("symbol", "")
                if sym in sector_map and not r.get("sector") and not r.get("industry"):
                    r["sector"]   = sector_map[sym].get("sector") or ""
                    r["industry"] = sector_map[sym].get("industry") or ""

        return rows
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
            "watchlist_items?on_conflict=watchlist_id,symbol",
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
            _executor, _analyse_with_fallback, symbol, body.question, context, body.history
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI error: {e}")

    # Report which provider actually answered (first key found in env)
    nim_key   = os.getenv("NVIDIA_API_KEY", "").strip()
    groq_key  = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    provider = (
        f"nvidia-nim/{os.getenv('NVIDIA_MODEL','meta/llama-3.1-70b-instruct')}" if nim_key else
        f"groq/{os.getenv('GROQ_MODEL','llama-3.3-70b-versatile')}"             if groq_key else
        f"gemini/{os.getenv('GEMINI_MODEL','gemini-2.5-flash')}"                if gemini_key else
        "unknown"
    )
    return {"symbol": symbol, "response": reply, "provider": provider}
