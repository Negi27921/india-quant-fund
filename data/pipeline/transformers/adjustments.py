"""Price adjustment for splits and dividends — back-adjusted series."""
from __future__ import annotations

from datetime import date

import pandas as pd
from loguru import logger

from data.storage import db


def apply_adjustments(
    df: pd.DataFrame,
    ticker: str,
    actions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Back-adjust OHLCV prices for corporate actions.
    actions DataFrame: columns [action_date, action_type, value, adj_factor]
    """
    if actions is None:
        actions = _load_actions(ticker)

    if actions.empty:
        df["adj_close"] = df["close"]
        df["adj_factor"] = 1.0
        return df

    df = df.copy().sort_index()
    actions = actions.sort_values("action_date", ascending=False)

    cumulative_factor = 1.0
    adj_factors = pd.Series(1.0, index=df.index)

    for _, action in actions.iterrows():
        action_date = pd.Timestamp(action["action_date"])
        action_type = action["action_type"]
        value = float(action.get("value", 0) or 0)

        if action_type == "split":
            # Split ratio: e.g., 2 means 2-for-1 (factor = 0.5 for back-adjustment)
            factor = 1 / value if value > 0 else 1.0
        elif action_type == "bonus":
            # Bonus 1:1 means 2x shares, price halves
            factor = 1 / (1 + value) if value > 0 else 1.0
        elif action_type == "dividend":
            # Dividend adjustment: subtract dividend from historical prices
            # Factor = (close - dividend) / close — approximate
            close_before = df[df.index < action_date]["close"]
            if not close_before.empty:
                last_close = close_before.iloc[-1]
                factor = (last_close - value) / last_close if last_close > 0 else 1.0
            else:
                factor = 1.0
        else:
            continue

        mask = df.index < action_date
        adj_factors[mask] *= factor
        cumulative_factor *= factor

    df["adj_factor"] = adj_factors
    df["adj_close"] = df["close"] * adj_factors
    df["adj_open"] = df["open"] * adj_factors
    df["adj_high"] = df["high"] * adj_factors
    df["adj_low"] = df["low"] * adj_factors

    return df


def _load_actions(ticker: str) -> pd.DataFrame:
    try:
        return db.query_df(
            "SELECT * FROM corporate_actions WHERE ticker = ? ORDER BY action_date DESC",
            [ticker],
        )
    except Exception as e:
        logger.debug(f"No corporate actions for {ticker}: {e}")
        return pd.DataFrame()


def compute_universe_adjustments(
    universe_data: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Apply adjustments to all tickers in the universe."""
    adjusted = {}
    for ticker, df in universe_data.items():
        try:
            adjusted[ticker] = apply_adjustments(df, ticker)
        except Exception as e:
            logger.warning(f"Adjustment failed for {ticker}: {e}")
            df["adj_close"] = df["close"]
            df["adj_factor"] = 1.0
            adjusted[ticker] = df
    return adjusted
