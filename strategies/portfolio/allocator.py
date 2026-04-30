"""Dynamic capital allocator — weights strategies by rolling Sharpe."""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from data.storage import db


BASE_ALLOCATION = {
    "momentum_st": 0.25,
    "momentum_mt": 0.25,
    "mean_reversion": 0.20,
    "factor": 0.25,
    "event": 0.05,
}


class StrategyAllocator:
    """
    Dynamically weights strategy capital allocations based on recent Sharpe.
    Rebalances quarterly. Falls back to BASE_ALLOCATION if insufficient history.
    """

    def __init__(self, lookback_days: int = 63, min_history_days: int = 42):
        self.lookback_days = lookback_days
        self.min_history_days = min_history_days

    def get_weights(self) -> dict[str, float]:
        """Return current strategy allocation weights (sum to 1.0)."""
        sharpes = self._compute_strategy_sharpes()

        if not sharpes or len(sharpes) < 2:
            logger.info("Insufficient Sharpe history, using base allocation")
            return BASE_ALLOCATION.copy()

        # Scale weights proportional to max(0, Sharpe) — penalize negative Sharpe
        weights = {}
        for strategy, sharpe in sharpes.items():
            base = BASE_ALLOCATION.get(strategy, 0.0)
            scaled = base * max(0.5, min(1.5, 1 + sharpe * 0.2))
            weights[strategy] = scaled

        # Add base allocation for strategies without history
        for strategy, base_w in BASE_ALLOCATION.items():
            if strategy not in weights:
                weights[strategy] = base_w

        # Normalize
        total = sum(weights.values())
        return {s: w / total for s, w in weights.items()}

    def _compute_strategy_sharpes(self) -> dict[str, float]:
        """Query backtest_results for rolling Sharpe of each strategy."""
        try:
            df = db.query_df("""
                SELECT strategy, sharpe_ratio, run_date
                FROM backtest_results
                WHERE run_date >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY strategy, run_date DESC
            """)
            if df.empty:
                return {}
            # Latest Sharpe per strategy
            latest = df.groupby("strategy").first()
            return latest["sharpe_ratio"].to_dict()
        except Exception as e:
            logger.debug(f"Strategy Sharpe lookup failed: {e}")
            return {}

    @staticmethod
    def get_base_allocation() -> dict[str, float]:
        return BASE_ALLOCATION.copy()
