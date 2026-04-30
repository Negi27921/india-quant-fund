"""Base strategy contract — all strategies implement SignalEngine."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd


@dataclass
class Signal:
    ticker: str
    strategy: str
    date: date
    signal: float          # -1.0 to 1.0 (negative = short bias, not used in cash)
    signal_raw: float      # Raw score before normalization
    rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    All strategies must implement this interface.
    generate() receives a dict of OHLCV DataFrames (key=ticker)
    and returns a dict of signal series (key=ticker, value=signal float).
    """

    name: str
    description: str

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = params or {}

    @abstractmethod
    def generate(
        self,
        data: dict[str, pd.DataFrame],
        features: dict[str, pd.DataFrame] | None = None,
        fundamentals: pd.DataFrame | None = None,
    ) -> dict[str, float]:
        """
        Returns: {ticker: signal_score}
        score 1.0 = strong buy, 0.0 = neutral, -1.0 = strong sell
        For cash-only strategies, signals are clipped to [0, 1].
        """
        ...

    def generate_ranked(
        self,
        data: dict[str, pd.DataFrame],
        features: dict[str, pd.DataFrame] | None = None,
        fundamentals: pd.DataFrame | None = None,
    ) -> list[Signal]:
        """Generate signals and rank them cross-sectionally."""
        raw_signals = self.generate(data, features, fundamentals)
        if not raw_signals:
            return []

        today = date.today()
        scores = pd.Series(raw_signals)
        scores = scores.clip(0, 1)  # Cash-only: no shorts

        # Rank by signal strength
        ranked = scores.sort_values(ascending=False)
        signals = []
        for rank, (ticker, score) in enumerate(ranked.items(), 1):
            signals.append(Signal(
                ticker=ticker,
                strategy=self.name,
                date=today,
                signal=float(score),
                signal_raw=float(raw_signals[ticker]),
                rank=rank,
            ))
        return signals

    def get_param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)
