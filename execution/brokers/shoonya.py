"""Shoonya broker client — fallback broker via NorenRestApiPy."""
from __future__ import annotations

import os
import time
from typing import Optional

from loguru import logger

from execution.brokers.base import (
    BrokerInterface, BrokerOrder, BrokerOrderResult,
    BrokerOrderStatus, BrokerPosition, OrderStatus,
)

try:
    from NorenRestApiPy.NorenApi import NorenApi
    HAS_SHOONYA = True
except ImportError:
    HAS_SHOONYA = False
    logger.warning("NorenRestApiPy not installed — Shoonya broker unavailable")


class ShoonyaBroker(BrokerInterface):
    name = "shoonya"

    def __init__(self):
        self._user = os.getenv("SHOONYA_USER", "")
        self._password = os.getenv("SHOONYA_PASSWORD", "")
        self._totp_secret = os.getenv("SHOONYA_TOTP_SECRET", "")
        self._vendor_code = os.getenv("SHOONYA_VENDOR_CODE", "")
        self._api_secret = os.getenv("SHOONYA_API_SECRET", "")
        self._imei = os.getenv("SHOONYA_IMEI", "abc1234")
        self._api: Optional["NorenApi"] = None
        self._logged_in = False
        self._paper_mode = os.getenv("PAPER_TRADING", "true").lower() == "true"

    def _login(self) -> bool:
        if self._logged_in:
            return True
        if not HAS_SHOONYA:
            return False
        try:
            import pyotp
            totp = pyotp.TOTP(self._totp_secret).now() if self._totp_secret else ""
            self._api = NorenApi(
                host="https://api.shoonya.com/NorenWClientTP/",
                websocket="wss://api.shoonya.com/NorenWSTP/",
            )
            resp = self._api.login(
                userid=self._user,
                password=self._password,
                twoFA=totp,
                vendor_code=self._vendor_code,
                api_secret=self._api_secret,
                imei=self._imei,
            )
            if resp and resp.get("stat") == "Ok":
                self._logged_in = True
                logger.info("Shoonya: login successful")
                return True
            logger.error(f"Shoonya login failed: {resp}")
            return False
        except Exception as e:
            logger.error(f"Shoonya login exception: {e}")
            return False

    def is_healthy(self) -> bool:
        if self._paper_mode:
            return True
        return self._login()

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        if self._paper_mode:
            return self._paper_order(order)
        if not self._login():
            return BrokerOrderResult(success=False, error="Shoonya login failed")
        try:
            buy_or_sell = "B" if order.side.value == "BUY" else "S"
            prd_type = "C"  # CNC delivery
            order_type = "LMT" if order.order_type.value == "LIMIT" else "MKT"

            resp = self._api.place_order(
                buy_or_sell=buy_or_sell,
                product_type=prd_type,
                exchange="NSE",
                tradingsymbol=f"{order.ticker}-EQ",
                quantity=order.quantity,
                discloseqty=0,
                price_type=order_type,
                price=order.price,
                trigger_price=order.trigger_price or None,
                retention="DAY",
                remarks=order.tag[:20] if order.tag else "",
            )

            if resp and resp.get("stat") == "Ok":
                oid = resp.get("norenordno", "")
                logger.info(f"Shoonya order placed: {oid}")
                return BrokerOrderResult(
                    success=True,
                    broker_order_id=oid,
                    status=OrderStatus.SUBMITTED,
                    raw_response=resp,
                )
            error = resp.get("emsg", str(resp)) if resp else "No response"
            return BrokerOrderResult(success=False, error=error, raw_response=resp)

        except Exception as e:
            logger.error(f"Shoonya place_order: {e}")
            return BrokerOrderResult(success=False, error=str(e))

    def cancel_order(self, broker_order_id: str) -> bool:
        if self._paper_mode:
            return True
        try:
            resp = self._api.cancel_order(orderno=broker_order_id)
            return bool(resp and resp.get("stat") == "Ok")
        except Exception as e:
            logger.error(f"Shoonya cancel {broker_order_id}: {e}")
            return False

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatus:
        if self._paper_mode:
            return BrokerOrderStatus(broker_order_id=broker_order_id, status=OrderStatus.FILLED)
        try:
            resp = self._api.single_order_history(orderno=broker_order_id)
            if resp and isinstance(resp, list):
                latest = resp[-1]
                status_map = {
                    "COMPLETE": OrderStatus.FILLED,
                    "OPEN": OrderStatus.SUBMITTED,
                    "CANCELED": OrderStatus.CANCELLED,
                    "REJECTED": OrderStatus.REJECTED,
                }
                status = status_map.get(latest.get("status", ""), OrderStatus.PENDING)
                return BrokerOrderStatus(
                    broker_order_id=broker_order_id,
                    status=status,
                    filled_qty=int(latest.get("fillshares", 0) or 0),
                    avg_fill_price=float(latest.get("avgprc", 0) or 0),
                )
        except Exception as e:
            logger.error(f"Shoonya order status {broker_order_id}: {e}")
        return BrokerOrderStatus(broker_order_id=broker_order_id, status=OrderStatus.FAILED)

    def get_positions(self) -> list[BrokerPosition]:
        if self._paper_mode:
            return []
        try:
            resp = self._api.get_positions()
            if not resp:
                return []
            positions = []
            for row in resp:
                qty = int(row.get("netqty", 0) or 0)
                if qty == 0:
                    continue
                positions.append(BrokerPosition(
                    ticker=row.get("tsym", "").replace("-EQ", ""),
                    quantity=qty,
                    avg_price=float(row.get("netupldprc", 0) or 0),
                    current_price=float(row.get("lp", 0) or 0),
                    unrealized_pnl=float(row.get("urmtom", 0) or 0),
                ))
            return positions
        except Exception as e:
            logger.error(f"Shoonya get_positions: {e}")
            return []

    def get_portfolio_value(self) -> float:
        if self._paper_mode:
            return 0.0
        try:
            resp = self._api.get_limits()
            if resp and resp.get("stat") == "Ok":
                return float(resp.get("cash", 0) or 0)
        except Exception as e:
            logger.error(f"Shoonya portfolio value: {e}")
        return 0.0

    def _paper_order(self, order: BrokerOrder) -> BrokerOrderResult:
        import uuid
        fake_id = f"SHO-{uuid.uuid4().hex[:8].upper()}"
        logger.info(f"[Paper/Shoonya] {order.side} {order.quantity}x {order.ticker} @ ₹{order.price:.2f}")
        return BrokerOrderResult(success=True, broker_order_id=fake_id, status=OrderStatus.FILLED)
