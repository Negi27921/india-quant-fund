"""Feature engineering — computes all technical and statistical features."""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False


def compute_features(df: pd.DataFrame, nifty: pd.Series | None = None) -> pd.DataFrame:
    """
    Given a single stock OHLCV DataFrame, compute all features.
    Returns DataFrame with same index, feature columns added.
    """
    out = pd.DataFrame(index=df.index)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    value = close * volume  # daily traded value ₹

    # ── Returns ───────────────────────────────────────────────────────────────
    out["ret_1d"] = close.pct_change(1)
    out["ret_5d"] = close.pct_change(5)
    out["ret_20d"] = close.pct_change(20)
    out["ret_63d"] = close.pct_change(63)
    out["ret_126d"] = close.pct_change(126)
    out["ret_252d"] = close.pct_change(252)

    # ── Momentum scores ───────────────────────────────────────────────────────
    vol_ratio = value.rolling(5).mean() / value.rolling(60).mean().replace(0, np.nan)
    out["mom_score_st"] = (
        0.40 * _zscore(out["ret_5d"])
        + 0.40 * _zscore(out["ret_20d"])
        + 0.20 * _zscore(vol_ratio)
    )
    # Medium-term: skip last month (12m - 1m)
    out["mom_score_mt"] = out["ret_252d"] - out["ret_20d"]

    # ── Moving averages ───────────────────────────────────────────────────────
    out["sma_20"] = close.rolling(20).mean()
    out["sma_50"] = close.rolling(50).mean()
    out["sma_200"] = close.rolling(200).mean()
    out["ema_12"] = close.ewm(span=12, adjust=False).mean()
    out["ema_26"] = close.ewm(span=26, adjust=False).mean()

    # ── RSI ───────────────────────────────────────────────────────────────────
    out["rsi_14"] = _rsi(close, 14)

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    out["bb_upper"] = bb_mid + 2 * bb_std
    out["bb_lower"] = bb_mid - 2 * bb_std
    out["bb_pct"] = (close - out["bb_lower"]) / (out["bb_upper"] - out["bb_lower"]).replace(0, np.nan)

    # ── MACD ─────────────────────────────────────────────────────────────────
    out["macd"] = out["ema_12"] - out["ema_26"]
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()

    # ── ADX ───────────────────────────────────────────────────────────────────
    out["adx_14"] = _adx(high, low, close, 14)

    # ── Volume ────────────────────────────────────────────────────────────────
    out["adv_5d"] = value.rolling(5).mean()
    out["adv_20d"] = value.rolling(20).mean()
    out["adv_60d"] = value.rolling(60).mean()
    out["volume_ratio"] = vol_ratio

    # ── Volatility ────────────────────────────────────────────────────────────
    log_ret = np.log(close / close.shift(1))
    out["vol_20d"] = log_ret.rolling(20).std() * np.sqrt(252)
    out["vol_60d"] = log_ret.rolling(60).std() * np.sqrt(252)

    # ── Beta ──────────────────────────────────────────────────────────────────
    if nifty is not None:
        nifty_ret = nifty.pct_change()
        stock_ret = close.pct_change()
        out["beta_252d"] = (
            stock_ret.rolling(252).cov(nifty_ret)
            / nifty_ret.rolling(252).var().replace(0, np.nan)
        )

    return out


def compute_factor_scores(
    fundamentals: pd.DataFrame,
    features: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cross-sectional factor z-scores for the factor strategy.
    Inputs are cross-sectional DataFrames (index=ticker, columns=metrics).
    """
    out = pd.DataFrame(index=fundamentals.index)

    # Value composite
    pe_inv = _cross_zscore(1 / fundamentals["pe_ratio"].replace(0, np.nan))
    pb_inv = _cross_zscore(1 / fundamentals["pb_ratio"].replace(0, np.nan))
    ev_inv = _cross_zscore(1 / fundamentals["ev_ebitda"].replace(0, np.nan))
    out["factor_value"] = (pe_inv + pb_inv + ev_inv) / 3

    # Quality composite
    roe_z = _cross_zscore(fundamentals["roe"])
    margin_z = _cross_zscore(fundamentals["gross_margin"])
    debt_z = _cross_zscore(-fundamentals["debt_equity"].fillna(2))
    out["factor_quality"] = (roe_z + margin_z + debt_z) / 3

    # Low vol
    if "vol_60d" in features.columns:
        out["factor_lowvol"] = _cross_zscore(-features["vol_60d"])
    else:
        out["factor_lowvol"] = 0.0

    # Composite
    out["factor_composite"] = (
        0.35 * out["factor_value"]
        + 0.40 * out["factor_quality"]
        + 0.25 * out["factor_lowvol"]
    )
    return out


# ── Internal helpers ─────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0)
    minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def _zscore(s: pd.Series, window: int = 252) -> pd.Series:
    """Rolling z-score."""
    mean = s.rolling(window, min_periods=20).mean()
    std = s.rolling(window, min_periods=20).std()
    return (s - mean) / std.replace(0, np.nan)


def _cross_zscore(s: pd.Series) -> pd.Series:
    """Cross-sectional z-score across tickers."""
    return (s - s.mean()) / s.std().replace(0, np.nan)
