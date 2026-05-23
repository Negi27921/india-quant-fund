"""yfinance market data provider (current default).

Wraps the existing scattered yfinance calls into a single, testable adapter.
15-min delayed for Indian stocks — acceptable for research / paper trading.
"""
from __future__ import annotations

import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import datetime
from typing import Any

from core.providers.base import MarketDataProvider

warnings.filterwarnings("ignore")

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="yf-market")

_NSE_SUFFIX = ".NS"
_BSE_SUFFIX = ".BO"


def _ns(symbol: str) -> str:
    """Add .NS suffix if not already present."""
    s = symbol.upper().strip()
    if s.endswith(_NSE_SUFFIX) or s.endswith(_BSE_SUFFIX):
        return s
    return s + _NSE_SUFFIX


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


class YFinanceProvider(MarketDataProvider):
    """Adapter over yfinance for NSE/BSE data."""

    def get_quote(self, symbol: str) -> dict[str, Any]:
        import yfinance as yf
        ticker = yf.Ticker(_ns(symbol))
        try:
            fi = ticker.fast_info
            price = _safe_float(fi.last_price)
            prev  = _safe_float(fi.previous_close) or price
            chg   = price - prev
            chg_p = (chg / prev * 100) if prev else 0.0
            return {
                "symbol":     symbol.upper(),
                "price":      price,
                "change":     round(chg, 2),
                "change_pct": round(chg_p, 2),
                "volume":     int(_safe_float(fi.three_month_average_volume)),
                "high":       _safe_float(fi.day_high),
                "low":        _safe_float(fi.day_low),
                "prev_close": prev,
                "source":     "yfinance",
            }
        except Exception as exc:
            return {
                "symbol": symbol.upper(), "price": 0.0, "change": 0.0,
                "change_pct": 0.0, "volume": 0, "high": 0.0, "low": 0.0,
                "prev_close": 0.0, "source": "yfinance", "error": str(exc),
            }

    def get_quotes_bulk(
        self, symbols: list[str], timeout_s: float = 8.0
    ) -> dict[str, dict[str, Any]]:
        """Fetch quotes for many tickers in parallel, capped at timeout_s."""
        results: dict[str, dict[str, Any]] = {}
        if not symbols:
            return results

        futures = {_executor.submit(self.get_quote, s): s for s in symbols}
        done, _ = wait(futures, timeout=timeout_s)
        for fut in done:
            sym = futures[fut]
            try:
                results[sym.upper()] = fut.result()
            except Exception:
                pass
        return results

    def get_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        import yfinance as yf
        import pandas as pd
        try:
            df: pd.DataFrame = yf.download(
                _ns(symbol), period=period, interval=interval,
                auto_adjust=True, progress=False
            )
            if df.empty:
                return []
            rows = []
            for ts, row in df.iterrows():
                rows.append({
                    "date":   ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                    "open":   round(_safe_float(row["Open"]), 2),
                    "high":   round(_safe_float(row["High"]), 2),
                    "low":    round(_safe_float(row["Low"]), 2),
                    "close":  round(_safe_float(row["Close"]), 2),
                    "volume": int(_safe_float(row["Volume"])),
                })
            return rows
        except Exception:
            return []

    def get_market_status(self) -> dict[str, Any]:
        from datetime import timezone
        from zoneinfo import ZoneInfo
        IST = ZoneInfo("Asia/Kolkata")
        now = datetime.now(IST)
        weekday = now.weekday()   # 0=Mon … 4=Fri, 5=Sat, 6=Sun
        hour = now.hour + now.minute / 60
        is_open = weekday < 5 and 9.25 <= hour < 15.5
        return {
            "is_open": is_open,
            "session": "regular" if is_open else "closed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "yfinance",
        }

    def name(self) -> str:
        return "yfinance"
