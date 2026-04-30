"""Risk manager — single gate for all trade validations. Cannot be bypassed."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from loguru import logger

from data.pipeline.transformers.universe import get_sector, get_sector_exposure
from risk.drawdown import DrawdownMonitor
from risk.kill_switch import KillSwitch
from risk.limits import RiskLimits, get_limits
from risk.liquidity import LiquidityFilter
from risk.position_sizer import PositionSizer


@dataclass
class OrderValidation:
    approved: bool
    order_id: str
    ticker: str
    side: str
    quantity: int
    price: float
    rejection_reason: str = ""
    adjusted_quantity: int = 0
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class RiskManager:
    """
    Central risk gateway. Every order must pass through validate_order().
    Risk manager can: approve, reject, or adjust (reduce size) orders.
    Kill switch is always checked first.
    """

    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or get_limits()
        self.kill_switch = KillSwitch(self.limits)
        self.drawdown_monitor = DrawdownMonitor(self.limits)
        self.liquidity_filter = LiquidityFilter(self.limits)
        self.position_sizer = PositionSizer(self.limits)
        self._daily_order_count: int = 0
        self._daily_loss: float = 0.0
        self._last_reset_date: date = date.today()

    def validate_order(
        self,
        order_id: str,
        ticker: str,
        side: str,                  # 'BUY' | 'SELL'
        quantity: int,
        price: float,
        strategy: str,
        portfolio_value: float,
        current_positions: dict[str, dict],  # {ticker: {qty, weight, sector}}
        features: dict | None = None,
        circuit_limits: dict | None = None,
    ) -> OrderValidation:
        """
        Validate a single order against all risk limits.
        Returns OrderValidation with approved=True/False and reason.
        """
        self._reset_daily_counters()

        result = OrderValidation(
            approved=False,
            order_id=order_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
        )

        # 0. Kill switch (absolute first check)
        if self.kill_switch.is_triggered():
            result.rejection_reason = "Kill switch is active — no trading"
            logger.error(f"Order {order_id} REJECTED: kill switch active")
            return result

        # 1. Daily order count limit
        if self._daily_order_count >= self.limits.order.max_orders_per_day:
            result.rejection_reason = f"Daily order limit reached ({self.limits.order.max_orders_per_day})"
            return result

        # 2. Minimum order value
        order_value = quantity * price
        if order_value < self.limits.order.min_order_value:
            result.rejection_reason = f"Order value ₹{order_value:.0f} below minimum ₹{self.limits.order.min_order_value:.0f}"
            return result

        # 3. Position size limit
        pos_pct = order_value / portfolio_value * 100
        if side == "BUY" and pos_pct > self.limits.position.max_single_stock_pct:
            # Try to adjust quantity down
            max_value = portfolio_value * self.limits.position.max_single_stock_pct / 100
            adjusted_qty = int(max_value / price)
            if adjusted_qty < 1:
                result.rejection_reason = f"Position size {pos_pct:.1f}% exceeds limit {self.limits.position.max_single_stock_pct}%"
                return result
            result.adjusted_quantity = adjusted_qty
            result.warnings.append(f"Quantity reduced: {quantity} → {adjusted_qty} (size cap)")
            quantity = adjusted_qty

        # 4. Sector exposure check (BUY only)
        if side == "BUY":
            sector = get_sector(ticker)
            new_weight = order_value / portfolio_value
            current_sector_exp = self._current_sector_exposure(current_positions, portfolio_value)
            new_sector_total = current_sector_exp.get(sector, 0) + new_weight
            if new_sector_total * 100 > self.limits.sector.max_sector_exposure_pct:
                result.rejection_reason = (
                    f"Sector '{sector}' exposure {new_sector_total:.1%} would exceed "
                    f"limit {self.limits.sector.max_sector_exposure_pct}%"
                )
                return result

        # 5. Max positions check (BUY only)
        if side == "BUY":
            n_positions = len(current_positions)
            if n_positions >= self.limits.position.max_stocks_in_portfolio:
                result.rejection_reason = f"Max positions {self.limits.position.max_stocks_in_portfolio} reached"
                return result

        # 6. Liquidity check (BUY)
        if side == "BUY" and features:
            liq_ok, liq_reason = self.liquidity_filter.check(ticker, quantity, price, features)
            if not liq_ok:
                result.rejection_reason = liq_reason
                return result

        # 7. Circuit limit check
        if circuit_limits and ticker in circuit_limits:
            cl = circuit_limits[ticker]
            upper = cl.get("upper_circuit")
            lower = cl.get("lower_circuit")
            buffer = self.limits.circuit.nse_upper_circuit_buffer_pct / 100
            if side == "BUY" and upper and price >= upper * (1 - buffer):
                result.rejection_reason = f"{ticker} near upper circuit (₹{upper:.2f})"
                return result
            if side == "SELL" and lower and price <= lower * (1 + buffer):
                result.rejection_reason = f"{ticker} near lower circuit (₹{lower:.2f})"
                return result

        # 8. Drawdown check
        dd_ok, dd_reason = self.drawdown_monitor.check_can_trade(side)
        if not dd_ok:
            result.rejection_reason = dd_reason
            return result

        # 9. Daily loss limit
        daily_loss_pct = abs(self._daily_loss) / portfolio_value * 100
        if daily_loss_pct >= self.limits.drawdown.daily_loss_limit_pct:
            result.rejection_reason = (
                f"Daily loss {daily_loss_pct:.1f}% at limit {self.limits.drawdown.daily_loss_limit_pct}%"
            )
            return result

        # All checks passed
        result.approved = True
        result.quantity = quantity if result.adjusted_quantity == 0 else result.adjusted_quantity
        self._daily_order_count += 1

        logger.info(
            f"Order {order_id} APPROVED: {side} {result.quantity}x {ticker} @ ₹{price:.2f} "
            f"({strategy}) | warnings: {result.warnings}"
        )
        return result

    def record_pnl(self, pnl: float) -> None:
        """Record realized/unrealized PnL for daily tracking."""
        self._daily_loss += min(pnl, 0)  # Only count losses
        self.drawdown_monitor.update_pnl(pnl)

    def update_portfolio_value(self, value: float, peak_value: float) -> None:
        self.drawdown_monitor.update(value, peak_value)
        if self.drawdown_monitor.should_kill_switch():
            self.kill_switch.trigger("Drawdown kill switch threshold breached")

    def _reset_daily_counters(self) -> None:
        today = date.today()
        if today != self._last_reset_date:
            self._daily_order_count = 0
            self._daily_loss = 0.0
            self._last_reset_date = today

    def _current_sector_exposure(
        self,
        positions: dict[str, dict],
        portfolio_value: float,
    ) -> dict[str, float]:
        weights = {}
        for ticker, pos in positions.items():
            w = (pos.get("quantity", 0) * pos.get("price", 0)) / portfolio_value
            weights[ticker] = w
        return get_sector_exposure(weights)

    def is_halted(self) -> bool:
        return self.kill_switch.is_triggered()

    def reset_kill_switch(self, reason: str = "Manual reset") -> None:
        self.kill_switch.reset(reason)
