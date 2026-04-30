"""NSE data loader — circuit limits, FII/DII flows, delivery percentage."""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
import requests
from loguru import logger

from data.pipeline.loaders.base import BaseLoader

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
}

NSE_BASE = "https://www.nseindia.com"


class NSELoader(BaseLoader):
    name = "nse"
    markets = {"NSE"}
    requires_auth = False

    def __init__(self):
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            s = requests.Session()
            s.headers.update(NSE_HEADERS)
            # Establish cookie
            try:
                s.get(NSE_BASE, timeout=10)
            except Exception:
                pass
            self._session = s
        return self._session

    def is_available(self) -> bool:
        try:
            s = self._get_session()
            r = s.get(f"{NSE_BASE}/api/market-status", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def fetch_ohlcv(self, tickers, start, end, interval="1d") -> dict[str, pd.DataFrame]:
        """NSE is not primary OHLCV source — use Yahoo. Returns empty."""
        return {}

    def fetch_circuit_limits(self, tickers: list[str]) -> dict[str, dict]:
        """Fetch current circuit limits for given tickers."""
        result = {}
        session = self._get_session()
        for ticker in tickers:
            try:
                url = f"{NSE_BASE}/api/quote-equity?symbol={ticker}"
                r = session.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                data = r.json()
                pd_data = data.get("priceInfo", {})
                result[ticker] = {
                    "upper_circuit": pd_data.get("upperCP"),
                    "lower_circuit": pd_data.get("lowerCP"),
                    "last_price": pd_data.get("lastPrice"),
                    "pct_change": pd_data.get("pChange"),
                }
            except Exception as e:
                logger.debug(f"NSE circuit limit failed for {ticker}: {e}")
        return result

    def fetch_fii_dii(self, trade_date: Optional[date] = None) -> dict:
        """Fetch FII/DII net buy-sell data."""
        try:
            session = self._get_session()
            url = f"{NSE_BASE}/api/fiidiiTradeReact"
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                return {}
            rows = r.json()
            if not rows:
                return {}
            latest = rows[0]
            return {
                "date": latest.get("date"),
                "fii_net_cr": self._parse_cr(latest.get("fiiNet")),
                "dii_net_cr": self._parse_cr(latest.get("diiNet")),
                "fii_buy_cr": self._parse_cr(latest.get("fiiBuy")),
                "fii_sell_cr": self._parse_cr(latest.get("fiiSell")),
                "dii_buy_cr": self._parse_cr(latest.get("diiBuy")),
                "dii_sell_cr": self._parse_cr(latest.get("diiSell")),
            }
        except Exception as e:
            logger.warning(f"FII/DII fetch failed: {e}")
            return {}

    def fetch_vix(self) -> Optional[float]:
        """Fetch India VIX current value."""
        try:
            session = self._get_session()
            url = f"{NSE_BASE}/api/allIndices"
            r = session.get(url, timeout=10)
            if r.status_code != 200:
                return None
            indices = r.json().get("data", [])
            for idx in indices:
                if idx.get("indexSymbol") == "India VIX":
                    return float(idx.get("last", 0))
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e}")
        return None

    def fetch_nifty500_list(self) -> list[str]:
        """Return Nifty 500 constituent symbols."""
        try:
            session = self._get_session()
            url = f"{NSE_BASE}/api/equity-stockIndices?index=NIFTY 500"
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                return self._hardcoded_nifty500_sample()
            data = r.json().get("data", [])
            return [row["symbol"] for row in data if row.get("symbol")]
        except Exception as e:
            logger.warning(f"Nifty 500 list fetch failed: {e}, using cached list")
            return self._hardcoded_nifty500_sample()

    def fetch_delivery_pct(self, tickers: list[str], trade_date: date) -> dict[str, float]:
        """Fetch delivery percentage for each ticker on a given date."""
        result = {}
        session = self._get_session()
        date_str = trade_date.strftime("%d-%m-%Y")
        for ticker in tickers:
            try:
                url = f"{NSE_BASE}/api/historical/securityArchives?from={date_str}&to={date_str}&symbol={ticker}&dataType=priceVolumeDeliverable&series=EQ"
                r = session.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                rows = r.json().get("data", [])
                if rows:
                    row = rows[0]
                    del_qty = float(row.get("deliveryQuantity", 0) or 0)
                    traded_qty = float(row.get("tradedQuantity", 1) or 1)
                    result[ticker] = round(del_qty / traded_qty * 100, 2) if traded_qty else 0
            except Exception:
                pass
        return result

    @staticmethod
    def _parse_cr(val: str | None) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(str(val).replace(",", ""))
        except Exception:
            return None

    @staticmethod
    def _hardcoded_nifty500_sample() -> list[str]:
        """Fallback: top 100 NSE symbols when API fails."""
        return [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
            "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
            "TITAN", "BAJFINANCE", "WIPRO", "ULTRACEMCO", "NESTLEIND",
            "POWERGRID", "NTPC", "TECHM", "M&M", "BAJAJFINSV",
            "HCLTECH", "ONGC", "COALINDIA", "TATAMOTORS", "ADANIENT",
            "JSWSTEEL", "GRASIM", "TATASTEEL", "BPCL", "HINDALCO",
            "CIPLA", "DRREDDY", "APOLLOHOSP", "DIVISLAB", "BRITANNIA",
            "EICHERMOT", "HEROMOTOCO", "BAJAJ-AUTO", "SHREECEM", "TATACONSUM",
            "SBILIFE", "HDFCLIFE", "INDUSINDBK", "PIDILITIND", "VEDL",
        ]
