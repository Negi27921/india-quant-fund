"""AI Chat — stock research assistant with rich Supabase + screener.in context."""
from __future__ import annotations

import asyncio
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from api.middleware.security import rate_limit_chat, require_internal_key

router = APIRouter()

_SAFE_SYMBOL_RE = re.compile(r'^[A-Z0-9&\-]{1,20}$')
_executor = ThreadPoolExecutor(max_workers=6)

PRESET_QUESTIONS = [
    {"id": "full_analysis",    "label": "Full analysis",        "prompt": "Give a complete investment analysis including fundamentals, technicals, recent news, FII/DII activity, and key risks."},
    {"id": "entry_targets",    "label": "Entry & targets",      "prompt": "Suggest optimal entry zones, price targets (1 month, 3 months, 12 months), and stop-loss levels based on technicals and fundamentals."},
    {"id": "fii_dii",          "label": "FII/DII flow",         "prompt": "Analyse FII and DII activity for this stock and sector. What is the smart money doing and what does it signal?"},
    {"id": "catalyst",         "label": "Near-term catalyst",   "prompt": "What are the upcoming catalysts for this stock? Include earnings dates, corporate actions, product launches, regulatory events, and macro triggers."},
    {"id": "breakout",         "label": "Breakout level",       "prompt": "Identify key technical breakout and breakdown levels, resistance/support zones, and volume confirmation requirements."},
    {"id": "risks",            "label": "Key risks",            "prompt": "What are the top 5 risks for this stock? Include sector risks, company-specific risks, regulatory risks, and macro headwinds."},
    {"id": "quarterly",        "label": "Quarterly results",    "prompt": "Analyse the latest quarterly results. How did revenue, PAT, and margins compare to estimates and last year? What did management say on the concall?"},
    {"id": "compare_sector",   "label": "Sector comparison",    "prompt": "How does this company compare to its top 3 sector peers on P/E, ROE, growth, and debt? Is it a sector leader or laggard?"},
]

SYSTEM_PROMPT = """You are the One Piece Market Intelligence — a world-class AI analyst for Indian equities (NSE & BSE).

You have access to live market data, fundamentals, technicals, and recent filings for the stock being discussed.

Rules:
- Be specific — cite exact numbers from the data provided. Don't say "moderate P/E" when you have the number.
- Structure every response: use **bold** for key metrics, bullet points for lists, clear section headers.
- Flag risks clearly. Don't be a bull shill. Present both bull and bear case.
- Keep it tight — max 400 words. Information-dense, not padded.
- End with 2-3 **Key Takeaways** as bullet points.
- Never give direct buy/sell advice. Frame as analysis, not recommendation.
- Add "Not financial advice" once at the end, briefly.
- Reference Indian market context: SEBI norms, NSE/BSE, India VIX, FII/DII flows, sector rotations.
- For technical levels, cite specific price numbers from the data.
- When earnings data is available, comment on beat/miss vs estimates and QoQ/YoY trends.
"""


# ---------------------------------------------------------------------------
# Screener.in scraper — fundamentals
# ---------------------------------------------------------------------------

_SCREENER_METRICS = [
    "Market Cap", "Current Price", "High / Low", "Stock P/E",
    "Book Value", "Dividend Yield", "ROCE", "ROE",
    "Face Value", "EPS", "Debt to equity", "Current ratio",
]


def _scrape_screener(symbol: str) -> dict[str, str]:
    """Fetch key ratios from screener.in. Returns dict of metric→value. Blocking."""
    url = f"https://www.screener.in/company/{symbol}/"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            if r.status != 200:
                return {}
            body = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}

    # Extract the ratios section (appears once, near top)
    idx = body.find("Market Cap")
    if idx < 0:
        return {}
    snippet = body[max(0, idx - 100): idx + 3000]
    text = re.sub(r"<[^>]+>", " ", snippet)
    text = re.sub(r"\s+", " ", text).strip()

    result: dict[str, str] = {}
    for metric in _SCREENER_METRICS:
        pattern = re.escape(metric) + r"\s*[₹%]?\s*([\d,\.]+\s*(?:Cr\.?|%|x)?)"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result[metric] = m.group(1).strip()

    # Also grab quarterly revenue/PAT if present
    for label, regex in [
        ("Sales TTM",   r"Sales\s+TTM.*?([\d,\.]+)"),
        ("Profit TTM",  r"Profit\s+after\s+tax.*?TTM.*?([\d,\.]+)"),
        ("Promoter %",  r"Promoter\s+Holding.*?([\d\.]+\s*%)"),
        ("FII %",       r"FII\s+Holding.*?([\d\.]+\s*%)"),
        ("DII %",       r"DII\s+Holding.*?([\d\.]+\s*%)"),
    ]:
        m = re.search(regex, body[:100000], re.IGNORECASE | re.DOTALL)
        if m:
            result[label] = m.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Supabase context — rich data from our tables
