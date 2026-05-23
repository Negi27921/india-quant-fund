"""Kite Connect (Zerodha) broker client.

Env vars required for live trading:
    KITE_API_KEY      — from Zerodha developer console
    KITE_ACCESS_TOKEN — refreshed daily via /api/auth/kite/callback
    KITE_API_SECRET   — used to generate access token (kept server-side only)

Paper mode (default) is active when PAPER_TRADING=true or ENABLE_LIVE_TRADING=false.
"""
from __future__ import annotations

import os
from typing import Optional

from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from execution.brokers.base import (
    BrokerInterface, BrokerOrder, BrokerOrderResult,
    BrokerOrderStatus, BrokerPosition, OrderStatus, OrderType,
)

try:
    from kiteconnect import KiteConnect
    HAS_KITE = True
except ImportError:
    HAS_KITE = False
    logger.warning("kiteconnect not installed — Kite broker unavailable (pip install kiteconnect)")


_KITE_STATUS_MAP = {
    "PUT ORDER REQ RECEIVED": OrderStatus.SUBMITTED,
    "VALIDATION PENDING":     OrderStatus.SUBMITTED,
    "OPEN PENDING":           OrderStatus.PENDING,
    "OPEN":                   OrderStatus.ACKNOWLEDGED,
    "COMPLETE":               OrderStatus.FILLED,
    "CANCELLED":              OrderStatus.CANCELLED,
    "REJECTED":               OrderStatus.REJECTED,
    "AMO REQ RECEIVED":       OrderStatus.SUBMITTED,
    "TRIGGER PENDING":        OrderStatus.PENDING,
}


