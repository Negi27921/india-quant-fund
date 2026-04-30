"""Yahoo Finance loader — primary OHLCV source for NSE/BSE (.NS/.BO suffix)."""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from data.pipeline.loaders.base import BaseLoader, LoaderResult


class YahooLoader(BaseLoader):
    name = "yahoo"
    markets = {"NSE", "BSE", "NIFTY"}
    requires_auth = False

    SUFFIX_MAP = {"NSE": ".NS", "BSE": ".BO"}
    BATCH_SIZE = 50        # Yahoo handles ~50 tickers per call
    SLEEP_BETWEEN = 1.0    # seconds between batch calls

    def __init__(self, exchange: str = "NSE"):
        self.exchange = exchange
        self.suffix = self.SUFFIX_MAP.get(exchange, ".NS")

    def is_available(self) -> bool:
        try:
            t = yf.Ticker("RELIANCE.NS")
            _ = t.fast_info
            return True
        except Exception:
            return False

    def _to_yahoo_ticker(self, ticker: str) -> str:
        if "." in ticker:
            return ticker
        return f"{ticker}{self.suffix}"

    def _from_yahoo_ticker(self, yahoo: str) -> str:
        return yahoo.replace(self.suffix, "")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_ohlcv(
        self,
        tickers: list[str],
        start: date,
        end: date,
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        result: dict[str, pd.DataFrame] = {}
        yahoo_tickers = [self._to_yahoo_ticker(t) for t in tickers]

        # Process in batches
        for i in range(0, len(yahoo_tickers), self.BATCH_SIZE):
            batch = yahoo_tickers[i : i + self.BATCH_SIZE]
            try:
                raw = yf.download(
                    batch,
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                    group_by="ticker",
                    threads=True,
                )
                for yt in batch:
                    ticker = self._from_yahoo_ticker(yt)
                    try:
                        if len(batch) == 1:
                            df = raw.copy()
                        else:
                            df = raw[yt].copy() if yt in raw.columns.get_level_values(0) else pd.DataFrame()

                        if df.empty:
                            logger.warning(f"Yahoo: no data for {ticker}")
                            continue

                        df = df.rename(columns=str.lower)
                        df.index.name = "date"
                        df = self._validate(df, ticker)
                        result[ticker] = df
                    except Exception as e:
                        logger.warning(f"Yahoo: failed to parse {ticker}: {e}")

            except Exception as e:
                logger.error(f"Yahoo batch download failed (batch {i}): {e}")

            if i + self.BATCH_SIZE < len(yahoo_tickers):
                time.sleep(self.SLEEP_BETWEEN)

        logger.info(f"Yahoo: fetched {len(result)}/{len(tickers)} tickers")
        return result

    def fetch_single(self, ticker: str, period: str = "5y") -> Optional[pd.DataFrame]:
        """Fetch a single ticker with period string instead of dates."""
        try:
            yt = self._to_yahoo_ticker(ticker)
            raw = yf.download(yt, period=period, auto_adjust=True, progress=False)
            if raw.empty:
                return None
            raw.columns = [c.lower() for c in raw.columns]
            return self._validate(raw, ticker)
        except Exception as e:
            logger.error(f"Yahoo single fetch failed for {ticker}: {e}")
            return None

    def fetch_fundamentals(self, ticker: str) -> dict:
        """Fetch key fundamental ratios from Yahoo Finance."""
        try:
            yt = yf.Ticker(self._to_yahoo_ticker(ticker))
            info = yt.info
            return {
                "pe_ratio": info.get("trailingPE"),
                "pb_ratio": info.get("priceToBook"),
                "market_cap_cr": (info.get("marketCap", 0) or 0) / 1e7,
                "roe": info.get("returnOnEquity"),
                "gross_margin": info.get("grossMargins"),
                "net_margin": info.get("profitMargins"),
                "debt_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "eps_ttm": info.get("trailingEps"),
                "revenue_cr": (info.get("totalRevenue", 0) or 0) / 1e7,
            }
        except Exception as e:
            logger.warning(f"Yahoo fundamentals failed for {ticker}: {e}")
            return {}

    def fetch_universe_batch(self, tickers: list[str], start: date, end: date) -> LoaderResult:
        data = self.fetch_ohlcv(tickers, start, end)
        success = list(data.keys())
        failed = [t for t in tickers if t not in success]
        return LoaderResult(success=success, failed=failed, data=data)