# ---------------------------------------------------------------------------

def _get_supabase_context(symbol: str) -> dict[str, Any]:
    """Pull company, technicals, recent announcements, results calendar from Supabase."""
    try:
        from supabase import create_client
        from core.config import settings
        sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

        ctx: dict[str, Any] = {}

        # 1. Company master
        c = sb.table("dim_company").select(
            "company_name,sector,industry,marketcap_category,market_cap_inr_cr,"
            "current_price_inr,high_52w_inr,low_52w_inr"
        ).eq("ticker", symbol).limit(1).execute()
        if c.data:
            ctx["company"] = c.data[0]

        # 2. Latest technicals
        t = sb.table("fact_technicals").select(
            "date,close,open,high,low,volume,rsi_14,macd,macd_signal,"
            "sma_20,sma_50,sma_200,ema_20,bb_upper,bb_lower,atr_14,"
            "pct_change_1d,pct_change_5d,pct_change_20d,"
            "high_52w,low_52w,pct_from_52w_high,rel_volume"
        ).eq("ticker", symbol).order("date", desc=True).limit(1).execute()
        if t.data:
            ctx["technicals"] = t.data[0]

        # 3. Recent AI-tagged announcements (last 6)
        a = sb.table("fact_announcements_tagged").select(
            "announcement_type,sentiment,summary_header,summary_text,published_date"
        ).eq("ticker", symbol).order("published_date", desc=True).limit(6).execute()
        if a.data:
            ctx["announcements"] = a.data

        # 4. Results calendar
        cal = sb.table("fact_results_calendar").select(
            "result_date,fiscal_year,fiscal_quarter,result_type"
        ).eq("ticker", symbol).order("result_date", desc=False).limit(3).execute()
        if cal.data:
            ctx["calendar"] = cal.data

        # 5. Screener.in fundamentals cache (populated by screener_scraper.py)
        sf = sb.table("fact_screener_fundamentals").select(
            "market_cap_cr,current_price,pe_ratio,book_value,face_value,eps_ttm,"
            "dividend_yield_pct,roce_pct,roe_pct,debt_to_equity,current_ratio,"
            "sales_ttm_cr,profit_ttm_cr,promoter_pct,fii_pct,dii_pct,public_pct,"
            "promoter_pledge_pct,scraped_at"
        ).eq("ticker", symbol).limit(1).execute()
        if sf.data:
            ctx["screener_db"] = sf.data[0]

        return ctx
    except Exception:
        return {}


