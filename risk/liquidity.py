"""Liquidity filter — ADV-based order size limits."""
from __future__ import annotations

import pandas as pd
from loguru import logger

from risk.limits import RiskLimits


class LiquidityFilter:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def check(
        self,
        ticker: str,
        quantity: int,
        price: float,
        features: dict | pd.DataFrame | None = None,
    ) -> tuple[bool, str]:
        """Returns (ok, reason). ok=False means order should be rejected."""
        if features is None:
            return True, ""  # Cannot check, pass through

        adv_cr = self._get_adv(ticker, features)
        if adv_cr is None:
            return True, ""  # No data, pass through

        order_value_cr = quantity * price / 1e7
        max_participation = self.limits.liquidity.max_order_as_pct_of_10d_adv / 100

        if order_value_cr > adv_cr * max_participation:
            return False, (
                f"{ticker}: order ₹{order_value_cr:.2f}Cr exceeds "
                f"{max_participation:.0%} of ADV ₹{adv_cr:.2f}Cr"
            )

        min_adv = self.limits.liquidity.min_adv_cr
        if adv_cr < min_adv:
            return False, f"{ticker}: ADV ₹{adv_cr:.2f}Cr below minimum ₹{min_adv:.1f}Cr"

        return True, ""

    def _get_adv(self, ticker: str, features) -> float | None:
        try:
            if isinstance(features, dict):
                feat = features.get(ticker)
                if feat is None or feat.empty:
                    return None
                return float(feat["adv_20d"].iloc[-1]) / 1e7  # Convert ₹ to Cr
            elif isinstance(features, pd.DataFrame):
                if ticker in features.index and "adv_20d" in features.columns:
                    return float(features.loc[ticker, "adv_20d"]) / 1e7
        except Exception:
            pass
        return None
