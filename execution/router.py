"""Smart order router — Dhan (primary) → Shoonya (failover)."""
from __future__ import annotations

import time
from typing import Optional

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from execution.brokers.base import (
    BrokerInterface, BrokerOrder, BrokerOrderResult, BrokerOrderStatus, OrderStatus,
)
from execution.brokers.dhan import DhanBroker
from execution.brokers.shoonya import ShoonyaBroker


class SmartOrderRouter:
    """
    Routes orders to the best available broker.
    Primary: Dhan. Failover: Shoonya.
    Switches automatically on failure, sends alert.
    """

    def __init__(
        self,
        primary: BrokerInterface | None = None,
        fallback: BrokerInterface | None = None,
    ):
        self.primary = primary or DhanBroker()
        self.fallback = fallback or ShoonyaBroker()
        self._active_broker: Optional[BrokerInterface] = None
        self._consecutive_failures: int = 0
        self.last_broker_used: str = ""

    def _get_broker(self) -> BrokerInterface:
        """Return the current best broker, with failover if needed."""
        if self._consecutive_failures >= 3:
            # Primary has failed 3 times — switch to fallback
            if self.fallback.is_healthy():
                logger.warning("Routing to fallback broker (Shoonya)")
                return self.fallback
            else:
                logger.error("Both brokers unhealthy!")
                return self.primary  # Try primary anyway

        if self.primary.is_healthy():
            return self.primary

        logger.warning("Primary broker (Dhan) unhealthy, trying fallback (Shoonya)")
        return self.fallback

    def submit(self, order: BrokerOrder) -> BrokerOrderResult:
        broker = self._get_broker()
        self.last_broker_used = broker.name

        result = broker.place_order(order)

        if result.success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            # If primary failed, try fallback
            if broker.name == self.primary.name and self.fallback.is_healthy():
                logger.warning(f"Primary failed, retrying on fallback: {result.error}")
                result = self.fallback.place_order(order)
                if result.success:
                    self.last_broker_used = self.fallback.name
                    self._consecutive_failures = 0

        return result

    def cancel(self, broker_order_id: str, broker_name: str) -> bool:
        broker = self.primary if broker_name == self.primary.name else self.fallback
        try:
            return broker.cancel_order(broker_order_id)
        except Exception as e:
            logger.error(f"Router cancel failed {broker_order_id}: {e}")
            return False

    def get_status(self, broker_order_id: str, broker_name: str) -> BrokerOrderStatus:
        broker = self.primary if broker_name == self.primary.name else self.fallback
        return broker.get_order_status(broker_order_id)

    def get_all_positions(self) -> list:
        positions = []
        try:
            positions.extend(self.primary.get_positions())
        except Exception as e:
            logger.warning(f"Primary positions failed: {e}")
        # Don't double-count by also fetching from fallback
        return positions

    def get_portfolio_value(self) -> float:
        try:
            return self.primary.get_portfolio_value()
        except Exception:
            try:
                return self.fallback.get_portfolio_value()
            except Exception:
                return 0.0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