def _build_context_prompt(symbol: str, screener: dict, supabase: dict) -> str:
    """Assemble all data sources into a single context block for the LLM."""
    parts: list[str] = [f"=== STOCK: {symbol} ===\n"]

    # Company info
    co = supabase.get("company", {})
    if co:
        parts.append(
            f"Company: {co.get('company_name', symbol)} | "
            f"Sector: {co.get('sector', 'N/A')} | "
            f"Industry: {co.get('industry', 'N/A')} | "
            f"Market Cap: {co.get('marketcap_category', 'N/A')} cap"
        )
        if co.get("market_cap_inr_cr"):
            parts.append(f"Market Cap: ₹{co['market_cap_inr_cr']:,.0f} Cr")

    # Screener fundamentals — prefer live scrape; fall back to cached DB row
    sdb = supabase.get("screener_db", {})
    if screener:
        parts.append("\n--- FUNDAMENTALS (screener.in live) ---")
        for k, v in screener.items():
            parts.append(f"{k}: {v}")
    elif sdb:
        parts.append(f"\n--- FUNDAMENTALS (screener.in cached {str(sdb.get('scraped_at',''))[:10]}) ---")
        mapping = {
            "Market Cap":      ("market_cap_cr",      "Cr"),
            "Price":           ("current_price",       "₹"),
            "P/E":             ("pe_ratio",            "x"),
            "Book Value":      ("book_value",          "₹"),
            "EPS (TTM)":       ("eps_ttm",             "₹"),
            "Dividend Yield":  ("dividend_yield_pct",  "%"),
            "ROCE":            ("roce_pct",            "%"),
            "ROE":             ("roe_pct",             "%"),
            "Debt/Equity":     ("debt_to_equity",      "x"),
            "Current Ratio":   ("current_ratio",       "x"),
            "Sales TTM":       ("sales_ttm_cr",        "Cr"),
            "Profit TTM":      ("profit_ttm_cr",       "Cr"),
            "Promoter %":      ("promoter_pct",        "%"),
            "Promoter Pledge": ("promoter_pledge_pct", "%"),
            "FII %":           ("fii_pct",             "%"),
            "DII %":           ("dii_pct",             "%"),
            "Public %":        ("public_pct",          "%"),
        }
        for label, (key, unit) in mapping.items():
            val = sdb.get(key)
            if val is not None:
                parts.append(f"{label}: {val} {unit}")

    # Technicals
    tech = supabase.get("technicals", {})
    if tech:
        parts.append("\n--- TECHNICALS ---")
        parts.append(
            f"Price: ₹{tech.get('close', 'N/A')} | Date: {tech.get('date', 'N/A')}\n"
            f"RSI(14): {tech.get('rsi_14', 'N/A')} | "
            f"MACD: {tech.get('macd', 'N/A')} | Signal: {tech.get('macd_signal', 'N/A')}\n"
            f"SMA20: {tech.get('sma_20', 'N/A')} | SMA50: {tech.get('sma_50', 'N/A')} | SMA200: {tech.get('sma_200', 'N/A')}\n"
            f"BB Upper: {tech.get('bb_upper', 'N/A')} | BB Lower: {tech.get('bb_lower', 'N/A')}\n"
            f"52W High: {tech.get('high_52w', 'N/A')} | 52W Low: {tech.get('low_52w', 'N/A')} | "
            f"From 52W High: {tech.get('pct_from_52w_high', 'N/A')}%\n"
            f"1D Change: {tech.get('pct_change_1d', 'N/A')}% | "
            f"5D Change: {tech.get('pct_change_5d', 'N/A')}% | "
            f"20D Change: {tech.get('pct_change_20d', 'N/A')}%\n"
            f"Rel Volume: {tech.get('rel_volume', 'N/A')}x | ATR(14): {tech.get('atr_14', 'N/A')}"
        )

    # Announcements
    anns = supabase.get("announcements", [])
    if anns:
        parts.append("\n--- RECENT ANNOUNCEMENTS (AI-tagged) ---")
        for a in anns:
            sent = a.get("sentiment", "")
            sent_sym = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(sent, "")
            parts.append(
                f"{sent_sym} [{a.get('published_date', '')[:10]}] "
                f"{a.get('announcement_type', '')} — {a.get('summary_header', '')}"
            )
            if a.get("summary_text"):
                parts.append(f"   {a['summary_text'][:200]}")

    # Results calendar
    cal = supabase.get("calendar", [])
    if cal:
        parts.append("\n--- RESULTS CALENDAR ---")
        for r in cal:
            parts.append(
                f"Q{r.get('fiscal_quarter', '?')} FY{r.get('fiscal_year', '?')}: "
                f"{r.get('result_date', 'TBD')} ({r.get('result_type', '')})"
            )

    if len(parts) == 1:
        parts.append("No additional data available. Provide analysis based on your knowledge of this company.")

    return "\n".join(parts)


