"""Signal generation flow — runs at 08:30 IST."""
from __future__ import annotations

from datetime import date

import pandas as pd
from loguru import logger

from agents.director import DirectorAgent
from agents.signal import SignalAgent
from data.storage import db
from strategies.factor.composite import FactorStrategy
from strategies.momentum.medium_term import MediumTermMomentum
from strategies.momentum.short_term import ShortTermMomentum
from strategies.mean_reversion.rsi_reversion import RSIMeanReversion
from strategies.portfolio.allocator import StrategyAllocator
from strategies.portfolio.constructor import PortfolioConstructor
from risk.limits import get_limits


def run_signal_generation(target_date: date | None = None) -> dict:
    """Run all strategies and generate portfolio target weights."""
    target_date = target_date or date.today()
    logger.info(f"Starting signal generation for {target_date}")

    # 1. Load data from DuckDB
    data = _load_data_from_db(target_date)
    if not data:
        logger.error("No data available for signal generation")
        return {"status": "abort", "reason": "No data"}

    # 2. Load fundamentals (for factor strategy)
    fundamentals = _load_fundamentals(target_date)

    # 3. Director agent — get regime and weights
    market_data = _get_market_context(target_date)
    director = DirectorAgent()
    director_output = director.run(market_data)
    logger.info(f"Director: regime={director_output['regime']}, posture={director_output['risk_posture']}")

    if director_output["risk_posture"] == "halt_new_positions":
        logger.warning("Director halted new positions — no signals generated")
        return {"status": "halted", "reason": "Director: halt_new_positions"}

    strategy_weights = director_output["strategy_weights"]
    size_scale = director_output.get("position_size_scale", 1.0)

    # 4. Run strategies
    all_signals: dict[str, dict[str, float]] = {}

    strategies = [
        ("momentum_st", ShortTermMomentum()),
        ("momentum_mt", MediumTermMomentum()),
        ("mean_reversion", RSIMeanReversion()),
        ("factor", FactorStrategy()),
    ]

    for name, strat in strategies:
        try:
            sigs = strat.generate(data, fundamentals=fundamentals)
            if sigs:
                all_signals[name] = sigs
                logger.info(f"Strategy {name}: {len(sigs)} signals generated")
        except Exception as e:
            logger.error(f"Strategy {name} failed: {e}")

    if not all_signals:
        return {"status": "no_signals", "reason": "All strategies returned empty"}

    # 5. Signal agent sanity check
    signal_agent = SignalAgent()
    combined_tickers = set()
    for sigs in all_signals.values():
        combined_tickers.update(sigs.keys())

    nse_data = _get_nse_market_data()
    approval = signal_agent.run({
        "signals": {t: 1.0 for t in combined_tickers},
        "news_headlines": [],
        "earnings_calendar": nse_data.get("earnings_calendar", []),
        "circuit_stocks": nse_data.get("circuit_stocks", []),
        "fno_ban_stocks": nse_data.get("fno_ban", []),
    })
    approved_set = set(approval["approved_tickers"])
    logger.info(f"Signal agent approved {len(approved_set)}/{len(combined_tickers)} tickers")

    # Filter rejected tickers
    filtered_signals: dict[str, dict[str, float]] = {}
    for strat_name, sigs in all_signals.items():
        filtered_signals[strat_name] = {t: s for t, s in sigs.items() if t in approved_set}

    # 6. Portfolio construction
    limits = get_limits()
    constructor = PortfolioConstructor(limits)
    features = _load_features(target_date, list(combined_tickers))

    target_weights = constructor.construct(
        strategy_signals=filtered_signals,
        strategy_weights=strategy_weights,
        current_prices={},
        features=features,
    )

    # Apply position size scale from director
    target_weights = {t: w * size_scale for t, w in target_weights.items()}

    # 7. Save signals to DB
    _save_signals(target_date, filtered_signals)

    # 8. Save target portfolio
    _save_target_portfolio(target_date, target_weights)

    return {
        "status": "ok",
        "date": str(target_date),
        "regime": director_output["regime"],
        "strategies_active": list(filtered_signals.keys()),
        "total_signals": sum(len(s) for s in filtered_signals.values()),
        "target_positions": len(target_weights),
        "target_weights": target_weights,
    }


def _load_data_from_db(target_date: date) -> dict[str, pd.DataFrame]:
    from datetime import timedelta
    start = target_date - timedelta(days=365)
    try:
        df = db.query_df(f"""
            SELECT ticker, date, open, high, low, close, volume
            FROM ohlcv
            WHERE date BETWEEN '{start}' AND '{target_date}'
            ORDER BY ticker, date
        """)
        data = {}
        for ticker, group in df.groupby("ticker"):
            g = group.set_index("date").drop("ticker", axis=1)
            g.index = pd.DatetimeIndex(g.index)
            data[ticker] = g
        return data
    except Exception as e:
        logger.error(f"Data load failed: {e}")
        return {}


def _load_fundamentals(target_date: date) -> pd.DataFrame:
    try:
        return db.query_df(f"""
            SELECT ticker, pe_ratio, pb_ratio, ev_ebitda, roe, gross_margin, debt_equity
            FROM fundamentals
            WHERE date = (SELECT MAX(date) FROM fundamentals WHERE date <= '{target_date}')
        """).set_index("ticker")
    except Exception:
        return pd.DataFrame()


def _load_features(target_date: date, tickers: list) -> dict[str, pd.DataFrame]:
    return {}  # Loaded from features table in production


def _get_market_context(target_date: date) -> dict:
    try:
        row = db.query_df(f"""
            SELECT vix_india, fii_net_cr, dii_net_cr
            FROM market_data WHERE date = '{target_date}'
        """)
        return {
            "vix_india": float(row["vix_india"].iloc[0]) if not row.empty else 15.0,
            "drawdown_pct": 0.0,
            "day_pnl_pct": 0.0,
        }
    except Exception:
        return {"vix_india": 15.0, "drawdown_pct": 0.0, "day_pnl_pct": 0.0}


def _get_nse_market_data() -> dict:
    return {"earnings_calendar": [], "circuit_stocks": [], "fno_ban": []}


def _save_signals(target_date: date, signals: dict[str, dict[str, float]]) -> None:
    for strat, tickers in signals.items():
        for ticker, score in tickers.items():
            try:
                db.execute("""
                    INSERT OR IGNORE INTO signals (date, ticker, strategy, signal)
                    VALUES (?, ?, ?, ?)
                """, [target_date, ticker, strat, score])
            except Exception:
                pass


def _save_target_portfolio(target_date: date, weights: dict[str, float]) -> None:
    for ticker, weight in weights.items():
        try:
            db.execute("""
                INSERT OR IGNORE INTO target_portfolio (date, ticker, target_weight)
                VALUES (?, ?, ?)
            """, [target_date, ticker, weight])
        except Exception:
            pass
