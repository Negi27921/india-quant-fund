"""Quality-Value-LowVol composite factor strategy."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class FactorStrategy(BaseStrategy):
    name = "factor"
    description = "Quality (40%) + Value (35%) + Low Volatility (25%) composite"

    DEFAULT_PARAMS = {
        "w_value": 0.35,
        "w_quality": 0.40,
        "w_lowvol": 0.25,
        "top_n": 30,
        "vol_lookback": 60,
        "rebalance": "monthly",
    }

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__({**self.DEFAULT_PARAMS, **(params or {})})

    def generate(
        self,
        data: dict[str, pd.DataFrame],
        features: dict[str, pd.DataFrame] | None = None,
        fundamentals: pd.DataFrame | None = None,
    ) -> dict[str, float]:
        if fundamentals is None or fundamentals.empty:
            return {}

        tickers = [t for t in fundamentals.index if t in data]
        if not tickers:
            return {}

        fund = fundamentals.loc[tickers]

        # ── Value z-scores ───────────────────────────────────────────────────
        value_scores = self._value_score(fund)

        # ── Quality z-scores ─────────────────────────────────────────────────
        quality_scores = self._quality_score(fund)

        # ── Low vol z-scores ─────────────────────────────────────────────────
        lowvol_scores = self._lowvol_score(data, tickers)

        # ── Composite ────────────────────────────────────────────────────────
        composite = pd.Series(dtype=float)
        for ticker in tickers:
            v = value_scores.get(ticker, 0) or 0
            q = quality_scores.get(ticker, 0) or 0
            lv = lowvol_scores.get(ticker, 0) or 0
            composite[ticker] = (
                self.params["w_value"] * v
                + self.params["w_quality"] * q
                + self.params["w_lowvol"] * lv
            )

        composite = composite.dropna()
        if composite.empty:
            return {}

        # Select top N
        top_n = self.params["top_n"]
        top = composite.nlargest(top_n)

        # Normalize to [0, 1]
        norm = (top - top.min()) / (top.max() - top.min() + 1e-9)
        return norm.to_dict()

    def _value_score(self, fund: pd.DataFrame) -> dict[str, float]:
        """Cross-sectional z-score of value metrics (higher = cheaper = better)."""
        scores = pd.Series(0.0, index=fund.index)
        n = 0
        if "pe_ratio" in fund.columns:
            pe_inv = 1 / fund["pe_ratio"].replace(0, np.nan)
            pe_z = self._cs_zscore(pe_inv)
            scores += pe_z.fillna(0)
            n += 1
        if "pb_ratio" in fund.columns:
            pb_inv = 1 / fund["pb_ratio"].replace(0, np.nan)
            pb_z = self._cs_zscore(pb_inv)
            scores += pb_z.fillna(0)
            n += 1
        if "ev_ebitda" in fund.columns:
            ev_inv = 1 / fund["ev_ebitda"].replace(0, np.nan)
            ev_z = self._cs_zscore(ev_inv)
            scores += ev_z.fillna(0)
            n += 1
        return (scores / max(n, 1)).to_dict()

    def _quality_score(self, fund: pd.DataFrame) -> dict[str, float]:
        """Cross-sectional z-score of quality metrics (higher = better quality)."""
        scores = pd.Series(0.0, index=fund.index)
        n = 0
        if "roe" in fund.columns:
            scores += self._cs_zscore(fund["roe"]).fillna(0)
            n += 1
        if "gross_margin" in fund.columns:
            scores += self._cs_zscore(fund["gross_margin"]).fillna(0)
            n += 1
        if "debt_equity" in fund.columns:
            scores += self._cs_zscore(-fund["debt_equity"].fillna(2)).fillna(0)
            n += 1
        return (scores / max(n, 1)).to_dict()

    def _lowvol_score(self, data: dict[str, pd.DataFrame], tickers: list[str]) -> dict[str, float]:
        """Cross-sectional z-score of low volatility (lower vol = better)."""
        vols = {}
        lookback = self.params["vol_lookback"]
        for ticker in tickers:
            df = data.get(ticker)
            if df is not None and len(df) >= lookback:
                log_ret = np.log(df["close"] / df["close"].shift(1))
                vol = log_ret.iloc[-lookback:].std() * np.sqrt(252)
                vols[ticker] = float(vol)
        if not vols:
            return {}
        vol_series = pd.Series(vols)
        z = self._cs_zscore(-vol_series)  # Negate: lower vol = higher score
        return z.to_dict()

    @staticmethod
    def _cs_zscore(s: pd.Series) -> pd.Series:
        return (s - s.mean()) / (s.std() + 1e-9)
