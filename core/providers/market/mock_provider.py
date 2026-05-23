"""Mock market data provider for local dev and CI testing.

Returns deterministic, realistic-looking data without any network calls.
Activate with: MARKET_PROVIDER=mock
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from core.providers.base import MarketDataProvider


class MockMarketProvider(MarketDataProvider):
    """Returns deterministic fake data — useful for dev/test without network."""

    _PRICES: dict[str, float] = {
        "RELIANCE": 2850.0, "TCS": 3900.0, "INFY": 1550.0, "HDFCBANK": 1650.0,
        "ICICIBANK": 1020.0, "WIPRO": 415.0, "AXISBANK": 1100.0, "BAJFINANCE": 6900.0,
        "SBIN": 730.0, "MARUTI": 9800.0, "NIFTY50": 24000.0, "SENSEX": 79000.0,
    }

    def _price(self, symbol: str) -> float:
        base = self._PRICES.get(symbol.upper(), 500.0)
        seed = sum(ord(c) for c in symbol) + int(datetime.now().strftime("%H%M")) // 5
        rng = random.Random(seed)
        return round(base * (1 + rng.uniform(-0.02, 0.02)), 2)

    def get_quote(self, symbol: str) -> dict[str, Any]:
        sym = symbol.upper().replace(".NS", "").replace(".BO", "")
        price = self._price(sym)
        prev  = price * random.uniform(0.97, 1.03)
        chg   = price - prev
        return {
            "symbol":     sym,
            "price":      price,
            "change":     round(chg, 2),
            "change_pct": round(chg / prev * 100, 2),
            "volume":     random.randint(500_000, 5_000_000),
            "high":       round(price * 1.01, 2),
            "low":        round(price * 0.99, 2),
            "prev_close": round(prev, 2),
            "source":     "mock",
        }

    def get_quotes_bulk(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        return {s.upper(): self.get_quote(s) for s in symbols}

    def get_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 252, "2y": 504}.get(period, 252)
        sym = symbol.upper().replace(".NS", "").replace(".BO", "")
        base = self._PRICES.get(sym, 500.0)
        rows = []
        price = base * 0.7
        today = datetime.now(timezone.utc).date()
        for i in range(days, 0, -1):
            d = today - timedelta(days=i)
            if d.weekday() >= 5:
                continue
            price = price * (1 + random.gauss(0.0003, 0.012))
            o = round(price * random.uniform(0.995, 1.005), 2)
            h = round(price * random.uniform(1.000, 1.015), 2)
            lo = round(price * random.uniform(0.985, 1.000), 2)
            c = round(price, 2)
            rows.append({
                "date": d.isoformat(), "open": o, "high": h,
                "low": lo, "close": c, "volume": random.randint(500_000, 3_000_000),
            })
        return rows

    def get_market_status(self) -> dict[str, Any]:
        from zoneinfo import ZoneInfo
        IST = ZoneInfo("Asia/Kolkata")
        now = datetime.now(IST)
        hour = now.hour + now.minute / 60
        is_open = now.weekday() < 5 and 9.25 <= hour < 15.5
        return {
            "is_open": is_open, "session": "mock",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "mock",
        }

    def name(self) -> str:
        return "mock"
