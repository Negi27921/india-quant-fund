"""RSI mean reversion strategy — large-cap only, trend filter."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class RSIMeanReversion(BaseStrategy):
    name = "mean_reversion"
    description = "RSI oversold/overbought with 200d SMA trend filter"

    DEFAULT_PARAMS = {
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "rsi_exit": 65,
        "trend_period": 200,
        "bb_period": 20,
        "bb_std": 2.0,
        "min_adv_cr": 20.0,   # Large-cap only
        "max_positions": 10,
        "stop_loss_pct": 3.0,
        "take_profit_pct": 5.0,
        "max_hold_days": 10,
    }

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__({**self.DEFAULT_PARAMS, **(params or {})})

    def generate(self, data, features=None, fundamentals=None) -> dict[str, float]:
        signals: dict[str, float] = {}
        min_data = max(self.params["trend_period"], self.params["rsi_period"]) + 5

        for ticker, df in data.items():
            if df is None or len(df) < min_data:
                continue
            try:
                score = self._compute_score(df)
                if score is not None and score > 0:
                    signals[ticker] = score
            except Exception:
                continue

        return signals

    def _compute_score(self, df: pd.DataFrame) -> float | None:
        close = df["close"]
        rsi_period = self.params["rsi_period"]
        trend_period = self.params["trend_period"]
        oversold = self.params["rsi_oversold"]

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        if pd.isna(current_rsi):
            return None

        # Trend filter: price must be above 200d SMA
        sma_200 = close.rolling(trend_period).mean()
        if close.iloc[-1] <= sma_200.iloc[-1]:
            return None  # Downtrend — no mean reversion buys

        # Bollinger Band confirmation
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_lower = bb_mid - self.params["bb_std"] * bb_std
        price_below_bb = close.iloc[-1] < bb_lower.iloc[-1]

        # Generate signal
        if current_rsi <= oversold:
            # Score: inversely proportional to RSI (lower RSI = stronger buy)
            score = (oversold - current_rsi) / oversold
            if price_below_bb:
                score *= 1.2  # Strengthen signal with BB confirmation
            return float(min(score, 1.0))
        return None

    def should_exit(self, ticker: str, df: pd.DataFrame) -> bool:
        """Return True if RSI has recovered to exit threshold."""
        if df is None or len(df) < self.params["rsi_period"]:
            return False
        close = df["close"]
        rsi_period = self.params["rsi_period"]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) >= self.params["rsi_exit"]
