"""OHLCV data validator — catches bad data before it hits the database."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class ValidationResult:
    ticker: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    rows_original: int = 0
    rows_clean: int = 0
    rows_dropped: int = 0

    @property
    def drop_rate(self) -> float:
        return self.rows_dropped / self.rows_original if self.rows_original else 0


class OHLCVValidator:
    """
    Validates OHLCV DataFrames for common data quality issues.
    Returns cleaned DataFrame and validation report.
    """

    MAX_DAILY_MOVE_PCT = 25.0      # Flag if price moves >25% in a day
    MAX_PRICE_GAP_PCT = 30.0       # Flag if open/close gap >30% (possible split)
    MIN_VOLUME = 1                 # Must have at least 1 share traded
    MAX_ZERO_VOLUME_PCT = 5.0      # Max 5% of days with zero volume

    def validate(self, df: pd.DataFrame, ticker: str) -> tuple[pd.DataFrame, ValidationResult]:
        result = ValidationResult(ticker=ticker, passed=True, rows_original=len(df))
        df = df.copy()

        # 1. Required columns
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            result.passed = False
            result.issues.append(f"Missing columns: {missing}")
            return df, result

        # 2. No NaN in critical columns
        nan_mask = df[["open", "high", "low", "close"]].isna().any(axis=1)
        if nan_mask.any():
            n = nan_mask.sum()
            result.issues.append(f"Dropped {n} rows with NaN prices")
            df = df[~nan_mask]

        # 3. Positive prices
        neg_mask = (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        if neg_mask.any():
            n = neg_mask.sum()
            result.issues.append(f"Dropped {n} rows with non-positive prices")
            df = df[~neg_mask]

        # 4. High >= Low (basic OHLC sanity)
        invalid_hl = df["high"] < df["low"]
        if invalid_hl.any():
            n = invalid_hl.sum()
            result.issues.append(f"Dropped {n} rows where high < low")
            df = df[~invalid_hl]

        # 5. Close within High-Low range
        invalid_close = (df["close"] > df["high"]) | (df["close"] < df["low"])
        if invalid_close.any():
            n = invalid_close.sum()
            result.issues.append(f"Fixed {n} rows where close outside H-L range")
            df.loc[invalid_close, "close"] = df.loc[invalid_close, ["high", "low"]].mean(axis=1)

        # 6. Extreme daily moves (likely bad data, not split)
        if len(df) > 1:
            df_sorted = df.sort_index()
            daily_ret = df_sorted["close"].pct_change().abs()
            extreme_moves = daily_ret > (self.MAX_DAILY_MOVE_PCT / 100)
            if extreme_moves.any():
                n = extreme_moves.sum()
                result.issues.append(
                    f"Warning: {n} days with >{self.MAX_DAILY_MOVE_PCT}% move — check for splits"
                )

        # 7. Zero volume
        zero_vol = (df["volume"] == 0).sum()
        zero_vol_pct = zero_vol / len(df) * 100 if len(df) else 0
        if zero_vol_pct > self.MAX_ZERO_VOLUME_PCT:
            result.issues.append(
                f"Warning: {zero_vol_pct:.1f}% days with zero volume"
            )

        # 8. Weekend/holiday rows (weekday only)
        df.index = pd.DatetimeIndex(df.index)
        weekend_mask = df.index.dayofweek >= 5
        if weekend_mask.any():
            n = weekend_mask.sum()
            result.issues.append(f"Dropped {n} weekend rows")
            df = df[~weekend_mask]

        # 9. Future dates
        today = pd.Timestamp.now().normalize()
        future_mask = pd.DatetimeIndex(df.index) > today
        if future_mask.any():
            n = future_mask.sum()
            result.issues.append(f"Dropped {n} future date rows")
            df = df[~future_mask]

        # 10. Duplicate dates
        dup_mask = df.index.duplicated(keep="last")
        if dup_mask.any():
            n = dup_mask.sum()
            result.issues.append(f"Dropped {n} duplicate date rows")
            df = df[~dup_mask]

        df = df.sort_index()
        result.rows_clean = len(df)
        result.rows_dropped = result.rows_original - result.rows_clean

        if result.rows_clean == 0:
            result.passed = False
            result.issues.append("No valid rows remaining after validation")
        elif result.drop_rate > 0.10:
            result.issues.append(
                f"High drop rate: {result.drop_rate:.1%} of rows removed"
            )

        return df, result


def validate_universe(
    data: dict[str, pd.DataFrame],
    abort_threshold: float = 0.10,
) -> tuple[dict[str, pd.DataFrame], dict[str, ValidationResult]]:
    """Validate entire universe. Abort if too many failures."""
    validator = OHLCVValidator()
    clean_data: dict[str, pd.DataFrame] = {}
    results: dict[str, ValidationResult] = {}

    for ticker, df in data.items():
        clean_df, vr = validator.validate(df, ticker)
        results[ticker] = vr
        if vr.passed and not clean_df.empty:
            clean_data[ticker] = clean_df
        elif not vr.passed:
            logger.warning(f"Validation FAILED for {ticker}: {vr.issues}")

    failure_rate = 1 - len(clean_data) / max(len(data), 1)
    logger.info(
        f"Validation: {len(clean_data)}/{len(data)} passed "
        f"({failure_rate:.1%} failure rate)"
    )

    if failure_rate > abort_threshold:
        logger.error(
            f"Failure rate {failure_rate:.1%} exceeds threshold {abort_threshold:.1%}"
            " — recommend aborting"
        )

    return clean_data, results
