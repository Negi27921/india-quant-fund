"""Abstract base classes (interfaces) for all provider types.

Every concrete provider implements one of these ABCs.  The rest of the
codebase only imports and calls these interfaces — swapping the underlying
implementation requires only a registry change, not a code change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ── Market Data ───────────────────────────────────────────────────────────────

class MarketDataProvider(ABC):
    """Provides real-time and historical price data for Indian equities."""

    @abstractmethod
    def get_quote(self, symbol: str) -> dict[str, Any]:
        """Return a single ticker quote.

        Keys: symbol, price, change, change_pct, volume, high, low, prev_close
        """

    @abstractmethod
    def get_quotes_bulk(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Return quotes for many tickers in one call.

        Returns: {symbol: quote_dict}
        """

    @abstractmethod
    def get_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        """Return OHLCV history.

        Each row: {date, open, high, low, close, volume}
        """

    @abstractmethod
    def get_market_status(self) -> dict[str, Any]:
        """Return current market session status.

        Keys: is_open, session, timestamp
        """

    def name(self) -> str:
        return self.__class__.__name__


# ── AI / LLM ─────────────────────────────────────────────────────────────────

class AIProvider(ABC):
    """Provides LLM completions for chat, analysis, and agent tasks."""

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Return a completion string."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""

    def name(self) -> str:
        return self.__class__.__name__


# ── Cache ─────────────────────────────────────────────────────────────────────

class CacheProvider(ABC):
    """Key-value cache with TTL support."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Return cached value or None if missing / expired."""

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Store value with a TTL."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove a key."""

    @abstractmethod
    def clear(self) -> None:
        """Flush all keys (use carefully)."""

    def name(self) -> str:
        return self.__class__.__name__


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationProvider(ABC):
    """Sends alerts and reports to configured channels."""

    @abstractmethod
    def send(
        self,
        message: str,
        title: str = "",
        level: str = "info",   # "info" | "warning" | "error"
        **kwargs: Any,
    ) -> bool:
        """Send a notification.  Returns True on success."""

    def name(self) -> str:
        return self.__class__.__name__


# ── Broker / Execution ────────────────────────────────────────────────────────

class BrokerProvider(ABC):
    """Executes orders and reports positions via a broker API."""

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,          # "BUY" | "SELL"
        quantity: int,
        order_type: str,    # "MARKET" | "LIMIT"
        price: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit an order.  Returns order status dict."""

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """Return open positions."""

    @abstractmethod
    def get_orders(self) -> list[dict[str, Any]]:
        """Return today's orders."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if credentials are set and connection is healthy."""

    def name(self) -> str:
        return self.__class__.__name__
