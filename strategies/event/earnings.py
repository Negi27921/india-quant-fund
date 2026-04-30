"""Earnings surprise event-driven strategy."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from strategies.base import BaseStrategy


class EarningsSurprise(BaseStrategy):
    name = "event"
    description = "Post-earnings momentum on positive earnings surprise"

    DEFAULT_PARAMS = {
        "entry_delay_days": 1,      # Enter day after announcement
        "hold_days": 5,
        "max_positions": 3,
        "min_surprise_pct": 5.0,   # Min EPS beat to trigger signal
        "stop_loss_pct": 5.0,
    }

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__({**self.DEFAULT_PARAMS, **(params or {})})
        self._recent_announcements: dict[str, dict] = {}

    def add_announcement(
        self,
        ticker: str,
        announced_date: date,
        actual_eps: float,
        estimated_eps: float,
    ) -> None:
        """Register a new earnings announcement."""
        if estimated_eps == 0:
            return
        surprise_pct = (actual_eps - estimated_eps) / abs(estimated_eps) * 100
        self._recent_announcements[ticker] = {
            "date": announced_date,
            "actual_eps": actual_eps,
            "estimated_eps": estimated_eps,
            "surprise_pct": surprise_pct,
        }

    def generate(self, data, features=None, fundamentals=None) -> dict[str, float]:
        today = date.today()
        signals: dict[str, float] = {}
        min_surprise = self.params["min_surprise_pct"]
        delay = self.params["entry_delay_days"]

        for ticker, ann in self._recent_announcements.items():
            ann_date = ann["date"]
            surprise = ann["surprise_pct"]

            # Only trade in the entry window (day after announcement)
            days_since = (today - ann_date).days
            if days_since < delay or days_since > delay + 2:
                continue

            # Only positive surprises
            if surprise < min_surprise:
                continue

            if ticker not in data:
                continue

            # Signal strength based on surprise magnitude
            signal = min(surprise / 20.0, 1.0)  # 20% surprise = max signal
            signals[ticker] = signal

        return signals

    def get_upcoming_earnings(self, tickers: list[str]) -> list[str]:
        """Return tickers with earnings in the next 5 days (placeholder)."""
        return []  # Populated by the data pipeline
