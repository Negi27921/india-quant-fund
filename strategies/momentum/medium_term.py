"""Medium-term cross-sectional momentum (3–12 month, skip last month)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class MediumTermMomentum(BaseStrategy):
    name = "momentum_mt"
    description = "12-1 month cross-sectional momentum (Jegadeesh-Titman)"

    DEFAULT_PARAMS = {
        "formation_days": 252,    # 12-month lookback
        "skip_days": 21,          # Skip last month (reversal)
        "entry_z": 0.84,          # Top quintile
        "exit_z": 0.0,            # Below median → exit
        "min_adv_cr": 10.0,
        "min_market_cap_cr": 1000,
        "max_positions": 20,
    }

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__({**self.DEFAULT_PARAMS, **(params or {})})

    def generate(self, data, features=None, fundamentals=None) -> dict[str, float]:
        formation = self.params["formation_days"]
        skip = self.params["skip_days"]
        min_days = formation + 5

        scores: dict[str, float] = {}
        for ticker, df in data.items():
            if df is None or len(df) < min_days:
                continue
            try:
                close = df["close"]
                # 12-month return excluding last month
                p_now = close.iloc[-skip - 1]          # price 1 month ago
                p_past = close.iloc[-formation - 1]    # price 12 months ago
                if p_past <= 0:
                    continue
                mom_score = (p_now - p_past) / p_past
                scores[ticker] = float(mom_score)
            except Exception:
                continue

        if not scores:
            return {}

        s = pd.Series(scores)
        z = (s - s.mean()) / (s.std() + 1e-9)
        entry_z = self.params["entry_z"]

        # Return normalized signal only for entry threshold passers
        normalized = (s - s.min()) / (s.max() - s.min() + 1e-9)
        return {
            ticker: float(normalized[ticker])
            for ticker in scores
            if z[ticker] >= entry_z
        }

    def should_exit(self, ticker: str, data: dict[str, pd.DataFrame]) -> bool:
        formation = self.params["formation_days"]
        skip = self.params["skip_days"]
        df = data.get(ticker)
        if df is None or len(df) < formation + 5:
            return False
        try:
            close = df["close"]
            p_now = close.iloc[-skip - 1]
            p_past = close.iloc[-formation - 1]
            if p_past <= 0:
                return False
            score = (p_now - p_past) / p_past
            all_scores = []
            for t, d in data.items():
                if d is not None and len(d) >= formation + 5:
                    c = d["close"]
                    if c.iloc[-formation - 1] > 0:
                        all_scores.append((c.iloc[-skip - 1] - c.iloc[-formation - 1]) / c.iloc[-formation - 1])
            if not all_scores:
                return False
            s = pd.Series(all_scores)
            z = (score - s.mean()) / (s.std() + 1e-9)
            return z < self.params["exit_z"]
        except Exception:
            return False
