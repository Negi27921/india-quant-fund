"""Dhan broker client — wraps dhanhq SDK for NSE cash delivery orders."""
from __future__ import annotations

import os
from typing import Optional

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from execution.brokers.base import (
    BrokerInterface, BrokerOrder, BrokerOrderResult,
    BrokerOrderStatus, BrokerPosition, OrderStatus, ProductType,
)

try:
    from dhanhq import dhanhq
    HAS_DHANHQ = True
except ImportError:
    HAS_DHANHQ = False
    logger.warning("dhanhq not installed — Dhan broker unavailable")


NSE_SECURITY_IDS: dict[str, str] = {}  # Cache: ticker → Dhan security ID


class DhanBroker(BrokerInterface):
    name = "dhan"

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
    ):
        self._client_id = client_id or os.getenv("DHAN_CLIENT_ID", "")
        self._access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN", "")
        self._client: Optional["dhanhq"] = None
        self._paper_mode = os.getenv("PAPER_TRADING", "true").lower() == "true"

    def _get_client(self) -> "dhanhq":
        if self._client is None:
            if not HAS_DHANHQ:
                raise RuntimeError("dhanhq package not installed")
            self._client = dhanhq(self._client_id, self._access_token)
        return self._client

    def is_healthy(self) -> bool:
        try:
            client = self._get_client()
            result = client.get_fund_limits()
            return isinstance(result, dict) and "data" in result
        except Exception as e:
            logger.warning(f"Dhan health check failed: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        if self._paper_mode:
            return self._paper_order(order)

        try:
            client = self._get_client()
            security_id = self._resolve_security_id(order.ticker)

            resp = client.place_order(
                security_id=security_id,
                exchange_segment=dhanhq.NSE if order.exchange == "NSE" else dhanhq.BSE,
                transaction_type=dhanhq.BUY if order.side.value == "BUY" else dhanhq.SELL,
                quantity=order.quantity,
                order_type=dhanhq.LIMIT if order.order_type.value == "LIMIT" else dhanhq.MARKET,
                product_type=dhanhq.CNC,
                price=order.price,
                trigger_price=order.trigger_price or 0,
                tag=order.tag[:20] if order.tag else "",
            )

            if resp.get("status") == "success":
                oid = resp["data"]["orderId"]
                logger.info(f"Dhan order placed: {oid} | {order.side} {order.quantity}x {order.ticker}")
                return BrokerOrderResult(
                    success=True,
                    broker_order_id=oid,
                    status=OrderStatus.SUBMITTED,
                    raw_response=resp,
                )
            else:
                error = resp.get("remarks", str(resp))
                logger.error(f"Dhan order failed: {error}")
                return BrokerOrderResult(success=False, error=error, raw_response=resp)

        except Exception as e:
            logger.error(f"Dhan place_order exception: {e}")
            return BrokerOrderResult(success=False, error=str(e))

    def cancel_order(self, broker_order_id: str) -> bool:
        if self._paper_mode:
            logger.info(f"[Paper] Cancel order {broker_order_id}")
            return True
        try:
            client = self._get_client()
            resp = client.cancel_order(broker_order_id)
            return resp.get("status") == "success"
        except Exception as e:
            logger.error(f"Dhan cancel order {broker_order_id}: {e}")
            return False

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        if self._paper_mode:
            return BrokerOrderStatus(
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_qty=100,
                avg_fill_price=0.0,
            )
        try:
            client = self._get_client()
            resp = client.get_order_by_id(broker_order_id)
            data = resp.get("data", {})
            status_map = {
                "PENDING": OrderStatus.PENDING,
                "TRANSIT": OrderStatus.SUBMITTED,
                "TRADED": OrderStatus.FILLED,
                "CANCELLED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "PART_TRADED": OrderStatus.PARTIALLY_FILLED,
            }
            status = status_map.get(data.get("orderStatus", ""), OrderStatus.PENDING)
            return BrokerOrderStatus(
                broker_order_id=broker_order_id,
                status=status,
                filled_qty=int(data.get("filledQty", 0) or 0),
                avg_fill_price=float(data.get("price", 0) or 0),
            )
        except Exception as e:
            logger.error(f"Dhan order status {broker_order_id}: {e}")
            return BrokerOrderStatus(
                broker_order_id=broker_order_id,
                status=OrderStatus.FAILED,
                error=str(e),
            )

    def get_positions(self) -> list[BrokerPosition]:
        if self._paper_mode:
            return []
        try:
            client = self._get_client()
            resp = client.get_positions()
            positions = []
            for row in resp.get("data", []):
                if int(row.get("netQty", 0) or 0) == 0:
                    continue
                positions.append(BrokerPosition(
                    ticker=row.get("tradingSymbol", ""),
                    quantity=int(row.get("netQty", 0)),
                    avg_price=float(row.get("buyAvg", 0) or 0),
                    current_price=float(row.get("ltp", 0) or 0),
                    unrealized_pnl=float(row.get("unrealizedProfit", 0) or 0),
                ))
            return positions
        except Exception as e:
            logger.error(f"Dhan get_positions: {e}")
            return []

    def get_portfolio_value(self) -> float:
        if self._paper_mode:
            return 0.0
        try:
            client = self._get_client()
            resp = client.get_fund_limits()
            data = resp.get("data", {})
            return float(data.get("availabelBalance", 0) or 0)
        except Exception as e:
            logger.error(f"Dhan portfolio value: {e}")
            return 0.0

    def _resolve_security_id(self, ticker: str) -> str:
        if ticker in NSE_SECURITY_IDS:
            return NSE_SECURITY_IDS[ticker]
        return ticker  # Dhan accepts trading symbols directly in many cases

    def _paper_order(self, order: BrokerOrder) -> BrokerOrderResult:
        import uuid
        fake_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        logger.info(
            f"[Paper] {order.side} {order.quantity}x {order.ticker} "
            f"@ ₹{order.price:.2f} | id={fake_id}"
        )
        return BrokerOrderResult(
            success=True,
            broker_order_id=fake_id,
            status=OrderStatus.FILLED,
        )
