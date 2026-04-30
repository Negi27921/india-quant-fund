"""Universe construction and filtering for Indian equity strategies."""
from __future__ import annotations

from datetime import date

import pandas as pd
from loguru import logger

from data.pipeline.loaders.nse import NSELoader
from data.storage import db


NIFTY50_TICKERS = [
    "ADANIPORTS", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV",
    "BAJFINANCE", "BHARTIARTL", "BPCL", "BRITANNIA", "CIPLA",
    "COALINDIA", "DIVISLAB", "DRREDDY", "EICHERMOT", "GRASIM",
    "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO",
    "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY", "ITC",
    "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE",
    "SBILIFE", "SBIN", "SHREECEM", "SUNPHARMA", "TATACONSUM",
    "TATAMOTORS", "TATASTEEL", "TCS", "TECHM", "TITAN",
    "ULTRACEMCO", "UPL", "WIPRO", "ADANIENT", "APOLLOHOSP",
]

NIFTY100_EXTRAS = [
    "ABB", "ADANIGREEN", "AMBUJACEM", "AUROPHARMA", "BANDHANBNK",
    "BERGEPAINT", "BOSCHLTD", "CADILAHC", "CHOLAFIN", "CUMMINSIND",
    "DABUR", "DLF", "GAIL", "GODREJCP", "HAVELLS",
    "HDFC", "ICICIGI", "ICICIPRULI", "IDFCFIRSTB", "IGL",
    "INDIGO", "INDUSTOWER", "JUBLFOOD", "LUPIN", "MCDOWELL-N",
    "MFSL", "MOTHERSUMI", "MPHASIS", "MUTHOOTFIN", "PAGEIND",
    "PEL", "PERSISTENT", "PIIND", "PNB", "SBICARD",
    "SRF", "TORNTPHARM", "TRENT", "VEDL", "ZOMATO",
]

SECTOR_MAP: dict[str, str] = {
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy", "GAIL": "Energy",
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT",
    "HDFCBANK": "Financials", "ICICIBANK": "Financials", "AXISBANK": "Financials",
    "KOTAKBANK": "Financials", "SBIN": "Financials", "BAJFINANCE": "Financials",
    "INDUSINDBK": "Financials", "BAJAJFINSV": "Financials",
    "SUNPHARMA": "Healthcare", "DRREDDY": "Healthcare", "CIPLA": "Healthcare",
    "DIVISLAB": "Healthcare", "APOLLOHOSP": "Healthcare",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "DABUR": "FMCG", "GODREJCP": "FMCG",
    "MARUTI": "Auto", "M&M": "Auto", "TATAMOTORS": "Auto",
    "BAJAJ-AUTO": "Auto", "HEROMOTOCO": "Auto", "EICHERMOT": "Auto",
    "LT": "Infrastructure", "POWERGRID": "Infrastructure", "NTPC": "Utilities",
    "COALINDIA": "Materials", "TATASTEEL": "Materials", "JSWSTEEL": "Materials",
    "HINDALCO": "Materials", "GRASIM": "Cement", "ULTRACEMCO": "Cement",
    "TITAN": "Consumer", "ASIANPAINT": "Consumer",
}


def get_nifty50() -> list[str]:
    return NIFTY50_TICKERS.copy()


def get_nifty100() -> list[str]:
    return list(set(NIFTY50_TICKERS + NIFTY100_EXTRAS))


def get_nifty500(use_cache: bool = True) -> list[str]:
    """Return Nifty 500 tickers. Tries NSE API, falls back to cached list."""
    if use_cache:
        try:
            cached = db.query_df(
                "SELECT ticker FROM universe WHERE is_active = TRUE LIMIT 500"
            )
            if len(cached) >= 200:
                return cached["ticker"].tolist()
        except Exception:
            pass

    try:
        loader = NSELoader()
        tickers = loader.fetch_nifty500_list()
        if len(tickers) >= 200:
            return tickers
    except Exception as e:
        logger.warning(f"NSE Nifty500 list failed: {e}")

    return get_nifty100()  # safe fallback


def apply_universe_filters(
    tickers: list[str],
    features: dict[str, pd.DataFrame],
    min_adv_cr: float = 5.0,
    min_price: float = 50.0,
    min_market_cap_cr: float = 500.0,
    circuit_limits: dict | None = None,
) -> list[str]:
    """Filter tickers by liquidity, price, and circuit limits."""
    filtered = []
    circuit_limits = circuit_limits or {}

    for ticker in tickers:
        df = features.get(ticker)
        if df is None or df.empty:
            continue

        latest = df.iloc[-1]

        # Price filter
        price = latest.get("close", 0)
        if price < min_price:
            continue

        # Liquidity filter (ADV)
        adv = latest.get("adv_20d", 0) / 1e7  # convert to Cr
        if adv < min_adv_cr:
            continue

        # Circuit limit filter
        cl = circuit_limits.get(ticker, {})
        if cl:
            upper = cl.get("upper_circuit")
            lower = cl.get("lower_circuit")
            if upper and price >= upper * 0.99:
                continue  # Near upper circuit — don't buy
            if lower and price <= lower * 1.01:
                continue  # Near lower circuit — don't sell into

        filtered.append(ticker)

    return filtered


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker, "Other")


def get_sector_exposure(positions: dict[str, float]) -> dict[str, float]:
    """Return sector -> total weight mapping."""
    sector_exp: dict[str, float] = {}
    for ticker, weight in positions.items():
        sector = get_sector(ticker)
        sector_exp[sector] = sector_exp.get(sector, 0) + weight
    return sector_exp
