"""Execution flow — places orders at market open (09:15 IST)."""
from __future__ import annotations

from datetime import date

from loguru import logger

from data.storage import db
from execution.oms import OMS
from execution.router import SmartOrderRouter
from monitoring.alerts import get_alerts
from monitoring.audit import AuditLogger
from risk.manager import RiskManager
from risk.limits import get_limits


def run_execution_flow(capital: float, target_date: date | None = None) -> dict:
    """
    Reads target portfolio from DB, computes trades, validates, executes.
    """
    target_date = target_date or date.today()
    alerts = get_alerts()
    limits = get_limits()

    # Load target portfolio
    target = db.query_df(f"""
        SELECT ticker, target_weight
        FROM target_portfolio
        WHERE date = '{target_date}'
    """)
    if target.empty:
        logger.warning("No target portfolio for today — skipping execution")
        return {"status": "skip", "reason": "No target portfolio"}

    # Load current positions
    current_pos = db.query_df("SELECT ticker, quantity, avg_buy_price FROM positions")
    current_weights = {}
    if not current_pos.empty:
        total_val = capital
        for _, row in current_pos.iterrows():
            current_weights[row["ticker"]] = (row["quantity"] * row["avg_buy_price"]) / total_val

    target_weights = dict(zip(target["ticker"], target["target_weight"]))

    # Setup components
    router = SmartOrderRouter()
    oms = OMS(router)
    risk_mgr = RiskManager(limits)

    # Register kill switch flatten callback
    risk_mgr.kill_switch.register_flatten_callback(lambda: oms.cancel_all_pending())
    risk_mgr.kill_switch.register_alert_callback(lambda msg: alerts.send_critical(msg))

    # Get live prices
    prices = _get_live_prices(list(set(list(target_weights.keys()) + list(current_weights.keys()))))

    # Compute trades
    all_tickers = set(target_weights.keys()) | set(current_weights.keys())
    sells = []
    buys = []

    for ticker in all_tickers:
        current_w = current_weights.get(ticker, 0)
        target_w = target_weights.get(ticker, 0)
        delta = target_w - current_w

        if abs(delta) < 0.005:
            continue  # Skip tiny trades

        if delta < 0:
            sells.append((ticker, delta))
        else:
            buys.append((ticker, delta))

    orders_placed = []
    orders_rejected = []

    # Process sells first (free up capital)
    for ticker, delta in sells:
        price = prices.get(ticker)
        if not price:
            continue
        qty = int(abs(delta) * capital / price)
        if qty < 1:
            continue
        validation = risk_mgr.validate_order(
            order_id=f"SELL-{ticker}-{target_date}",
            ticker=ticker,
            side="SELL",
            quantity=qty,
            price=price,
            strategy="rebalance",
            portfolio_value=capital,
            current_positions={},
        )
        if validation.approved:
            order_id = oms.submit(ticker=ticker, side="SELL", quantity=qty, price=price, strategy="rebalance")
            AuditLogger.order_submitted(order_id, ticker, "SELL", qty, price, "rebalance")
            orders_placed.append(order_id)
        else:
            AuditLogger.order_rejected(validation.order_id, ticker, validation.rejection_reason)
            orders_rejected.append({"ticker": ticker, "reason": validation.rejection_reason})

    # Process buys
    for ticker, delta in buys:
        if risk_mgr.is_halted():
            break
        price = prices.get(ticker)
        if not price:
            continue
        qty = int(delta * capital / price)
        if qty < 1:
            continue
        validation = risk_mgr.validate_order(
            order_id=f"BUY-{ticker}-{target_date}",
            ticker=ticker,
            side="BUY",
            quantity=qty,
            price=price,
            strategy="rebalance",
            portfolio_value=capital,
            current_positions={},
        )
        if validation.approved:
            actual_qty = validation.quantity
            order_id = oms.submit(ticker=ticker, side="BUY", quantity=actual_qty, price=price, strategy="rebalance")
            AuditLogger.order_submitted(order_id, ticker, "BUY", actual_qty, price, "rebalance")
            orders_placed.append(order_id)
        else:
            orders_rejected.append({"ticker": ticker, "reason": validation.rejection_reason})

    result = {
        "status": "ok",
        "date": str(target_date),
        "orders_placed": len(orders_placed),
        "orders_rejected": len(orders_rejected),
        "sells": len(sells),
        "buys": len(buys),
    }
    logger.info(f"Execution complete: {result}")
    return result


def _order_priority(order: dict) -> int:
    """SELLs get priority 0 (processed first), BUYs get 1."""
    return 0 if order.get("side") == "SELL" else 1


def _get_live_prices(tickers: list[str]) -> dict[str, float]:
    """Get latest close prices from DuckDB as proxy for live prices."""
    if not tickers:
        return {}
    ticker_list = "','".join(tickers)
    try:
        df = db.query_df(f"""
            SELECT ticker, close
            FROM ohlcv
            WHERE ticker IN ('{ticker_list}')
            AND date = (SELECT MAX(date) FROM ohlcv)
        """)
        return dict(zip(df["ticker"], df["close"]))
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        return {}
