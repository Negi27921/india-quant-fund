"""AI Chat endpoint — stock research assistant via multi-provider LLM router."""
from __future__ import annotations

import asyncio
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from api.middleware.security import rate_limit_chat

router = APIRouter()

_SAFE_SYMBOL_RE = re.compile(r'^[A-Z0-9&\-]{1,20}$')
IST = ZoneInfo("Asia/Kolkata")

_executor = ThreadPoolExecutor(max_workers=4)


class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    symbol: str | None = Field(default=None, max_length=20)
    history: list[dict] | None = None
    pdf_text: str | None = Field(default=None, max_length=8000)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().upper().replace(".NS", "").replace(".BO", "")
        if cleaned and not _SAFE_SYMBOL_RE.match(cleaned):
            return None
        return cleaned or None


class ChatResponse(BaseModel):
    response: str
    sources: list[str]
    symbol: str | None
    provider: str | None = None
    latency_ms: int | None = None


def _get_stock_context(symbol: str) -> str:
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{symbol.upper()}.NS")
        info = ticker.info
        hist = ticker.history(period="5d")

        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        pe = info.get("trailingPE", "N/A")
        pb = info.get("priceToBook", "N/A")
        mktcap = info.get("marketCap", 0)
        mktcap_cr = round(mktcap / 1e7, 0) if mktcap else "N/A"
        revenue = info.get("totalRevenue", 0)
        rev_cr = round(revenue / 1e7, 0) if revenue else "N/A"
        roe = info.get("returnOnEquity", "N/A")
        div_yield = info.get("dividendYield", 0)
        week_52_high = info.get("fiftyTwoWeekHigh", "N/A")
        week_52_low = info.get("fiftyTwoWeekLow", "N/A")

        change_pct = 0.0
        if not hist.empty and len(hist) >= 2:
            change_pct = ((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2]) * 100

        return f"""
Stock: {symbol.upper()} (NSE)
Current Price: ₹{price:,.2f} ({change_pct:+.2f}% today)
Market Cap: ₹{mktcap_cr:,} Cr
52W High: ₹{week_52_high} | 52W Low: ₹{week_52_low}
P/E Ratio: {pe} | P/B: {pb}
ROE: {round(float(roe)*100, 1) if roe != 'N/A' else 'N/A'}%
Revenue (TTM): ₹{rev_cr:,} Cr
Dividend Yield: {round(float(div_yield)*100, 2) if div_yield else 'N/A'}%
Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}
""".strip()
    except Exception:
        return f"Stock: {symbol.upper()} (NSE) - Live data unavailable"


SYSTEM_PROMPT = """You are the IQF Market Intelligence Assistant — a world-class AI analyst specialising in Indian stock markets (NSE & BSE).

You help users with:
1. Stock analysis and fundamental research (P/E, ROE, debt, margins, competitive position)
2. BSE/NSE filings interpretation (reading between the lines of corporate announcements)
3. Corporate actions (dividends, splits, bonuses, rights issues)
4. Quarterly results analysis (what's the real story behind the numbers)
5. Sector and macro trends affecting Indian equities
6. Technical levels and price context
7. Comparing companies within sectors
8. FII/DII flow interpretation

Rules:
- Always be specific with numbers — cite the data provided
- Flag risks clearly — don't be a bull/bear shill
- Format responses with clear structure: use **bold** for key metrics, bullet points for lists
- Keep responses concise (max 300 words) but information-dense
- End with 1-2 "Key Takeaways" in bullet points
- Never give direct buy/sell advice — give analysis, flag risks, present both sides
- Always mention "This is not financial advice" briefly at the end
- Reference Indian market context: SEBI rules, NSE/BSE norms, India VIX, FII/DII dynamics
"""


def _groq_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    """Direct HTTP call to Groq with conversation history support."""
    import requests as _req
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise ValueError("GROQ_API_KEY not set")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        for turn in history:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": user_msg})
    r = _req.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1200},
        timeout=25,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    """Direct HTTP call to Gemini with multi-turn conversation history support."""
    import requests as _req
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

    contents: list[dict] = []
    if history:
        for turn in history:
            role = turn.get("role", "user")
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": turn.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": user_msg}]})

    r = _req.post(
        url,
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1200},
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _openai_compat_complete(system: str, user_msg: str) -> str:
    """OpenAI-compatible endpoint (custom router, OpenAI, DeepSeek)."""
    import requests as _req
    key = os.getenv("OPENAI_API_KEY", "").strip()
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").strip().rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY not set")
    r = _req.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.3,
            "max_tokens": 1200,
        },
        timeout=25,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _llm_complete(system: str, user_msg: str, history: list[dict] | None = None) -> tuple[str, str, int]:
    """Try LLM providers in order. Returns (reply, provider, latency_ms)."""
    preferred = os.getenv("LLM_PROVIDER", "gemini").lower()

    providers: list[tuple[str, callable]] = []
    if preferred == "groq":
        providers = [("groq", _groq_complete), ("gemini", _gemini_complete), ("openai", _openai_compat_complete)]
    elif preferred == "gemini":
        providers = [("gemini", _gemini_complete), ("groq", _groq_complete), ("openai", _openai_compat_complete)]
    else:
        providers = [("openai", _openai_compat_complete), ("groq", _groq_complete), ("gemini", _gemini_complete)]

    last_error = ""
    for name, fn in providers:
        try:
            t0 = time.monotonic()
            # Gemini supports history; other providers get history injected into user_msg
            if name == "gemini":
                result = fn(system, user_msg, history)
            elif history and name in ("groq", "openai"):
                result = fn(system, user_msg, history)
            else:
                result = fn(system, user_msg)
            latency_ms = int((time.monotonic() - t0) * 1000)
            if result and result.strip():
                return result.strip(), name, latency_ms
        except Exception as exc:
            last_error = f"{name}: {exc}"
            continue

    return (
        "I encountered a temporary issue connecting to the AI provider. "
        "Please try again in a moment.",
        f"none:{last_error[:80]}" if last_error else "none",
        0,
    )


