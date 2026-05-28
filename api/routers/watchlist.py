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

    # ── 1. Groq — llama-3.3-70b-versatile (fastest, ~1s) ────────────────────
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

    # ── 2. NVIDIA NIM — Nemotron 49B ─────────────────────────────────────────
    nim_key = os.getenv("NVIDIA_API_KEY", "").strip()
    nim_model = os.getenv("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1").strip()
    if nim_key:
        try:
            raw = _openai_compat_call(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                nim_key, nim_model, messages, timeout=35,
            )
            return _strip_think(raw)
        except Exception as exc:
            errors.append(f"NIM({nim_model}): {exc}")

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


def _screener_quick(symbol: str) -> dict[str, str]:
    """Scrape key ratios from screener.in. Blocking, max 4s."""
    url = f"https://www.screener.in/company/{symbol}/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            if r.status != 200:
                return {}
            body = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}

    idx = body.find("Market Cap")
    if idx < 0:
        return {}
    snippet = body[max(0, idx - 100): idx + 3000]
    text = re.sub(r"<[^>]+>", " ", snippet)
    text = re.sub(r"\s+", " ", text).strip()

    result: dict[str, str] = {}
    for metric in ("Market Cap", "Stock P/E", "Book Value", "Dividend Yield", "ROCE", "ROE", "Debt to equity", "Current ratio"):
        m = re.search(re.escape(metric) + r"\s*[₹%]?\s*([\d,\.]+\s*(?:Cr\.?|%|x)?)", text, re.IGNORECASE)
        if m:
            result[metric] = m.group(1).strip()
    for label, regex in [
        ("Promoter %", r"Promoter\s+Holding.*?([\d\.]+\s*%)"),
        ("FII %",      r"FII\s+Holding.*?([\d\.]+\s*%)"),
        ("DII %",      r"DII\s+Holding.*?([\d\.]+\s*%)"),
    ]:
        m = re.search(regex, body[:80000], re.IGNORECASE | re.DOTALL)
        if m:
            result[label] = m.group(1).strip()
    return result