class KiteBroker(BrokerInterface):
    """Zerodha Kite Connect v3 broker implementation.

    Supports NSE CNC (delivery) orders only. Intraday / F&O not used.
    Access tokens expire at 06:00 IST daily — caller must refresh before market open.
    """

    name = "kite"

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
    ):
        self._api_key = api_key or os.getenv("KITE_API_KEY", "")
        self._access_token = access_token or os.getenv("KITE_ACCESS_TOKEN", "")
        self._paper_mode = (
            os.getenv("PAPER_TRADING", "true").lower() == "true"
            or os.getenv("ENABLE_LIVE_TRADING", "false").lower() != "true"
        )
        self._client: Optional["KiteConnect"] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _get_client(self) -> "KiteConnect":
        if not HAS_KITE:
            raise RuntimeError("kiteconnect package not installed — run: pip install kiteconnect")
        if not self._api_key:
            raise RuntimeError("KITE_API_KEY not set")
        if not self._access_token:
            raise RuntimeError("KITE_ACCESS_TOKEN not set (refresh daily before market open)")
        if self._client is None:
            self._client = KiteConnect(api_key=self._api_key)
            self._client.set_access_token(self._access_token)
        return self._client

    def refresh_token(self, request_token: str, api_secret: str) -> str:
        """Exchange a login request_token for an access_token. Call once per day."""
        if not HAS_KITE:
            raise RuntimeError("kiteconnect package not installed")
        kite = KiteConnect(api_key=self._api_key)
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        self._access_token = access_token
        if self._client is not None:
            self._client.set_access_token(access_token)
        return access_token

    # ── Health ────────────────────────────────────────────────────────────────

    def is_healthy(self) -> bool:
        if self._paper_mode:
            return True
        try:
            profile = self._get_client().profile()
            return bool(profile.get("user_id"))
        except Exception as e:
            logger.warning(f"Kite health check failed: {e}")
            return False

    # ── Orders ────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        if self._paper_mode:
            return self._paper_order(order)

        try:
            kite = self._get_client()

            variety = KiteConnect.VARIETY_REGULAR
            exchange = KiteConnect.EXCHANGE_NSE if order.exchange == "NSE" else KiteConnect.EXCHANGE_BSE
            transaction = KiteConnect.TRANSACTION_TYPE_BUY if order.side.value == "BUY" else KiteConnect.TRANSACTION_TYPE_SELL
            product = KiteConnect.PRODUCT_CNC

            order_type_map = {
                OrderType.MARKET: KiteConnect.ORDER_TYPE_MARKET,
                OrderType.LIMIT:  KiteConnect.ORDER_TYPE_LIMIT,
                OrderType.SL:     KiteConnect.ORDER_TYPE_SL,
                OrderType.SLM:    KiteConnect.ORDER_TYPE_SLM,
            }
            kite_order_type = order_type_map.get(order.order_type, KiteConnect.ORDER_TYPE_MARKET)

            tag = order.tag[:20] if order.tag else ""

            order_id = kite.place_order(
                variety=variety,
                exchange=exchange,
                tradingsymbol=order.ticker.replace(".NS", "").replace(".BO", ""),
                transaction_type=transaction,
                quantity=order.quantity,
                product=product,
                order_type=kite_order_type,
                price=order.price if order.order_type == OrderType.LIMIT else None,
                trigger_price=order.trigger_price if order.trigger_price > 0 else None,
                tag=tag or None,
            )

            logger.info(f"Kite order placed: {order_id} | {order.side} {order.quantity}x {order.ticker}")
            return BrokerOrderResult(
                success=True,
                broker_order_id=str(order_id),
                status=OrderStatus.SUBMITTED,
            )

        except Exception as e:
            logger.error(f"Kite place_order exception: {e}")
            return BrokerOrderResult(success=False, error=str(e))

    def cancel_order(self, broker_order_id: str) -> bool:
        if self._paper_mode:
            logger.info(f"[Paper] Kite cancel order {broker_order_id}")
            return True
        try:
            self._get_client().cancel_order(
                variety=KiteConnect.VARIETY_REGULAR,
                order_id=broker_order_id,
            )
            return True
        except Exception as e:
            logger.error(f"Kite cancel order {broker_order_id}: {e}")
            return False

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        if self._paper_mode:
            return BrokerOrderStatus(
                broker_order_id=broker_order_id,
                status=OrderStatus.FILLED,
                filled_qty=1,
                avg_fill_price=0.0,
            )
        try:
            orders = self._get_client().order_history(broker_order_id)
            if not orders:
                return BrokerOrderStatus(broker_order_id=broker_order_id, status=OrderStatus.PENDING)
            latest = orders[-1]
            status = _KITE_STATUS_MAP.get(latest.get("status", ""), OrderStatus.PENDING)
            return BrokerOrderStatus(
                broker_order_id=broker_order_id,
                status=status,
                filled_qty=int(latest.get("filled_quantity", 0) or 0),
                avg_fill_price=float(latest.get("average_price", 0) or 0),
            )
        except Exception as e:
            logger.error(f"Kite order status {broker_order_id}: {e}")
            return BrokerOrderStatus(broker_order_id=broker_order_id, status=OrderStatus.FAILED, error=str(e))

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def get_positions(self) -> list[BrokerPosition]:
        if self._paper_mode:
            return []
        try:
            resp = self._get_client().positions()
            positions: list[BrokerPosition] = []
            for row in resp.get("net", []):
                qty = int(row.get("quantity", 0) or 0)
                if qty == 0:
                    continue
                positions.append(BrokerPosition(
                    ticker=row.get("tradingsymbol", ""),
                    quantity=qty,
                    avg_price=float(row.get("average_price", 0) or 0),
                    current_price=float(row.get("last_price", 0) or 0),
                    unrealized_pnl=float(row.get("unrealised_profit", 0) or 0),
                    product=row.get("product", "CNC"),
                ))
            return positions
        except Exception as e:
            logger.error(f"Kite get_positions: {e}")
            return []

    def get_portfolio_value(self) -> float:
        if self._paper_mode:
            return 0.0
        try:
            margins = self._get_client().margins(segment=KiteConnect.MARGIN_EQUITY)
            return float(margins.get("net", 0) or 0)
        except Exception as e:
            logger.error(f"Kite portfolio value: {e}")
            return 0.0

    # ── Quote (bonus — Kite is real-time, not 15-min delayed like yfinance) ──

    def get_ltp(self, instruments: list[str]) -> dict[str, float]:
        """Fetch real-time last-traded prices. instruments = ['NSE:RELIANCE', ...]"""
        if self._paper_mode:
            return {}
        try:
            resp = self._get_client().ltp(instruments)
            return {sym: float(data.get("last_price", 0)) for sym, data in resp.items()}
        except Exception as e:
            logger.error(f"Kite ltp({instruments[:3]}…): {e}")
            return {}

    # ── Paper mode ────────────────────────────────────────────────────────────

    def _paper_order(self, order: BrokerOrder) -> BrokerOrderResult:
        import uuid
        fake_id = f"KITE-PAPER-{uuid.uuid4().hex[:8].upper()}"
        logger.info(
            f"[Paper/Kite] {order.side} {order.quantity}x {order.ticker} "
            f"@ ₹{order.price:.2f} | id={fake_id}"
        )
        return BrokerOrderResult(
            success=True,
            broker_order_id=fake_id,
            status=OrderStatus.FILLED,
        )
