"""AI Chat endpoint — stock research assistant powered by Groq."""
from __future__ import annotations

import os
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


class ChatMessage(BaseModel):
    message: str
    symbol: str | None = None
    history: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]
    pdf_text: str | None = None


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
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=2)

    # No API key — return helpful fallback immediately
    if not GROQ_API_KEY:
        return ChatResponse(
            response=(
                "I'm your IQF Market Assistant. To enable AI-powered analysis, "
                "please set the GROQ_API_KEY environment variable (free at console.groq.com).\n\n"
                "For now, use the market data panels for live indices, FII/DII flows, and filings."
            ),
            sources=["IQF Market Intelligence"],
            symbol=None,
        )

    symbol = (body.symbol or "").strip().upper().replace(".NS", "").replace(".BO", "")
    user_msg = body.message.strip()

    # Build context
    context_parts = []
    sources = []

    # Try to extract symbol from message if not provided
    if not symbol:
        import re
        candidates = re.findall(r'\b([A-Z]{2,10})\b', user_msg.upper())
        common_stops = {"THE", "AND", "FOR", "ARE", "YOU", "NSE", "BSE", "FII", "DII", "IPO", "AGM", "EPS", "ROE", "PAT", "NII", "NIM", "AUM", "SEBI"}
        for c in candidates:
            if c not in common_stops:
                symbol = c
                break

    if symbol:
        def _get_ctx():
            return _get_stock_context(symbol)

        try:
            stock_context = await loop.run_in_executor(executor, _get_ctx)
            if stock_context:
                context_parts.append(stock_context)
                sources.append(f"NSE Live Data: {symbol}")
        except Exception:
            pass

    # Prepend PDF document context if provided
    if body.pdf_text:
        context_parts.insert(0, f"Document context:\n{body.pdf_text[:4000]}")
        sources.append("Uploaded Document")

    # Build message history
    history = body.history or []
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-6:]:  # Last 6 turns for context
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})

    # Build final user message with context
    full_msg = user_msg
    if context_parts:
        full_msg = f"Context (live market data):\n{'---'.join(context_parts)}\n\nUser question: {user_msg}"

    messages.append({"role": "user", "content": full_msg})

    # Call Groq API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": messages,
                    "max_tokens": 1200,
                    "temperature": 0.3,
                },
            )
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
    except Exception as e:
        reply = (
            f"I encountered a temporary issue connecting to the AI service. "
            f"Please try again in a moment.\n\n"
            f"_(Error: {type(e).__name__})_\n\n"
            f"In the meantime, the live market panels on this page have indices, "
            f"FII/DII flows, filings, and corporate actions."
        )

    if not sources:
        sources = ["IQF Market Intelligence"]

    return ChatResponse(response=reply, sources=sources, symbol=symbol or None)


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
