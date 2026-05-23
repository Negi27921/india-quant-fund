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

from api.middleware.security import rate_limit_chat, require_internal_key

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
    # Delegates to the unified market data layer (fast_info only, avoids the
    # 3-10s yfinance .info call that caused 504s on Vercel's 10s timeout).
    from core.market_data import get_stock_context
    return get_stock_context(symbol, fast=True)


SYSTEM_PROMPT = """You are the One Piece Market Intelligence Assistant — a world-class AI analyst specialising in Indian stock markets (NSE & BSE).

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


def _nvidia_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    """NVIDIA NIM — DeepSeek R1 via OpenAI-compatible endpoint."""
    import requests as _req
    key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not key:
        raise ValueError("NVIDIA_API_KEY not set")
    model = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-r1").strip()

    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        for turn in history:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": user_msg})

    r = _req.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 800, "stream": False},
        timeout=12,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    # DeepSeek R1 wraps chain-of-thought in <think>…</think> — strip for clean reply
    if "<think>" in content and "</think>" in content:
        after = content.split("</think>", 1)[-1].strip()
        if after:
            content = after
    return content


def _groq_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    """Groq — Llama 3.3 70B (fallback 1)."""
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
        json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 800},
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini_complete(system: str, user_msg: str, history: list[dict] | None = None) -> str:
    """Gemini Flash (fallback 2)."""
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
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800},
        },
        timeout=6,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _llm_complete(system: str, user_msg: str, history: list[dict] | None = None) -> tuple[str, str, int]:
    """Try providers in order: NVIDIA/DeepSeek → Groq → Gemini. Returns (reply, provider, latency_ms)."""
    preferred = os.getenv("LLM_PROVIDER", "nvidia").lower()

    # Build cascade — always try all three, just change order by preference
    _all = [
        ("nvidia",  _nvidia_complete),
        ("groq",    _groq_complete),
        ("gemini",  _gemini_complete),
    ]
    if preferred == "groq":
        ordered = [("groq", _groq_complete), ("nvidia", _nvidia_complete), ("gemini", _gemini_complete)]
    elif preferred == "gemini":
        ordered = [("gemini", _gemini_complete), ("nvidia", _nvidia_complete), ("groq", _groq_complete)]
    else:
        ordered = _all  # nvidia first (default)

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
            continue

    return (
        "I encountered a temporary issue connecting to the AI provider. "
        "Please try again in a moment.",
        f"none:{last_error[:80]}" if last_error else "none",
        0,
    )


@router.post("/message", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat), Depends(require_internal_key)])
async def chat_message(body: ChatMessage):
    loop = asyncio.get_running_loop()

    symbol = body.symbol or ""
    user_msg = body.message.strip()

    # Auto-extract stock symbol — only from UPPERCASE tokens already in the message
    if not symbol:
        _STOP = {
            "THE", "AND", "FOR", "ARE", "YOU", "NSE", "BSE", "FII", "DII",
            "IPO", "AGM", "EPS", "ROE", "PAT", "NII", "NIM", "AUM", "SEBI",
            "WHAT", "HOW", "WHY", "WHEN", "WHERE", "BANK", "TODAY", "STOCK",
            "MARKET", "SHARE", "PRICE", "ANALYSE", "ANALYZE", "COMPARE",
            "LATEST", "RECENT", "UPCOMING", "WHICH", "SECTOR", "QUARTERLY",
            "RESULTS", "ANNUAL", "REPORT", "NEWS", "FLOW", "DATA",
        }
        for c in re.findall(r'\b([A-Z][A-Z0-9&\-]{1,9})\b', user_msg):
            if c not in _STOP:
                symbol = c
                break

    context_parts: list[str] = []
    sources: list[str] = []

    # yfinance capped at 1s — skip quickly to preserve budget for LLM within Vercel's 10s limit
    if symbol:
        try:
            stock_context = await asyncio.wait_for(
                loop.run_in_executor(_executor, _get_stock_context, symbol),
                timeout=1.0,
            )
            if stock_context and "unavailable" not in stock_context:
                context_parts.append(stock_context)
                sources.append(f"NSE Live Data: {symbol}")
        except (asyncio.TimeoutError, Exception):
            pass

    if body.pdf_text:
        context_parts.insert(0, f"Document context:\n{body.pdf_text[:4000]}")
        sources.append("Uploaded Document")

    full_msg = user_msg
    if context_parts:
        full_msg = f"Context (live market data):\n{'---'.join(context_parts)}\n\nUser question: {user_msg}"

    # Trim history to last 4 turns to reduce token count and latency
    trimmed_history = (body.history or [])[-4:] if body.history else None

    # LLM capped at 6s — leaves ~4s headroom for Vercel cold start within the 10s function limit
    try:
        reply, provider, latency_ms = await asyncio.wait_for(
            loop.run_in_executor(_executor, _llm_complete, SYSTEM_PROMPT, full_msg, trimmed_history),
            timeout=8.5,
        )
    except asyncio.TimeoutError:
        reply = "One Piece Market Intelligence: AI response took too long. This is a temporary issue — Groq and Gemini are being retried. Please send your message again."
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
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        results["gemini_model"] = gemini_model
        try:
            r = _req.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_key.strip()}",
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