def _gather_all_context(symbol: str) -> tuple[str, list[str]]:
    """Gather screener + Supabase context synchronously (runs in thread pool)."""
    sources: list[str] = []

    # These two are independent — run in parallel using threading
    screener_result: dict = {}
    supabase_result: dict = {}

    import threading
    def fetch_screener():
        nonlocal screener_result
        screener_result = _scrape_screener(symbol)

    def fetch_supabase():
        nonlocal supabase_result
        supabase_result = _get_supabase_context(symbol)

    t1 = threading.Thread(target=fetch_screener)
    t2 = threading.Thread(target=fetch_supabase)
    t1.start(); t2.start()
    t1.join(timeout=4); t2.join(timeout=3)

    if screener_result:
        sources.append(f"screener.in: {symbol}")
    if supabase_result:
        sources.append("NEO Database")

    context = _build_context_prompt(symbol, screener_result, supabase_result)
    return context, sources


# ---------------------------------------------------------------------------
# LLM providers (unchanged cascade)
# ---------------------------------------------------------------------------

def _groq_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    import requests as _req
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        for turn in history[-4:]:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": user_msg})
    r = _req.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 900},
        timeout=6,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    import requests as _req
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    contents: list[dict] = []
    if history:
        for turn in history[-4:]:
            role = "model" if turn.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": user_msg}]})
    r = _req.post(
        url,
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 900},
        },
        timeout=7,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _nvidia_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    import requests as _req
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        raise ValueError("NVIDIA_API_KEY not set")
    model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-r1").strip()
    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        for turn in history[-4:]:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": user_msg})
    r = _req.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 900, "stream": False},
        timeout=10,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    if "<think>" in content and "</think>" in content:
        after = content.split("</think>", 1)[-1].strip()
        if after:
            content = after
    return content


def _llm_complete(system: str, user_msg: str, history: list[dict] | None = None) -> tuple[str, str, int]:
    preferred = os.getenv("LLM_PROVIDER", "groq").lower()
    cascade = {
        "groq":   [("groq", _groq_complete),    ("gemini", _gemini_complete), ("nvidia", _nvidia_complete)],
        "gemini": [("gemini", _gemini_complete), ("groq", _groq_complete),    ("nvidia", _nvidia_complete)],
        "nvidia": [("nvidia", _nvidia_complete), ("groq", _groq_complete),    ("gemini", _gemini_complete)],
    }
    ordered = cascade.get(preferred, cascade["groq"])
    last_error = ""
    for name, fn in ordered:
        try:
            t0 = time.monotonic()
            result = fn(system, user_msg, history)
            latency_ms = int((time.monotonic() - t0) * 1000)
            if result and result.strip():
                return result.strip(), name, latency_ms
        except Exception as exc:
            last_error = f"{name}: {exc}"
    return (
        "All AI providers temporarily unavailable. Please try again in a moment.",
        f"none:{last_error[:80]}",
        0,
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    symbol: str | None = Field(default=None, max_length=20)
    history: list[dict] | None = None
    pdf_text: str | None = Field(default=None, max_length=8000)
    preset_id: str | None = None  # matches PRESET_QUESTIONS ids

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().upper().replace(".NS", "").replace(".BO", "")
        return cleaned if cleaned and _SAFE_SYMBOL_RE.match(cleaned) else None


class ChatResponse(BaseModel):
    response: str
    sources: list[str]
    symbol: str | None
    provider: str | None = None
    latency_ms: int | None = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "THE", "AND", "FOR", "ARE", "YOU", "NSE", "BSE", "FII", "DII",
    "IPO", "AGM", "EPS", "ROE", "PAT", "NII", "NIM", "AUM", "SEBI",
    "WHAT", "HOW", "WHY", "WHEN", "WHERE", "BANK", "TODAY", "STOCK",
    "MARKET", "SHARE", "PRICE", "ANALYSE", "ANALYZE", "COMPARE",
    "LATEST", "RECENT", "UPCOMING", "WHICH", "SECTOR", "QUARTERLY",
    "RESULTS", "ANNUAL", "REPORT", "NEWS", "FLOW", "DATA", "GIVE",
    "FULL", "ANALYSIS", "ENTRY", "TARGETS", "NEAR", "TERM", "KEY",
    "RISKS", "LEVEL", "BREAKOUT", "CATALYST",
}


