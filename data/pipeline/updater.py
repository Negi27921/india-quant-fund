"""
Incremental daily data updater.
Called by the Prefect daily_pipeline flow at 06:00 IST.
Only fetches the last N trading days to avoid re-downloading history.
"""
from __future__ import annotations
from datetime import date, timedelta

import pandas as pd

from data.pipeline.loaders.registry import fetch_universe_ohlcv
from data.pipeline.validators.ohlcv import validate_universe
from data.pipeline.transformers.adjustments import apply_adjustments
from data.pipeline.transformers.features import compute_features
from data.pipeline.transformers.universe import get_nifty500
from data.storage.db import db
from monitoring.alerts import get_alerts
from monitoring.audit import AuditLogger


def get_last_stored_date(ticker: str) -> date | None:
    try:
        row = db.query_df(
            f"SELECT MAX(date) as last_date FROM ohlcv WHERE ticker = '{ticker}'"
        )
        if not row.empty and row["last_date"].iloc[0] is not None:
            return pd.to_datetime(row["last_date"].iloc[0]).date()
    except Exception:
        pass
    return None


def update_universe_data(
    universe: list[str] | None = None,
    lookback_days: int = 5,
    abort_threshold: float = 0.5,
) -> dict:
    """
    Incrementally fetch and store the last `lookback_days` of OHLCV data.

    Returns a summary dict with counts of success/failure.
    """
    if universe is None:
        universe = get_nifty500()

    today = date.today()
    fetch_start = today - timedelta(days=lookback_days * 2)  # buffer for weekends

    alerts = get_alerts()
    result = {"tickers_attempted": len(universe), "tickers_ok": 0, "tickers_failed": 0}

    loader_result = fetch_universe_ohlcv(universe, str(fetch_start), str(today))

    raw = loader_result.data
    if raw is None or raw.empty:
        alerts.send_critical("Data Pipeline", "Daily update fetched 0 rows — check data sources")
        AuditLogger.log("DATA_PIPELINE", "updater", "fetch_failed", payload={"universe": len(universe)})
        return result

    fetch_rate = raw["ticker"].nunique() / len(universe)
    result["tickers_ok"] = raw["ticker"].nunique()
    result["tickers_failed"] = len(loader_result.failed_tickers)

    if fetch_rate < abort_threshold:
        msg = f"Fetch rate {fetch_rate:.1%} below abort threshold {abort_threshold:.1%}"
        alerts.send_critical("Data Pipeline", msg)
        AuditLogger.log("DATA_PIPELINE", "updater", "aborted", payload={"fetch_rate": fetch_rate})
        raise RuntimeError(msg)

    if fetch_rate < 0.9:
        alerts.send_warning("Data Pipeline", f"Partial fetch: {fetch_rate:.1%} of universe")

    # Validate
    validated, _ = validate_universe(raw)

    # Adjust for corporate actions
    adjusted = apply_adjustments(validated)

    # Write OHLCV (upsert on ticker+date)
    db.upsert_df(adjusted, "ohlcv", conflict_cols=["ticker", "date"])

    # Compute features for each ticker
    feature_errors = 0
    for ticker in adjusted["ticker"].unique():
        # Get recent 300 rows for stable indicator computation
        ticker_hist = db.query_df(f"""
            SELECT * FROM ohlcv
            WHERE ticker = '{ticker}'
            ORDER BY date DESC
            LIMIT 300
        """).sort_values("date")

        if len(ticker_hist) < 30:
            continue

        try:
            feats = compute_features(ticker_hist)
            # Only store today's features (avoid overwriting history)
            today_feats = feats[feats["date"] == str(today)]
            if not today_feats.empty:
                db.upsert_df(today_feats, "features", conflict_cols=["ticker", "date"])
        except Exception:
            feature_errors += 1

    AuditLogger.log("DATA_PIPELINE", "updater", "complete", payload={
        "rows": len(adjusted),
        "tickers": result["tickers_ok"],
        "feature_errors": feature_errors,
        "date": str(today),
    })

    return result
