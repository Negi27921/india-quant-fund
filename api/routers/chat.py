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


def _llm_complete(system: str, user_msg: str) -> tuple[str, str, int]:
    """
    Runs the BaseLLMClient completion synchronously (called from executor).
    Returns (reply, provider_used, latency_ms).
    """
    from agents.base import BaseLLMClient

    client = BaseLLMClient()
    preferred = os.getenv("LLM_PROVIDER", "groq")
    _PROVIDER_ORDER = ["openai", "groq", "deepseek", "gemini", "qwen", "ollama"]
    order = [preferred] + [p for p in _PROVIDER_ORDER if p != preferred]

    for provider in order:
        if not client._has_key(provider):
            continue
        try:
            t0 = time.monotonic()
            result = client._call(provider, system, user_msg, 0.3, 1200)
            latency_ms = int((time.monotonic() - t0) * 1000)
            if result:
                return result, provider, latency_ms
        except Exception:
            continue

    return (
        "I encountered a temporary issue connecting to all AI providers. "
        "Please try again in a moment.",
        "none",
        0,
    )


@router.post("/message", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat)])
async def chat_message(body: ChatMessage):
    loop = asyncio.get_event_loop()

    symbol = body.symbol or ""
    user_msg = body.message.strip()

    # Auto-extract symbol from message
    if not symbol:
        candidates = re.findall(r'\b([A-Z]{2,10})\b', user_msg.upper())
        common_stops = {"THE", "AND", "FOR", "ARE", "YOU", "NSE", "BSE", "FII", "DII",
                        "IPO", "AGM", "EPS", "ROE", "PAT", "NII", "NIM", "AUM", "SEBI"}
        for c in candidates:
            if c not in common_stops:
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

    reply, provider, latency_ms = await loop.run_in_executor(
        _executor, _llm_complete, SYSTEM_PROMPT, full_msg
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
