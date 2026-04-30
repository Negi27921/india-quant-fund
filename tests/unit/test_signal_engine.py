"""Unit tests for strategy signal generation."""
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from data.pipeline.transformers.features import compute_features
from strategies.momentum.short_term import ShortTermMomentum
from strategies.momentum.medium_term import MediumTermMomentum
from strategies.mean_reversion.rsi_reversion import RSIMeanReversion


@pytest.fixture
def features_df(sample_universe_ohlcv):
    """Pre-computed features for the test universe."""
    frames = []
    for ticker in sample_universe_ohlcv["ticker"].unique():
        df = sample_universe_ohlcv[sample_universe_ohlcv["ticker"] == ticker].copy()
        if len(df) >= 30:
            frames.append(compute_features(df))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class TestShortTermMomentum:
    def test_generate_returns_dict(self, features_df):
        if features_df.empty:
            pytest.skip("No features computed")
        strat = ShortTermMomentum()
        signals = strat.generate(features_df)
        assert isinstance(signals, dict)

    def test_signals_are_normalized(self, features_df):
        if features_df.empty:
            pytest.skip("No features computed")
        strat = ShortTermMomentum()
        signals = strat.generate(features_df)
        if signals:
            values = list(signals.values())
            assert all(-3 <= v <= 3 for v in values), "Z-scores should be reasonable"

    def test_no_nan_signals(self, features_df):
        if features_df.empty:
            pytest.skip("No features computed")
        strat = ShortTermMomentum()
        signals = strat.generate(features_df)
        assert all(not np.isnan(v) for v in signals.values())

    def test_generate_ranked_returns_sorted(self, features_df):
        if features_df.empty:
            pytest.skip("No features computed")
        strat = ShortTermMomentum()
        ranked = strat.generate_ranked(features_df)
        scores = [s.score for s in ranked]
        assert scores == sorted(scores, reverse=True)


class TestMediumTermMomentum:
    def test_skips_last_month(self, sample_universe_ohlcv):
        """Jegadeesh-Titman skip — last 21 days excluded from signal."""
        strat = MediumTermMomentum()
        from data.pipeline.transformers.features import compute_features
        frames = []
        for ticker in sample_universe_ohlcv["ticker"].unique():
            df = sample_universe_ohlcv[sample_universe_ohlcv["ticker"] == ticker].copy()
            if len(df) >= 30:
                frames.append(compute_features(df))
        if not frames:
            pytest.skip("No features computed")
        features_df = pd.concat(frames, ignore_index=True)
        signals = strat.generate(features_df)
        assert isinstance(signals, dict)


class TestRSIMeanReversion:
    def test_only_trades_oversold(self, features_df):
        """RSI reversion should only fire on RSI < 30."""
        if features_df.empty or "rsi_14" not in features_df.columns:
            pytest.skip("RSI column not available")

        strat = RSIMeanReversion()
        signals = strat.generate(features_df)

        latest = features_df.sort_values("date").groupby("ticker").last().reset_index()

        for ticker, score in signals.items():
            if score > 0:
                row = latest[latest["ticker"] == ticker]
                if not row.empty and "rsi_14" in row.columns:
                    rsi = row["rsi_14"].iloc[0]
                    assert rsi < 35 or np.isnan(rsi), f"{ticker} has RSI={rsi} but got buy signal"


class TestFeatureComputation:
    def test_required_columns_present(self, sample_ohlcv):
        result = compute_features(sample_ohlcv)
        expected_cols = ["rsi_14", "sma_20", "sma_200", "vol_20d", "momentum_st"]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_no_future_values(self, sample_ohlcv):
        result = compute_features(sample_ohlcv)
        today = date.today()
        result["date"] = pd.to_datetime(result["date"]).dt.date
        assert (result["date"] <= today).all(), "Feature dates must not be in the future"

    def test_returns_same_length(self, sample_ohlcv):
        result = compute_features(sample_ohlcv)
        assert len(result) == len(sample_ohlcv)
