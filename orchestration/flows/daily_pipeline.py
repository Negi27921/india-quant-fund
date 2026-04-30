"""Daily pipeline flow — runs at 06:00 IST, fetches and validates all data."""
from __future__ import annotations

from datetime import date, timedelta

from loguru import logger

from data.pipeline.loaders.nse import NSELoader
from data.pipeline.loaders.registry import fetch_universe_ohlcv
from data.pipeline.transformers.adjustments import compute_universe_adjustments
from data.pipeline.transformers.features import compute_features
from data.pipeline.transformers.universe import apply_universe_filters, get_nifty500
from data.pipeline.validators.ohlcv import validate_universe
from data.storage import db
from monitoring.alerts import get_alerts


def run_daily_data_pipeline(target_date: date | None = None) -> dict:
    """
    Full daily data ingestion pipeline.
    Returns status dict with counts and any errors.
    """
    target_date = target_date or date.today()
    start_date = target_date - timedelta(days=504)  # 2 years for features
    alerts = get_alerts()

    logger.info(f"Starting daily data pipeline for {target_date}")

    # 1. Get universe
    tickers = get_nifty500()
    logger.info(f"Universe: {len(tickers)} tickers")

    # 2. Fetch OHLCV
    logger.info("Fetching OHLCV from Yahoo Finance...")
    result = fetch_universe_ohlcv(tickers, start_date, target_date)

    if result.success_rate < 0.50:
        msg = f"Data fetch CRITICAL: only {result.success_rate:.0%} success rate"
        logger.error(msg)
        alerts.send_critical(msg)
        return {"status": "abort", "reason": msg}

    if result.success_rate < 0.90:
        alerts.send_warning(f"Data quality warning: {result.success_rate:.0%} fetch rate")

    # 3. Validate
    logger.info("Validating OHLCV data...")
    clean_data, validation_results = validate_universe(result.data)

    if len(clean_data) < 0.50 * len(result.data):
        msg = "Too many validation failures — aborting pipeline"
        logger.error(msg)
        alerts.send_critical(msg)
        return {"status": "abort", "reason": msg}

    # 4. Apply corporate action adjustments
    logger.info("Applying price adjustments...")
    adjusted_data = compute_universe_adjustments(clean_data)

    # 5. Compute features for each ticker
    logger.info("Computing features...")
    features_computed = 0
    nse = NSELoader()
    vix = nse.fetch_vix()
    fii_dii = nse.fetch_fii_dii()

    all_features = {}
    for ticker, df in adjusted_data.items():
        try:
            feat = compute_features(df)
            all_features[ticker] = feat
            features_computed += 1
        except Exception as e:
            logger.warning(f"Feature computation failed for {ticker}: {e}")

    # 6. Store in DuckDB
    logger.info("Writing to DuckDB...")
    stored = 0
    for ticker, df in adjusted_data.items():
        try:
            df_store = df.reset_index()
            df_store["ticker"] = ticker
            db.upsert_df(
                df_store[["ticker", "date", "open", "high", "low", "close", "volume"]],
                "ohlcv",
                ["ticker", "date"],
            )
            stored += 1
        except Exception as e:
            logger.warning(f"Store failed for {ticker}: {e}")

    # 7. Store market_data (VIX, FII)
    if vix or fii_dii:
        try:
            db.execute("""
                INSERT OR REPLACE INTO market_data (ticker, date, vix_india, fii_net_cr, dii_net_cr)
                VALUES ('INDEX', ?, ?, ?, ?)
            """, [target_date, vix, fii_dii.get("fii_net_cr"), fii_dii.get("dii_net_cr")])
        except Exception:
            pass

    summary = {
        "status": "ok",
        "date": str(target_date),
        "universe_size": len(tickers),
        "fetched": len(result.data),
        "clean": len(clean_data),
        "stored": stored,
        "features_computed": features_computed,
        "success_rate": result.success_rate,
        "vix": vix,
    }

    logger.info(f"Daily pipeline complete: {summary}")
    return summary