def _build_stock_context(symbol: str) -> str:
    """
    Build LLM context from vw_stock_snapshot (unified read model) + technicals + news.
    vw_stock_snapshot = dim_company + fact_market_realtime + fact_screener_fundamentals.
    AI agents must consume ONLY this unified view — never query underlying tables directly.
    """
    lines: list[str] = [f"=== STOCK: {symbol} ==="]
    sym = symbol.upper()

    # 1. vw_stock_snapshot — single truth source (identity + live price + fundamentals + shareholding)
    try:
        snap_rows = _sb_get(f"vw_stock_snapshot?symbol=eq.{sym}&limit=1")
        if isinstance(snap_rows, list) and snap_rows:
            s = snap_rows[0]
            # Identity
            lines.append("\n--- COMPANY ---")
            lines.append(
                f"Name: {s.get('company_name','—')} | Sector: {s.get('sector','—')} | "
                f"Industry: {s.get('industry','—')} | Cap tier: {s.get('marketcap_category','—')}"
            )
            # Live market state
            cmp = s.get("ltp") or s.get("cmp")
            pct = s.get("pct_change")
            mc  = s.get("market_cap_cr")
            lines.append(f"\n--- MARKET STATE (price freshness: {s.get('price_freshness','unknown')}) ---")
            if cmp:
                chg_str = f"  Change: {float(pct):+.2f}%" if pct is not None else ""
                lines.append(f"CMP: ₹{float(cmp):,.2f}{chg_str}")
            if s.get("vwap"):
                lines.append(f"VWAP: ₹{float(s['vwap']):,.2f}  Volume: {s.get('volume','—')}")
            if s.get("day_open"):
                lines.append(
                    f"Open: ₹{s['day_open']}  High: ₹{s.get('day_high','—')}  Low: ₹{s.get('day_low','—')}"
                )
            if mc:
                lines.append(f"Live Market Cap: ₹{float(mc):,.0f} Cr")
            h52 = s.get("best_52w_high")
            l52 = s.get("best_52w_low")
            if h52 or l52:
                lines.append(
                    f"52W High: ₹{h52 or '—'}  52W Low: ₹{l52 or '—'}  "
                    f"From 52W High: {s.get('pct_from_52w_high','—')}%"
                )
            # Fundamentals
            lines.append(f"\n--- FUNDAMENTALS (freshness: {s.get('fundamentals_freshness','unknown')}) ---")
            for label, key, unit in [
                ("P/E (live)",    "live_pe",           "x"),
                ("ROCE",          "roce_pct",          "%"),
                ("ROE",           "roe_pct",           "%"),
                ("Debt/Equity",   "debt_to_equity",    "x"),
                ("Current Ratio", "current_ratio",     "x"),
                ("Book Value",    "book_value",        "₹"),
                ("EPS TTM",       "eps_ttm",           "₹"),
                ("Sales TTM",     "sales_ttm_cr",      "Cr"),
                ("Profit TTM",    "profit_ttm_cr",     "Cr"),
                ("Div Yield",     "dividend_yield_pct","%"),
            ]:
                val = s.get(key)
                if val is not None:
                    lines.append(f"{label}: {val} {unit}")
            # Shareholding
            promoter = s.get("promoter_pct")
            pledge   = s.get("promoter_pledge_pct")
            if promoter is not None:
                lines.append("\n--- SHAREHOLDING ---")
                pledge_str = f" (pledged: {pledge}% ⚠)" if pledge and float(pledge) > 5 else ""
                lines.append(f"Promoter: {promoter}%{pledge_str}")
                for lbl, k in [("FII", "fii_pct"), ("DII", "dii_pct"), ("Public", "public_pct")]:
                    if s.get(k) is not None:
                        lines.append(f"{lbl}: {s[k]}%")
                if pledge and float(pledge) > 20:
                    lines.append("⚠ HIGH PROMOTER PLEDGE — elevated balance-sheet risk")
        else:
            # vw_stock_snapshot miss — fallback to dim_company only
            co_rows = _sb_get(
                f"dim_company?ticker=eq.{sym}&select=company_name,sector,industry,"
                f"marketcap_category,market_cap_inr_cr,current_price_inr,high_52w_inr,low_52w_inr&limit=1"
            )
            if isinstance(co_rows, list) and co_rows:
                co = co_rows[0]
                lines.append(f"\n--- COMPANY (dim_company fallback) ---")
                lines.append(
                    f"Name: {co.get('company_name','—')} | Sector: {co.get('sector','—')} | "
                    f"Industry: {co.get('industry','—')}"
                )
                if co.get("market_cap_inr_cr"):
                    lines.append(f"Market Cap: ₹{float(co['market_cap_inr_cr']):,.0f} Cr")
    except Exception:
        pass

    # 2. Technicals (fact_technicals — latest row)
    try:
        t_rows = _sb_get(
            f"fact_technicals?ticker=eq.{sym}&select=date,close,open,high,low,volume,"
            f"rsi_14,macd,macd_signal,sma_20,sma_50,sma_200,ema_20,bb_upper,bb_lower,atr_14,"
            f"pct_change_1d,pct_change_5d,pct_change_20d,high_52w,low_52w,pct_from_52w_high,"
            f"rel_volume&order=date.desc&limit=1"
        )
        if isinstance(t_rows, list) and t_rows:
            t = t_rows[0]
            lines.append(f"\n--- TECHNICALS ({t.get('date','?')}) ---")
            lines.append(
                f"Price: ₹{t.get('close','—')} | RSI(14): {t.get('rsi_14','—')} | "
                f"MACD: {t.get('macd','—')} / Signal: {t.get('macd_signal','—')}"
            )
            lines.append(
                f"SMA20: {t.get('sma_20','—')} | SMA50: {t.get('sma_50','—')} | SMA200: {t.get('sma_200','—')}"
            )
            lines.append(
                f"BB Upper: {t.get('bb_upper','—')} | BB Lower: {t.get('bb_lower','—')} | ATR(14): {t.get('atr_14','—')}"
            )
            lines.append(
                f"52W High: {t.get('high_52w','—')} | 52W Low: {t.get('low_52w','—')} | "
                f"From 52W High: {t.get('pct_from_52w_high','—')}%"
            )
            lines.append(
                f"1D: {t.get('pct_change_1d','—')}% | 5D: {t.get('pct_change_5d','—')}% | "
                f"20D: {t.get('pct_change_20d','—')}% | Rel Volume: {t.get('rel_volume','—')}x"
            )
    except Exception:
        pass

    # 4. AI-tagged announcements (last 6)
    try:
        ann_rows = _sb_get(
            f"fact_announcements_tagged?ticker=eq.{sym}&select=announcement_type,sentiment,"
            f"summary_header,summary_text,published_date&order=published_date.desc&limit=6"
        )
        if isinstance(ann_rows, list) and ann_rows:
            lines.append("\n--- RECENT ANNOUNCEMENTS (AI-tagged) ---")
            sent_map = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
            for a in ann_rows:
                em = sent_map.get(a.get("sentiment", ""), "")
                lines.append(
                    f"{em} [{str(a.get('published_date',''))[:10]}] "
                    f"{a.get('announcement_type','')} — {a.get('summary_header','')}"
                )
                if a.get("summary_text"):
                    lines.append(f"   {str(a['summary_text'])[:200]}")
    except Exception:
        pass

    # 5. Results calendar (next 3 events)
    try:
        cal_rows = _sb_get(
            f"fact_results_calendar?ticker=eq.{sym}&select=result_date,fiscal_year,"
            f"fiscal_quarter,result_type&order=result_date.asc&limit=3"
        )
        if isinstance(cal_rows, list) and cal_rows:
            lines.append("\n--- RESULTS CALENDAR ---")
            for r in cal_rows:
                lines.append(
                    f"Q{r.get('fiscal_quarter','?')} FY{r.get('fiscal_year','?')}: "
                    f"{r.get('result_date','TBD')} ({r.get('result_type','')})"
                )
    except Exception:
        pass

    # Note: live NSE price removed — vw_stock_snapshot (step 1) already provides
    # ltp, pct_change, volume, vwap from fact_market_realtime. No external call needed.

    return "\n".join(lines) if len(lines) > 1 else f"No data found for {symbol}."


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/universe/search")
async def universe_search(q: str = "", limit: int = 40) -> list[dict]:
    """
    Search dim_company (canonical universe ≥₹1,000Cr) for the stock picker.
    Returns {symbol, company, sector, industry} sorted by market cap desc.
    q="" returns top-N stocks by market cap.
    """
    import urllib.parse as _up
    if not (_SB_URL and _SB_KEY):
        return []
    try:
        q_clean = q.strip().upper()
        cap = min(limit, 80)
        base_filters = "&market_cap_inr_cr=gte.1000&ticker=not.is.null"
        if q_clean:
            # Use %25 as URL-encoded % wildcard for PostgREST ilike
            q_enc = _up.quote(q.strip(), safe="")
            q_ticker = _up.quote(q_clean, safe="")
            path = (
                f"dim_company?select=ticker,company_name,sector,industry,market_cap_inr_cr"
                f"&or=(ticker.ilike.{q_ticker}%25,company_name.ilike.%25{q_enc}%25)"
                f"{base_filters}"
                f"&order=market_cap_inr_cr.desc.nullslast&limit={cap}"
            )
        else:
            path = (
                f"dim_company?select=ticker,company_name,sector,industry,market_cap_inr_cr"
                f"{base_filters}"
                f"&order=market_cap_inr_cr.desc.nullslast&limit={cap}"
            )
        rows = _sb_get(path)
        if not isinstance(rows, list):
            return []
        return [
            {
                "symbol":   r["ticker"],
                "company":  r.get("company_name", ""),
                "sector":   r.get("sector", ""),
                "industry": r.get("industry", ""),
            }
            for r in rows
            if r.get("ticker")
        ]
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

    Universe watchlist (type='universe'): returns ALL stocks from dim_company
    (5,400+ rows) — bypasses watchlist_items table entirely.

    Manual/auto watchlists: reads from watchlist_items with Range pagination.
    """
    try:
        # Detect watchlist type first
        wl_type = "manual"
        try:
            wl_rows = _sb_get(f"watchlists?id=eq.{watchlist_id}&select=type&limit=1")
            if isinstance(wl_rows, list) and wl_rows:
                wl_type = wl_rows[0].get("type", "manual")
        except Exception:
            pass

        # ── Universe watchlist: canonical dim_company universe (market_cap >= 1000 Cr) ─
        if wl_type == "universe":
            dc_rows = _sb_get_all(
                "dim_company?select=ticker,company_name,sector,industry,"
                "basic_industry,macro_sector,marketcap_category,"
                "market_cap_inr_cr,current_price_inr,high_52w_inr,low_52w_inr"
                "&market_cap_inr_cr=gte.1000"
                "&order=market_cap_inr_cr.desc.nullslast"
            )
            now_iso = __import__("datetime").datetime.utcnow().isoformat() + "Z"
            items = []
            for r in (dc_rows if isinstance(dc_rows, list) else []):
                t = (r.get("ticker") or "").strip()
                if not t:
                    continue
                items.append({
                    "id":                   f"universe-{t}",
                    "watchlist_id":         watchlist_id,
                    "symbol":               t,
                    "ticker":               t,
                    "company":              r.get("company_name") or t,
                    "sector":               r.get("sector") or r.get("macro_sector") or "",
                    "industry":             r.get("industry") or r.get("basic_industry") or "",
                    "marketcap_category":   r.get("marketcap_category") or "",
                    "market_cap_cr":        r.get("market_cap_inr_cr"),
                    "current_price":        r.get("current_price_inr"),
                    "high_52w":             r.get("high_52w_inr"),
                    "low_52w":              r.get("low_52w_inr"),
                    "added_at":             now_iso,
                    "added_reason":         "universe",
                    "result_date":          None,
                    "result_high":          None,
                    "result_volume_avg":    None,
                    "result_rating":        None,
                    "breakout_alerted":     False,
                    "breakout_date":        None,
                    "notes":                "",
                })
            return items

        # ── Manual / auto watchlist: read from watchlist_items ────────────────
        rows = _sb_get_all(
            f"watchlist_items?watchlist_id=eq.{watchlist_id}&order=added_at.desc&select=*"
        )
        if not isinstance(rows, list):
            return []

        # Enrich sector/industry from dim_company for items that have empty values
        missing_sector = [r["symbol"] for r in rows
                          if not r.get("sector") and not r.get("industry")
                          and r.get("symbol")]
        if missing_sector:
            sector_map: dict[str, dict] = {}
            for i in range(0, len(missing_sector), 200):
                chunk = missing_sector[i: i + 200]
                sym_filter = ",".join(chunk)
                try:
                    dc = _sb_get(
                        f"dim_company?ticker=in.({sym_filter})"
                        f"&select=ticker,sector,industry&limit=200"
                    )
                    for u in (dc if isinstance(dc, list) else []):
                        sector_map[u["ticker"]] = u
                except Exception:
                    pass
            for r in rows:
                sym = r.get("symbol", "")
                if sym in sector_map and not r.get("sector"):
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
