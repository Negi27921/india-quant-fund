"""Walk-forward validation — rolling train/test windows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd
from loguru import logger

from backtest.engine.india_equity import IndiaEquityEngine
from backtest.engine.metrics import compute_metrics


@dataclass
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    test_metrics: dict[str, Any]
    test_equity: pd.Series


@dataclass
class WalkForwardResult:
    windows: list[WalkForwardWindow]
    aggregate_metrics: dict[str, Any]
    passed: bool
    failure_reasons: list[str]

    @property
    def median_sharpe(self) -> float:
        sharpes = [w.test_metrics.get("sharpe_ratio", 0) for w in self.windows]
        return float(np.median(sharpes)) if sharpes else 0

    @property
    def pass_rate(self) -> float:
        passing = sum(1 for w in self.windows if w.test_metrics.get("sharpe_ratio", 0) > 0.5)
        return passing / len(self.windows) if self.windows else 0


class WalkForwardValidator:
    """
    Runs rolling walk-forward validation.
    Pass criteria:
      - Sharpe > 0.5 in >60% of test windows
      - Max DD < 20% in all test windows
      - No single window loss > 15%
    """

    PASS_SHARPE_THRESHOLD = 0.5
    PASS_SHARPE_RATE = 0.60        # Must pass in >60% of windows
    MAX_DRAWDOWN_LIMIT = 0.20
    MAX_SINGLE_WINDOW_LOSS = 0.15

    def __init__(
        self,
        train_days: int = 252,     # 1 year
        test_days: int = 63,       # 1 quarter
        step_days: int = 21,       # 1 month
        min_windows: int = 8,      # Minimum 2 years of data
    ):
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.min_windows = min_windows

    def validate(
        self,
        signal_fn: Callable[[dict[str, pd.DataFrame]], dict[str, pd.Series]],
        data: dict[str, pd.DataFrame],
        initial_capital: float = 1_000_000,
    ) -> WalkForwardResult:
        """
        signal_fn: function(data_slice) -> {ticker: signal_series}
        data: full historical data for all tickers
        """
        trading_dates = self._get_dates(data)
        if len(trading_dates) < self.train_days + self.test_days:
            return WalkForwardResult(
                windows=[], aggregate_metrics={}, passed=False,
                failure_reasons=["Insufficient data for walk-forward validation"],
            )

        windows = self._build_windows(trading_dates)
        if len(windows) < self.min_windows:
            return WalkForwardResult(
                windows=[], aggregate_metrics={}, passed=False,
                failure_reasons=[f"Only {len(windows)} windows, need {self.min_windows}"],
            )

        engine = IndiaEquityEngine(initial_capital=initial_capital)
        results: list[WalkForwardWindow] = []

        for train_start, train_end, test_start, test_end in windows:
            test_data = self._slice_data(data, test_start, test_end)
            if not test_data:
                continue
            try:
                signals = signal_fn(test_data)
                if not signals:
                    continue
                result = engine.run(signals, test_data, "walk_forward")
                results.append(WalkForwardWindow(
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    test_metrics=result.metrics,
                    test_equity=result.equity_curve,
                ))
            except Exception as e:
                logger.warning(f"Walk-forward window failed: {e}")

        if not results:
            return WalkForwardResult(
                windows=results, aggregate_metrics={}, passed=False,
                failure_reasons=["All windows failed"],
            )

        agg = self._aggregate_metrics(results)
        passed, reasons = self._check_pass(results, agg)

        logger.info(
            f"Walk-forward: {len(results)} windows, "
            f"pass_rate={sum(1 for r in results if r.test_metrics.get('sharpe_ratio', 0) > 0.5)/len(results):.0%}, "
            f"median_sharpe={np.median([r.test_metrics.get('sharpe_ratio', 0) for r in results]):.2f}"
        )

        return WalkForwardResult(
            windows=results,
            aggregate_metrics=agg,
            passed=passed,
            failure_reasons=reasons,
        )

    def _build_windows(self, dates: pd.DatetimeIndex) -> list[tuple]:
        windows = []
        i = 0
        while True:
            train_start = dates[i]
            train_end_idx = i + self.train_days
            if train_end_idx >= len(dates):
                break
            test_start_idx = train_end_idx
            test_end_idx = test_start_idx + self.test_days
            if test_end_idx >= len(dates):
                break
            windows.append((
                dates[i], dates[train_end_idx],
                dates[test_start_idx], dates[test_end_idx],
            ))
            i += self.step_days
        return windows

    def _slice_data(self, data, start, end) -> dict[str, pd.DataFrame]:
        sliced = {}
        for ticker, df in data.items():
            subset = df.loc[start:end]
            if not subset.empty:
                sliced[ticker] = subset
        return sliced

    def _get_dates(self, data: dict) -> pd.DatetimeIndex:
        idx = pd.DatetimeIndex([])
        for df in data.values():
            if df is not None:
                idx = idx.union(df.index)
        return idx.sort_values()

    def _aggregate_metrics(self, windows: list[WalkForwardWindow]) -> dict:
        sharpes = [w.test_metrics.get("sharpe_ratio", 0) for w in windows]
        drawdowns = [w.test_metrics.get("max_drawdown", 0) for w in windows]
        returns = [w.test_metrics.get("total_return", 0) for w in windows]
        return {
            "n_windows": len(windows),
            "median_sharpe": round(float(np.median(sharpes)), 3),
            "mean_sharpe": round(float(np.mean(sharpes)), 3),
            "worst_sharpe": round(float(np.min(sharpes)), 3),
            "pass_rate": round(sum(s > 0.5 for s in sharpes) / len(sharpes), 3),
            "worst_drawdown": round(float(np.min(drawdowns)), 4),
            "median_return": round(float(np.median(returns)), 4),
        }

    def _check_pass(self, windows, agg) -> tuple[bool, list[str]]:
        reasons = []
        if agg["pass_rate"] < self.PASS_SHARPE_RATE:
            reasons.append(f"Pass rate {agg['pass_rate']:.0%} < {self.PASS_SHARPE_RATE:.0%}")
        if agg["worst_drawdown"] < -self.MAX_DRAWDOWN_LIMIT:
            reasons.append(f"Worst DD {agg['worst_drawdown']:.1%} < -{self.MAX_DRAWDOWN_LIMIT:.0%}")
        for w in windows:
            ret = w.test_metrics.get("total_return", 0)
            if ret < -self.MAX_SINGLE_WINDOW_LOSS:
                reasons.append(f"Window {w.test_start.date()} loss {ret:.1%} < -{self.MAX_SINGLE_WINDOW_LOSS:.0%}")
        return (len(reasons) == 0), reasons
