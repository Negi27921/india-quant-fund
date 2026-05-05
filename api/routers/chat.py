"""AI Chat endpoint — stock research assistant powered by DeepSeek/Anthropic."""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")

_chat_cache: dict[str, tuple[float, str]] = {}


class ChatMessage(BaseModel):
    message: str
    symbol: str | None = None
    history: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]


class ChatResponse(BaseModel):
    response: str
    sources: list[str]
    symbol: str | None


def _get_stock_context(symbol: str) -> str:
    """Fetch live stock data as context for the LLM."""
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


def _get_bse_filings_context(symbol: str) -> str:
    """Fetch recent BSE filings for context."""
    try:
        import urllib.request
        import json
        # Try to get BSE scrip code first via NSE search
        url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=&strScrip=&strSearch=P&strToDate=&strType=C&subcategory=-1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())

        items = data.get("Table", [])
        relevant = [i for i in items if symbol.upper() in i.get("SLONGNAME", "").upper() or symbol.upper() in str(i.get("SCRIP_CD", ""))][:5]

        if not relevant:
            return ""

        context = f"\nRecent BSE Filings for {symbol.upper()}:\n"
        for item in relevant:
            context += f"- [{item.get('CATEGORYNAME','')}] {item.get('HEADLINE','')} ({item.get('NEWS_DT','')[:10]})\n"
        return context
    except Exception:
        return ""


def _call_llm(messages: list[dict], system: str) -> str:
    """Call LLM — tries DeepSeek first, falls back to Anthropic."""
    # Try DeepSeek
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        try:
            import httpx
            resp = httpx.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "system", "content": system}] + messages,
                    "max_tokens": 800,
                    "temperature": 0.3,
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    # Try Anthropic
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            import httpx
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "system": system,
                    "messages": messages,
                    "max_tokens": 800,
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"]
        except Exception:
            pass

    # No LLM available — intelligent fallback
    last_msg = messages[-1]["content"] if messages else ""
    return f"I'm your IQF Market Assistant. You asked: '{last_msg[:100]}...'\n\nI need an API key (DEEPSEEK_API_KEY or ANTHROPIC_API_KEY) to provide AI-powered analysis. Please set one in your environment.\n\nFor now, use the market data panels on the left for live indices, FII/DII flows, and filings."


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


@router.post("/message", response_model=ChatResponse)
async def chat_message(body: ChatMessage):
    """Process a chat message and return AI analysis."""
    import asyncio
    loop = asyncio.get_event_loop()
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=2)

    symbol = (body.symbol or "").strip().upper().replace(".NS", "").replace(".BO", "")
    user_msg = body.message.strip()

    # Build context
    context_parts = []
    sources = []

    # Try to extract symbol from message if not provided
    if not symbol:
        import re
        # Look for NSE symbols in the message (all-caps 2-10 char words)
        candidates = re.findall(r'\b([A-Z]{2,10})\b', user_msg.upper())
        common_stops = {"THE", "AND", "FOR", "ARE", "YOU", "NSE", "BSE", "FII", "DII", "IPO", "AGM", "EPS", "ROE", "PAT", "NII", "NIM", "AUM", "SEBI"}
        for c in candidates:
            if c not in common_stops:
                symbol = c
                break

    if symbol:
        # Fetch stock context in parallel with filing context
        def _get_ctx():
            stock_ctx = _get_stock_context(symbol)
            filing_ctx = _get_bse_filings_context(symbol)
            return stock_ctx, filing_ctx

        try:
            stock_context, filing_context = await loop.run_in_executor(executor, _get_ctx)
            if stock_context:
                context_parts.append(stock_context)
                sources.append(f"NSE Live Data: {symbol}")
            if filing_context:
                context_parts.append(filing_context)
                sources.append("BSE Filings Feed")
        except Exception:
            pass

    # Build message history
    history = body.history or []
    messages = []
    for h in history[-6:]:  # Last 6 turns for context
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})

    # Build final user message with context
    full_msg = user_msg
    if context_parts:
        full_msg = f"Context (live market data):\n{'---'.join(context_parts)}\n\nUser question: {user_msg}"

    messages.append({"role": "user", "content": full_msg})

    # Call LLM
    def _call():
        return _call_llm(messages, SYSTEM_PROMPT)

    response_text = await loop.run_in_executor(executor, _call)

    if not sources:
        sources = ["IQF Market Intelligence"]

    return ChatResponse(response=response_text, sources=sources, symbol=symbol or None)


@router.get("/suggestions")
async def chat_suggestions():
    """Return suggested starter questions for the chatbot."""
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
