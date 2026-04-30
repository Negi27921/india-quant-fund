"""Position sizing — vol-targeted half-Kelly."""
from __future__ import annotations

import numpy as np

from risk.limits import RiskLimits


class PositionSizer:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def size(
        self,
        portfolio_value: float,
        signal_strength: float,    # 0.0 to 1.0
        stock_volatility: float,   # annualized, e.g., 0.30
        vol_target: float | None = None,
        kelly_fraction: float = 0.5,
    ) -> float:
        """
        Returns target position value in ₹.
        vol_target: annual portfolio vol target (default from limits)
        """
        if portfolio_value <= 0 or stock_volatility <= 0:
            return 0.0

        target_vol = vol_target or (self.limits.portfolio.vol_target_annual_pct / 100)

        # Vol-targeted base size
        vol_scaled = (target_vol / stock_volatility) * portfolio_value

        # Half-Kelly on signal strength
        position_value = vol_scaled * signal_strength * kelly_fraction

        # Hard cap at max position %
        max_value = portfolio_value * (self.limits.position.max_single_stock_pct / 100)

        return min(position_value, max_value)

    def shares(
        self,
        position_value: float,
        price: float,
        round_lot: int = 1,
    ) -> int:
        """Convert position value to number of shares, rounded to lot size."""
        if price <= 0:
            return 0
        qty = int(position_value / price / round_lot) * round_lot
        return max(qty, 0)

    def vix_scale(self, vix: float) -> float:
        """Scale down position sizing when VIX is high."""
        reduce_t = self.limits.circuit.vix_india_reduce_threshold
        halt_t = self.limits.circuit.vix_india_halt_threshold
        if vix >= halt_t:
            return 0.0
        if vix >= reduce_t:
            # Linear scale: 1.0 at reduce_t, 0.0 at halt_t
            return 1.0 - (vix - reduce_t) / (halt_t - reduce_t)
        return 1.0
