"""NSE India market data provider (via nsepython scraping).

Near-real-time for index data and FII/DII flows.
Fragile — NSE can block scrapers; yfinance is the fallback.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.providers.base import MarketDataProvider


class NSEProvider(MarketDataProvider):
    """Adapter over nsepython for official NSE data."""

    def __init__(self) -> None:
        try:
            from nsepython import nsefetch as _nf  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

    def _nsefetch(self, url: str) -> dict:
        from nsepython import nsefetch
        return nsefetch(url)

    def get_quote(self, symbol: str) -> dict[str, Any]:
        if not self._available:
            return {"symbol": symbol, "error": "nsepython not installed", "source": "nse"}
        try:
            data = self._nsefetch(
                f"https://www.nseindia.com/api/quote-equity?symbol={symbol.upper()}"
            )
            pd = data.get("priceInfo", {})
            price = float(pd.get("lastPrice", 0))
            prev  = float(pd.get("previousClose", price))
            chg   = price - prev
            chg_p = (chg / prev * 100) if prev else 0.0
            intradata = pd.get("intraDayHighLow", {})
            return {
                "symbol":     symbol.upper(),
                "price":      price,
                "change":     round(chg, 2),
                "change_pct": round(chg_p, 2),
                "volume":     int(data.get("marketDeptOrderBook", {}).get("totalTradedVolume", 0)),
                "high":       float(intradata.get("max", price)),
                "low":        float(intradata.get("min", price)),
                "prev_close": prev,
                "source":     "nse",
            }
        except Exception as exc:
            return {
                "symbol": symbol.upper(), "price": 0.0, "change": 0.0,
                "change_pct": 0.0, "volume": 0, "high": 0.0, "low": 0.0,
                "prev_close": 0.0, "source": "nse", "error": str(exc),
            }

    def get_quotes_bulk(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        return {s.upper(): self.get_quote(s) for s in symbols}

    def get_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        # NSE scraping for history is unreliable; delegate to yfinance
        from core.providers.market.yfinance_provider import YFinanceProvider
        return YFinanceProvider().get_history(symbol, period, interval)

    def get_market_status(self) -> dict[str, Any]:
        if not self._available:
            from core.providers.market.yfinance_provider import YFinanceProvider
            return YFinanceProvider().get_market_status()
        try:
            data = self._nsefetch("https://www.nseindia.com/api/marketStatus")
            markets = data.get("marketState", [])
            nse = next((m for m in markets if "NSE" in m.get("market", "")), {})
            is_open = nse.get("marketStatus", "").lower() == "open"
            return {
                "is_open": is_open,
                "session": nse.get("tradeDate", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "nse",
            }
        except Exception:
            from core.providers.market.yfinance_provider import YFinanceProvider
            return YFinanceProvider().get_market_status()

    def name(self) -> str:
        return "nse"