@router.post("/message", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat), Depends(require_internal_key)])
async def chat_message(body: ChatMessage):
    loop = asyncio.get_running_loop()
    t_start = time.monotonic()

    symbol = body.symbol or ""
    user_msg = body.message.strip()

    # If a preset button was clicked, expand to full question
    if body.preset_id:
        for pq in PRESET_QUESTIONS:
            if pq["id"] == body.preset_id:
                user_msg = pq["prompt"] + (f" (stock: {symbol})" if symbol else "")
                break

    # Auto-extract symbol from message if not provided
    if not symbol:
        for tok in re.findall(r'\b([A-Z][A-Z0-9&\-]{1,14})\b', user_msg):
            if tok not in _STOP_WORDS and len(tok) >= 2:
                symbol = tok
                break

    context_str = ""
    sources: list[str] = []

    # Gather rich context (screener.in + Supabase) within 5s budget
    if symbol:
        try:
            context_str, sources = await asyncio.wait_for(
                loop.run_in_executor(_executor, _gather_all_context, symbol),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            sources = []

    # Add uploaded PDF if any
    if body.pdf_text:
        context_str = f"Document context:\n{body.pdf_text[:4000]}\n\n" + context_str
        sources.insert(0, "Uploaded Document")

    # Build full message for LLM
    if context_str:
        full_msg = f"{context_str}\n\n---\nUser question: {user_msg}"
    else:
        full_msg = user_msg

    trimmed_history = (body.history or [])[-4:]

    # LLM call — 8.5s budget (Vercel 10s function limit)
    try:
        reply, provider, latency_ms = await asyncio.wait_for(
            loop.run_in_executor(_executor, _llm_complete, SYSTEM_PROMPT, full_msg, trimmed_history),
            timeout=8.5,
        )
    except asyncio.TimeoutError:
        reply = "Response took too long. Please try again — Groq/Gemini will retry automatically."
        provider = "timeout"
        latency_ms = 8500

    if not sources:
        sources = ["One Piece Market Intelligence"]

    return ChatResponse(
        response=reply,
        sources=sources,
        symbol=symbol or None,
        provider=provider,
        latency_ms=latency_ms,
    )


@router.get("/presets")
async def get_presets() -> list[dict]:
    """Return available preset question buttons."""
    return PRESET_QUESTIONS


@router.get("/probe")
async def chat_probe():
    """Debug: verify all data source connectivity."""
    import requests as _req
    results: dict[str, Any] = {}

    # LLM providers
    for name, key_env, test_url, headers_fn, payload in [
        ("groq",   "GROQ_API_KEY",
         "https://api.groq.com/openai/v1/chat/completions",
         lambda k: {"Authorization": f"Bearer {k}"},
         {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5}),
        ("gemini", "GEMINI_API_KEY", None, None, None),
    ]:
        key = os.getenv(key_env, "")
        results[f"{name}_key"] = bool(key)
        if key and name == "groq":
            try:
                r = _req.post(test_url, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=8)
                results[f"{name}_status"] = r.status_code
                if r.status_code == 200:
                    results[f"{name}_ok"] = True
            except Exception as e:
                results[f"{name}_error"] = str(e)[:100]

    # Screener test
    try:
        d = _scrape_screener("INFY")
        results["screener_ok"] = bool(d)
        results["screener_pe"] = d.get("Stock P/E")
    except Exception as e:
        results["screener_error"] = str(e)

    # Supabase context test
    try:
        d = _get_supabase_context("INFY")
        results["supabase_company"] = bool(d.get("company"))
        results["supabase_technicals"] = bool(d.get("technicals"))
        results["supabase_announcements"] = len(d.get("announcements", []))
    except Exception as e:
        results["supabase_error"] = str(e)

    return results


@router.get("/suggestions")
async def chat_suggestions():
    return [
        "Full analysis of RELIANCE",
        "Entry & targets for HDFCBANK",
        "What is the FII/DII activity in INFY?",
        "Key risks for TCS at current levels",
        "Breakout level for ICICIBANK",
        "Compare AXISBANK vs HDFCBANK",
        "Near-term catalysts for BAJFINANCE",
        "Quarterly results analysis of WIPRO",
        "Is TATAMOTORS overvalued or undervalued?",
        "Shareholding changes in ADANIENT",
    ]
