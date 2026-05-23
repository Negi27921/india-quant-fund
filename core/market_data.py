"""Unified market data access layer — replaces all ad-hoc yfinance calls.

Previously, three separate helpers existed across routers:
  - portfolio.py  → _live_prices()
  - journal.py    → _fetch_prices_sync()
  - market.py     → _fetch_fast_info() / _batch_download()
  - chat.py       → _get_stock_context()

All routers now call functions from this module.  The underlying provider
is determined by MARKET_PROVIDER env var and can be swapped without code
changes (yfinance → nse → kite → mock).

Thread-safety
-------------
All functions are safe to call from concurrent threads / async code via
run_in_executor.  The provider itself manages its own executor.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, wait
from functools import lru_cache
from typing import Any

from core.providers.registry import get_market_provider

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="market-data")


# ── Synchronous helpers (use in sync contexts or run_in_executor) ─────────────

def get_price(symbol: str) -> float:
    """Return the last traded price for a single symbol. 0.0 on error."""
    try:
        quote = get_market_provider().get_quote(symbol)
        return float(quote.get("price", 0.0))
    except Exception:
        return 0.0


def get_prices_bulk(
    symbols: list[str], timeout_s: float = 8.0
) -> dict[str, float]:
    """Return {symbol: price} for many tickers, capped at timeout_s.

    Replaces:
      - portfolio.py _live_prices()
      - journal.py _fetch_prices_sync()
    """
    if not symbols:
        return {}
    provider = get_market_provider()
    quotes = provider.get_quotes_bulk(symbols, timeout_s) if hasattr(
        provider, "get_quotes_bulk"
    ) else {}
    # Fallback: individual calls in thread pool
    if not quotes:
        futs = {_executor.submit(get_price, s): s for s in symbols}
        done, _ = wait(futs, timeout=timeout_s)
        return {futs[f]: f.result() for f in done if not f.exception()}
    return {sym: float(q.get("price", 0.0)) for sym, q in quotes.items()}


def get_quote(symbol: str) -> dict[str, Any]:
    """Full quote dict for one symbol."""
    return get_market_provider().get_quote(symbol)


def get_history(
    symbol: str, period: str = "1y", interval: str = "1d"
) -> list[dict[str, Any]]:
    """OHLCV history list.  Each row: {date, open, high, low, close, volume}."""
    return get_market_provider().get_history(symbol, period, interval)


def get_stock_context(symbol: str, fast: bool = True) -> str:
    """Return a formatted text context block for a stock — used by AI chat.

    Replaces chat.py _get_stock_context().
    Uses fast_info (no heavy .info call) to stay within Vercel's 10s timeout.
    """
    sym = symbol.upper().replace(".NS", "").replace(".BO", "")
    try:
        # fast path — only fast_info + 5d history
        import yfinance as yf
        ticker = yf.Ticker(f"{sym}.NS")
        fi = ticker.fast_info

        price     = float(fi.last_price or 0)
        prev      = float(fi.previous_close or price)
        high_52w  = float(fi.year_high or 0)
        low_52w   = float(fi.year_low or 0)
        mktcap    = float(fi.market_cap or 0)
        mktcap_cr = round(mktcap / 1e7, 0) if mktcap else "N/A"

        chg_p = ((price - prev) / prev * 100) if prev else 0.0

        hist_rows = []
        if not fast:
            hist_rows = get_history(sym, period="1mo", interval="1d")
        else:
            # 5d only — much faster than .history()
            import pandas as pd
            raw = yf.download(f"{sym}.NS", period="5d", interval="1d",
                              auto_adjust=True, progress=False)
            if not raw.empty:
                hist_rows = [
                    {"date": str(d.date()), "close": round(float(c), 2)}
                    for d, c in zip(raw.index, raw["Close"])
                ]

        hist_text = ""
        if hist_rows:
            recent = hist_rows[-5:]
            lines = [f"  {r['date']}: ₹{r.get('close', r.get('price', 0)):,.2f}" for r in recent]
            hist_text = "\nRecent closes:\n" + "\n".join(lines)

        return (
            f"Stock: {sym} (NSE)\n"
            f"Price: ₹{price:,.2f} ({chg_p:+.2f}% today)\n"
            f"52W High: ₹{high_52w:,.2f} | 52W Low: ₹{low_52w:,.2f}\n"
            f"Market Cap: ₹{mktcap_cr:,} Cr"
            f"{hist_text}"
        )
    except Exception as exc:
        return f"Stock: {sym} (NSE)\nData unavailable: {exc}"


def get_market_status() -> dict[str, Any]:
    """Return market open/closed status."""
    return get_market_provider().get_market_status()


# ── Async wrappers (use in FastAPI route handlers) ────────────────────────────

async def async_get_price(symbol: str) -> float:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, get_price, symbol)


async def async_get_prices_bulk(
    symbols: list[str], timeout_s: float = 8.0
) -> dict[str, float]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _executor, get_prices_bulk, symbols, timeout_s
    )


async def async_get_quote(symbol: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, get_quote, symbol)


async def async_get_history(
    symbol: str, period: str = "1y", interval: str = "1d"
) -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, get_history, symbol, period, interval)


async def async_get_stock_context(symbol: str, fast: bool = True) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, get_stock_context, symbol, fast)
