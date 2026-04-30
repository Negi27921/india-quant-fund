"""Order Management System — full order lifecycle, idempotency, retry."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from loguru import logger

from data.storage import db
from execution.brokers.base import BrokerOrder, OrderSide, OrderStatus, OrderType, ProductType
from execution.router import SmartOrderRouter
from execution.slippage import SlippageModel


class OMS:
    """
    Manages the full order lifecycle:
    CREATED → VALIDATED → SUBMITTED → ACKNOWLEDGED → FILLED | CANCELLED | FAILED

    Idempotency: duplicate orders identified by (strategy + date + ticker + side)
    are silently dropped.
    """

    def __init__(self, router: SmartOrderRouter):
        self.router = router
        self.slippage = SlippageModel()
        self._daily_orders: dict[str, str] = {}  # idempotency_key → order_id

    def submit(
        self,
        ticker: str,
        side: str,                  # 'BUY' | 'SELL'
        quantity: int,
        price: float,
        order_type: str = "LIMIT",  # 'LIMIT' | 'MARKET'
        strategy: str = "system",
        exchange: str = "NSE",
        tag: str = "",
        limit_price: float | None = None,
    ) -> str:
        """Submit an order. Returns order_id."""
        order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        idem_key = f"{strategy}:{datetime.now().date()}:{ticker}:{side}"

        # Idempotency check
        if idem_key in self._daily_orders:
            logger.warning(f"Duplicate order detected for {idem_key}, skipping")
            return self._daily_orders[idem_key]

        actual_price = limit_price or price
        if order_type == "LIMIT" and side == "BUY":
            # Slightly above ask for certainty
            actual_price = price * 1.001
        elif order_type == "LIMIT" and side == "SELL":
            actual_price = price * 0.999

        # Store in DB
        db.execute("""
            INSERT INTO orders (
                order_id, idempotency_key, ticker, exchange, side, order_type,
                quantity, limit_price, product, strategy, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            order_id, idem_key, ticker, exchange, side, order_type,
            quantity, actual_price, "CNC", strategy, "CREATED", datetime.now(),
        ])

        self._daily_orders[idem_key] = order_id

        # Build broker order
        broker_order = BrokerOrder(
            ticker=ticker,
            exchange=exchange,
            side=OrderSide(side),
            order_type=OrderType(order_type),
            quantity=quantity,
            price=actual_price,
            product=ProductType.CNC,
            tag=tag or strategy[:20],
        )

        # Submit via router
        result = self.router.submit(broker_order)

        if result.success:
            db.execute("""
                UPDATE orders SET
                    status = ?, broker = ?, broker_order_id = ?, submitted_at = ?
                WHERE order_id = ?
            """, [
                OrderStatus.SUBMITTED.value,
                self.router.last_broker_used,
                result.broker_order_id,
                datetime.now(),
                order_id,
            ])
            logger.info(f"OMS submitted {order_id}: {side} {quantity}x {ticker} via {self.router.last_broker_used}")
        else:
            db.execute("""
                UPDATE orders SET status = ?, error_message = ? WHERE order_id = ?
            """, [OrderStatus.FAILED.value, result.error, order_id])
            logger.error(f"OMS submission failed {order_id}: {result.error}")

        return order_id

    def poll_fills(self) -> list[str]:
        """Poll all SUBMITTED orders for fill status. Returns list of filled order IDs."""
        pending = db.query_df("""
            SELECT order_id, broker, broker_order_id, quantity, limit_price, ticker, side
            FROM orders
            WHERE status IN ('SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED')
        """)

        filled_ids = []
        for _, row in pending.iterrows():
            bid = row["broker_order_id"]
            if not bid:
                continue
            try:
                status = self.router.get_status(bid, row["broker"])
                if status.status == OrderStatus.FILLED:
                    db.execute("""
                        UPDATE orders SET
                            status = ?, filled_quantity = ?, avg_fill_price = ?, filled_at = ?
                        WHERE order_id = ?
                    """, [
                        OrderStatus.FILLED.value,
                        status.filled_qty,
                        status.avg_fill_price,
                        datetime.now(),
                        row["order_id"],
                    ])
                    filled_ids.append(row["order_id"])
                    logger.info(f"Order {row['order_id']} FILLED: {status.filled_qty}x {row['ticker']} @ ₹{status.avg_fill_price:.2f}")
                elif status.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
                    db.execute("""
                        UPDATE orders SET status = ? WHERE order_id = ?
                    """, [status.status.value, row["order_id"]])
            except Exception as e:
                logger.warning(f"Poll fill failed for {bid}: {e}")

        return filled_ids

    def cancel_all_pending(self) -> int:
        """Cancel all pending/submitted orders. Used by kill switch."""
        pending = db.query_df("""
            SELECT order_id, broker, broker_order_id FROM orders
            WHERE status IN ('CREATED', 'SUBMITTED', 'ACKNOWLEDGED', 'PARTIALLY_FILLED')
        """)
        cancelled = 0
        for _, row in pending.iterrows():
            try:
                ok = self.router.cancel(row["broker_order_id"], row["broker"])
                if ok:
                    db.execute(
                        "UPDATE orders SET status = ?, cancelled_at = ? WHERE order_id = ?",
                        [OrderStatus.CANCELLED.value, datetime.now(), row["order_id"]],
                    )
                    cancelled += 1
            except Exception as e:
                logger.error(f"Cancel failed for {row['order_id']}: {e}")

        logger.info(f"Cancelled {cancelled}/{len(pending)} pending orders")
        return cancelled

    def cancel_stale_orders(self, timeout_minutes: int = 30) -> int:
        """Cancel orders that have been pending too long (end-of-day cleanup)."""
        cutoff = datetime.now().timestamp() - timeout_minutes * 60
        pending = db.query_df(f"""
            SELECT order_id, broker, broker_order_id FROM orders
            WHERE status IN ('SUBMITTED', 'ACKNOWLEDGED')
            AND epoch(submitted_at) < {cutoff}
        """)
        cancelled = 0
        for _, row in pending.iterrows():
            try:
                self.router.cancel(row["broker_order_id"], row["broker"])
                db.execute(
                    "UPDATE orders SET status = 'CANCELLED' WHERE order_id = ?",
                    [row["order_id"]],
                )
                cancelled += 1
            except Exception:
                pass
        return cancelled

    def reset_daily(self) -> None:
        self._daily_orders.clear()


def is_t1_eligible(buy_date: "date", sell_date: "date") -> bool:
    """
    Returns True if a CNC position bought on buy_date can be sold on sell_date.
    Indian equity T+1 settlement: cannot sell on the same day as buy.
    """
    from datetime import date as _date
    return sell_date > buy_date
