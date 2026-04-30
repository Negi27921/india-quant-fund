"""Short-term momentum strategy (5–20 day price + volume confirmation)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class ShortTermMomentum(BaseStrategy):
    name = "momentum_st"
    description = "5–20 day price momentum with volume confirmation"

    DEFAULT_PARAMS = {
        "roc_fast": 5,
        "roc_slow": 20,
        "vol_fast": 5,
        "vol_slow": 60,
        "w_roc_fast": 0.40,
        "w_roc_slow": 0.40,
        "w_vol_ratio": 0.20,
        "entry_z": 1.28,         # Top decile threshold
        "exit_z": -0.25,         # Bottom quartile
        "min_price": 50.0,
        "min_adv_cr": 5.0,
        "lookback_z": 252,       # Z-score window
    }

    def __init__(self, params: dict[str, Any] | None = None):
        merged = {**self.DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged)

    def generate(self, data, features=None, fundamentals=None) -> dict[str, float]:
        signals: dict[str, float] = {}

        for ticker, df in data.items():
            if df is None or len(df) < self.params["roc_slow"] + 5:
                continue

            try:
                score = self._compute_score(df)
                if score is not None:
                    signals[ticker] = float(np.clip(score, -3, 3))
            except Exception:
                continue

        # Cross-sectional normalization to [0, 1]
        if not signals:
            return {}

        s = pd.Series(signals)
        entry_z = self.params["entry_z"]

        # Normalize: convert z-scores to 0–1 probabilities
        normalized = (s - s.min()) / (s.max() - s.min() + 1e-9)
        # Only pass stocks above entry threshold
        z_standardized = (s - s.mean()) / (s.std() + 1e-9)
        mask = z_standardized >= entry_z
        result = {}
        for ticker in signals:
            if mask.get(ticker, False):
                result[ticker] = float(normalized[ticker])
        return result

    def _compute_score(self, df: pd.DataFrame) -> float | None:
        close = df["close"]
        volume = df["volume"]
        n_fast = self.params["roc_fast"]
        n_slow = self.params["roc_slow"]
        v_fast = self.params["vol_fast"]
        v_slow = self.params["vol_slow"]

        if len(close) < n_slow + 1:
            return None

        # Price rate of change
        roc_fast = (close.iloc[-1] - close.iloc[-n_fast - 1]) / close.iloc[-n_fast - 1]
        roc_slow = (close.iloc[-1] - close.iloc[-n_slow - 1]) / close.iloc[-n_slow - 1]

        # Volume ratio (value-based)
        value = close * volume
        vol_fast_avg = value.iloc[-v_fast:].mean()
        vol_slow_avg = value.iloc[-v_slow:].mean()
        vol_ratio = vol_fast_avg / max(vol_slow_avg, 1)

        score = (
            self.params["w_roc_fast"] * roc_fast
            + self.params["w_roc_slow"] * roc_slow
            + self.params["w_vol_ratio"] * (vol_ratio - 1)
        )
        return score

    def should_exit(self, ticker: str, data: dict[str, pd.DataFrame]) -> bool:
        """Check exit condition for an existing position."""
        df = data.get(ticker)
        if df is None or len(df) < 5:
            return False
        score = self._compute_score(df)
        if score is None:
            return False
        all_scores = {t: self._compute_score(d) for t, d in data.items() if d is not None}
        all_scores = {t: v for t, v in all_scores.items() if v is not None}
        if not all_scores:
            return False
        s = pd.Series(all_scores)
        z = (score - s.mean()) / (s.std() + 1e-9)
        return z < self.params["exit_z"]
