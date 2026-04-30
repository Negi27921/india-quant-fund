"""Screener.in loader — fundamental data (P/E, P/B, ROE, etc.)."""
from __future__ import annotations

import os
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup
from loguru import logger

SCREENER_BASE = "https://www.screener.in"
SCREENER_API = "https://www.screener.in/api/company"


class ScreenerLoader:
    name = "screener"
    markets = {"NSE", "BSE"}
    requires_auth = False  # Cookie-based auth for better limits

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "text/html,application/xhtml+xml",
            "Referer": SCREENER_BASE,
        })
        cookie = os.getenv("SCREENER_SESSION_COOKIE", "")
        if cookie:
            self._session.cookies.set("sessionid", cookie, domain=".screener.in")

    def is_available(self) -> bool:
        try:
            r = self._session.get(SCREENER_BASE, timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def fetch_fundamentals(self, ticker: str) -> dict:
        """Scrape key ratios from Screener.in company page."""
        try:
            url = f"{SCREENER_BASE}/company/{ticker}/consolidated/"
            r = self._session.get(url, timeout=15)
            if r.status_code == 404:
                url = f"{SCREENER_BASE}/company/{ticker}/"
                r = self._session.get(url, timeout=15)
            if r.status_code != 200:
                logger.debug(f"Screener: {ticker} returned {r.status_code}")
                return {}
            return self._parse_ratios(r.text, ticker)
        except Exception as e:
            logger.debug(f"Screener fetch failed for {ticker}: {e}")
            return {}

    def fetch_batch(self, tickers: list[str], sleep: float = 1.0) -> dict[str, dict]:
        """Fetch fundamentals for multiple tickers with rate limiting."""
        result = {}
        for i, ticker in enumerate(tickers):
            data = self.fetch_fundamentals(ticker)
            if data:
                result[ticker] = data
            if i < len(tickers) - 1:
                time.sleep(sleep)
        logger.info(f"Screener: fetched {len(result)}/{len(tickers)} tickers")
        return result

    def _parse_ratios(self, html: str, ticker: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        ratios = {}

        # Parse top ratios section
        for li in soup.select("ul#top-ratios li"):
            name_el = li.select_one(".name")
            val_el = li.select_one(".value, .number")
            if name_el and val_el:
                name = name_el.get_text(strip=True).lower()
                val_text = val_el.get_text(strip=True)
                val = self._parse_number(val_text)
                if "stock p/e" in name or "p/e" == name:
                    ratios["pe_ratio"] = val
                elif "price to book" in name or "p/b" in name:
                    ratios["pb_ratio"] = val
                elif "return on equity" in name or "roe" in name:
                    ratios["roe"] = val
                elif "return on capital" in name or "roce" in name:
                    ratios["roce"] = val
                elif "debt to equity" in name:
                    ratios["debt_equity"] = val
                elif "current ratio" in name:
                    ratios["current_ratio"] = val
                elif "market cap" in name:
                    ratios["market_cap_cr"] = val

        # Parse earnings data from table
        eps_data = self._parse_eps(soup)
        ratios.update(eps_data)

        return ratios

    def _parse_eps(self, soup: BeautifulSoup) -> dict:
        """Extract latest EPS from profit/loss table."""
        try:
            table = soup.find("section", {"id": "profit-loss"})
            if not table:
                return {}
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if cells and "eps" in cells[0].get_text(strip=True).lower():
                    # Get the most recent (last) column
                    vals = [self._parse_number(c.get_text(strip=True)) for c in cells[1:]]
                    vals = [v for v in vals if v is not None]
                    return {"eps_ttm": vals[-1] if vals else None}
        except Exception:
            pass
        return {}

    @staticmethod
    def _parse_number(text: str) -> Optional[float]:
        text = text.strip().replace(",", "").replace("%", "").replace("Cr.", "")
        match = re.search(r"[-+]?\d+\.?\d*", text)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
        return None
