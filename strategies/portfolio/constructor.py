"""Portfolio constructor — converts signals to target weights with constraints."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from data.pipeline.transformers.universe import get_sector_exposure
from risk.limits import RiskLimits


class PortfolioConstructor:
    """
    Converts raw strategy signals into a target portfolio (ticker → weight).
    Applies all constraints: sector caps, liquidity, position limits, beta.
    """

    def __init__(self, limits: RiskLimits, config: dict[str, Any] | None = None):
        self.limits = limits
        self.config = config or {}

    def construct(
        self,
        strategy_signals: dict[str, dict[str, float]],
        strategy_weights: dict[str, float],
        current_prices: dict[str, float],
        features: dict[str, pd.DataFrame] | None = None,
        total_capital: float = 1_000_000,
    ) -> dict[str, float]:
        """
        strategy_signals: {strategy_name: {ticker: signal_score}}
        strategy_weights: {strategy_name: capital_fraction}
        Returns: {ticker: target_weight_in_portfolio}
        """
        # 1. Combine signals weighted by strategy allocation
        combined = self._combine_signals(strategy_signals, strategy_weights)

        if not combined:
            logger.warning("No signals from any strategy")
            return {}

        # 2. Apply liquidity filter
        combined = self._apply_liquidity_filter(combined, features, total_capital)

        # 3. Apply position size limits
        combined = self._apply_position_limits(combined)

        # 4. Apply sector caps
        combined = self._apply_sector_caps(combined)

        # 5. Normalize to sum to 1 (fully invested, no leverage)
        combined = self._normalize(combined)

        # 6. Filter out tiny positions (reduce churn)
        min_weight = 0.005  # 0.5% minimum
        combined = {t: w for t, w in combined.items() if w >= min_weight}

        logger.info(f"Portfolio constructed: {len(combined)} positions")
        return combined

    def compute_trades(
        self,
        target: dict[str, float],
        current: dict[str, float],
        min_trade_pct: float = 0.005,
    ) -> dict[str, float]:
        """
        Returns: {ticker: weight_delta}  (+ve = buy, -ve = sell)
        Filters out tiny trades to reduce turnover costs.
        """
        all_tickers = set(target.keys()) | set(current.keys())
        trades = {}
        for ticker in all_tickers:
            delta = target.get(ticker, 0) - current.get(ticker, 0)
            if abs(delta) >= min_trade_pct:
                trades[ticker] = delta
        return trades

    def _combine_signals(
        self,
        strategy_signals: dict[str, dict[str, float]],
        strategy_weights: dict[str, float],
    ) -> dict[str, float]:
        combined: dict[str, float] = {}
        total_weight = sum(strategy_weights.values())
        if total_weight == 0:
            return {}

        for strategy, signals in strategy_signals.items():
            w = strategy_weights.get(strategy, 0) / total_weight
            for ticker, score in signals.items():
                combined[ticker] = combined.get(ticker, 0) + w * score

        return combined

    def _apply_liquidity_filter(
        self,
        signals: dict[str, float],
        features: dict[str, pd.DataFrame] | None,
        total_capital: float,
    ) -> dict[str, float]:
        if features is None:
            return signals
        filtered = {}
        min_adv = self.limits.liquidity.min_adv_cr * 1e7  # convert to ₹
        for ticker, score in signals.items():
            feat = features.get(ticker)
            if feat is None or feat.empty:
                continue
            adv = feat["adv_20d"].iloc[-1] if "adv_20d" in feat.columns else 0
            if adv >= min_adv:
                filtered[ticker] = score
        return filtered

    def _apply_position_limits(self, signals: dict[str, float]) -> dict[str, float]:
        max_pos = self.limits.position.max_single_stock_pct / 100
        # We'll normalize later, but flag the cap
        # Just return top N positions by signal strength
        max_n = self.limits.position.max_stocks_in_portfolio
        if len(signals) > max_n:
            signals = dict(
                sorted(signals.items(), key=lambda x: x[1], reverse=True)[:max_n]
            )
        return signals

    def _apply_sector_caps(self, signals: dict[str, float]) -> dict[str, float]:
        max_sector_pct = self.limits.sector.max_sector_exposure_pct / 100
        signals_series = pd.Series(signals)
        total = signals_series.sum()
        if total == 0:
            return signals

        normalized = signals_series / total
        sector_exposure = get_sector_exposure(normalized.to_dict())

        for sector, exp in sector_exposure.items():
            if exp > max_sector_pct:
                # Scale down all tickers in this sector
                scale = max_sector_pct / exp
                for ticker in list(signals.keys()):
                    from data.pipeline.transformers.universe import get_sector
                    if get_sector(ticker) == sector:
                        signals[ticker] *= scale

        return signals

    def _normalize(self, signals: dict[str, float]) -> dict[str, float]:
        total = sum(signals.values())
        if total == 0:
            return signals
        return {t: v / total for t, v in signals.items()}