@router.post("/message", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat)])
async def chat_message(body: ChatMessage):
    loop = asyncio.get_event_loop()

    symbol = body.symbol or ""
    user_msg = body.message.strip()

    # Auto-extract stock symbol from message (words already uppercase in original)
    if not symbol:
        _STOP = {
            "THE", "AND", "FOR", "ARE", "YOU", "NSE", "BSE", "FII", "DII",
            "IPO", "AGM", "EPS", "ROE", "PAT", "NII", "NIM", "AUM", "SEBI",
            "WHAT", "HOW", "WHY", "WHEN", "WHERE", "BANK", "TODAY", "STOCK",
            "MARKET", "SHARE", "PRICE", "ANALYSE", "ANALYZE", "COMPARE",
            "LATEST", "RECENT", "UPCOMING", "WHICH", "SECTOR", "QUARTERLY",
            "RESULTS", "ANNUAL", "REPORT", "NEWS", "FLOW", "DATA",
        }
        # Look for UPPERCASE tokens in the original (not uppercased) message
        candidates = re.findall(r'\b([A-Z][A-Z0-9&\-]{1,9})\b', user_msg)
        for c in candidates:
            if c not in _STOP and len(c) >= 2:
                symbol = c
                break

    context_parts: list[str] = []
    sources: list[str] = []

    if symbol:
        try:
            stock_context = await loop.run_in_executor(_executor, _get_stock_context, symbol)
            if stock_context:
                context_parts.append(stock_context)
                sources.append(f"NSE Live Data: {symbol}")
        except Exception:
            pass

    if body.pdf_text:
        context_parts.insert(0, f"Document context:\n{body.pdf_text[:4000]}")
        sources.append("Uploaded Document")

    full_msg = user_msg
    if context_parts:
        full_msg = f"Context (live market data):\n{'---'.join(context_parts)}\n\nUser question: {user_msg}"

    # Trim history to last 10 turns to stay within token limits
    trimmed_history = (body.history or [])[-10:] if body.history else None

    reply, provider, latency_ms = await loop.run_in_executor(
        _executor, _llm_complete, SYSTEM_PROMPT, full_msg, trimmed_history
    )

    if not sources:
        sources = ["IQF Market Intelligence"]

    return ChatResponse(
        response=reply,
        sources=sources,
        symbol=symbol or None,
        provider=provider,
        latency_ms=latency_ms,
    )


@router.get("/probe")
async def chat_probe():
    """Debug: check LLM provider connectivity."""
    import requests as _req
    results = {}
    groq_key = os.getenv("GROQ_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    results["groq_key_set"] = bool(groq_key)
    results["gemini_key_set"] = bool(gemini_key)
    results["llm_provider"] = os.getenv("LLM_PROVIDER", "NOT_SET")

    if groq_key:
        try:
            r = _req.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key.strip()}"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5},
                timeout=10,
            )
            results["groq_status"] = r.status_code
            if r.status_code == 200:
                results["groq_response"] = r.json()["choices"][0]["message"]["content"]
            else:
                results["groq_error"] = r.text[:200]
        except Exception as e:
            results["groq_exception"] = str(e)[:200]

    if gemini_key:
        try:
            r = _req.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={gemini_key.strip()}",
                json={"contents": [{"parts": [{"text": "Say OK"}]}], "generationConfig": {"maxOutputTokens": 5}},
                timeout=10,
            )
            results["gemini_status"] = r.status_code
            if r.status_code == 200:
                results["gemini_response"] = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                results["gemini_error"] = r.text[:200]
        except Exception as e:
            results["gemini_exception"] = str(e)[:200]

    return results


@router.get("/suggestions")
async def chat_suggestions():
    return [
        "What are the latest filings from Reliance Industries?",
        "Analyse HDFC Bank's Q4 results and dividend outlook",
        "Compare Infosys vs TCS — which is better valued?",
        "What does today's FII selling mean for the market?",
        "Upcoming corporate actions this week — dividends and splits?",
        "Explain the Adani Enterprises latest BSE filing",
        "Which sectors are FIIs buying vs selling?",
        "What is the results calendar for next 2 weeks?",
        "Is Bajaj Finance expensive at current P/E?",
        "What are top SME IPOs in the pipeline?",
    ]
