"""Loader registry with automatic fallback chains."""
from __future__ import annotations

from datetime import date

import pandas as pd
from loguru import logger

from data.pipeline.loaders.base import BaseLoader, LoaderResult
from data.pipeline.loaders.yahoo import YahooLoader
from data.pipeline.loaders.nse import NSELoader

# Fallback chain: primary first, then alternatives
FALLBACK_CHAINS: dict[str, list[str]] = {
    "NSE": ["yahoo_nse", "yahoo_bse"],
    "BSE": ["yahoo_bse", "yahoo_nse"],
}

_LOADERS: dict[str, BaseLoader] = {}


def _build_loaders() -> dict[str, BaseLoader]:
    return {
        "yahoo_nse": YahooLoader(exchange="NSE"),
        "yahoo_bse": YahooLoader(exchange="BSE"),
        "nse": NSELoader(),
    }


def _get_loaders() -> dict[str, BaseLoader]:
    global _LOADERS
    if not _LOADERS:
        _LOADERS = _build_loaders()
    return _LOADERS


def get_loader(exchange: str = "NSE") -> BaseLoader:
    """Return the first available loader for the given exchange."""
    loaders = _get_loaders()
    chain = FALLBACK_CHAINS.get(exchange, ["yahoo_nse"])
    for name in chain:
        loader = loaders.get(name)
        if loader and loader.is_available():
            return loader
    raise RuntimeError(f"No available loader for exchange: {exchange}")


def get_nse_loader() -> NSELoader:
    loaders = _get_loaders()
    return loaders["nse"]  # type: ignore[return-value]


def fetch_universe_ohlcv(
    tickers: list[str],
    start: date,
    end: date,
    exchange: str = "NSE",
    interval: str = "1d",
) -> LoaderResult:
    """Fetch OHLCV for a list of tickers with fallback."""
    loaders = _get_loaders()
    chain = FALLBACK_CHAINS.get(exchange, ["yahoo_nse"])
    remaining = list(tickers)
    all_data: dict[str, pd.DataFrame] = {}

    for loader_name in chain:
        if not remaining:
            break
        loader = loaders.get(loader_name)
        if not loader:
            continue
        if not loader.is_available():
            logger.warning(f"Loader {loader_name} unavailable, skipping")
            continue

        try:
            data = loader.fetch_ohlcv(remaining, start, end, interval)
            all_data.update(data)
            fetched = set(data.keys())
            remaining = [t for t in remaining if t not in fetched]
            if remaining:
                logger.info(f"{loader_name}: {len(fetched)} ok, {len(remaining)} falling back")
        except Exception as e:
            logger.error(f"Loader {loader_name} failed: {e}")

    success = list(all_data.keys())
    failed = [t for t in tickers if t not in all_data]
    if failed:
        logger.warning(f"Failed to fetch {len(failed)} tickers: {failed[:10]}...")
    return LoaderResult(success=success, failed=failed, data=all_data)
