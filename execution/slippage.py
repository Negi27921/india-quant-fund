"""Slippage estimation model — pre-trade cost estimation."""
from __future__ import annotations


class SlippageModel:
    """
    Pre-trade slippage estimate for Indian equity cash market.
    Components: half-spread + linear market impact.
    """

    def estimate(
        self,
        order_value: float,         # ₹ value of the order
        adv: float,                 # 10-day average daily value ₹
        bid_ask_spread_pct: float = 0.10,  # % spread, 10bps default
    ) -> float:
        """Returns estimated slippage as percentage of order value."""
        if adv <= 0:
            return bid_ask_spread_pct / 100

        participation = order_value / adv
        # Linear impact model: 10bps per 1% participation rate
        market_impact_pct = 0.001 * participation * 100
        half_spread_pct = bid_ask_spread_pct / 2 / 100

        return half_spread_pct + market_impact_pct

    def estimate_round_trip(self, order_value: float, adv: float) -> float:
        """Full round-trip slippage (buy + sell)."""
        return 2 * self.estimate(order_value, adv)

    def adjust_price(
        self,
        price: float,
        side: str,
        order_value: float,
        adv: float,
    ) -> float:
        """Return slippage-adjusted execution price."""
        slip = self.estimate(order_value, adv)
        if side.upper() == "BUY":
            return price * (1 + slip)
        return price * (1 - slip)
