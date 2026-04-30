"""Shared test fixtures."""
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from unittest.mock import MagicMock, patch


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """100 days of synthetic OHLCV data for RELIANCE."""
    n = 100
    dates = pd.date_range(end=date.today(), periods=n, freq="B")
    closes = 2500 + np.cumsum(np.random.normal(0, 15, n))
    opens = closes + np.random.normal(0, 5, n)
    highs = np.maximum(opens, closes) + abs(np.random.normal(0, 10, n))
    lows = np.minimum(opens, closes) - abs(np.random.normal(0, 10, n))
    volumes = np.random.randint(100_000, 5_000_000, n).astype(float)

    return pd.DataFrame({
        "ticker": "RELIANCE.NS",
        "date": dates.date,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


@pytest.fixture
def sample_universe_ohlcv(sample_ohlcv) -> pd.DataFrame:
    """Multi-ticker OHLCV for a 10-stock universe."""
    tickers = [
        "RELIANCE.NS", "INFY.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS",
        "WIPRO.NS", "LT.NS", "AXISBANK.NS", "SBIN.NS", "BAJFINANCE.NS",
    ]
    frames = []
    for t in tickers:
        df = sample_ohlcv.copy()
        df["ticker"] = t
        df["close"] += np.random.normal(0, 50, len(df))
        df["close"] = df["close"].clip(100)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def mock_db():
    """Mock DuckDB connection."""
    db = MagicMock()
    db.query_df.return_value = pd.DataFrame()
    return db


@pytest.fixture
def mock_risk_limits():
    """Standard risk limits for testing."""
    from risk.limits import RiskLimits, PositionLimits, SectorLimits, LiquidityLimits
    from risk.limits import PortfolioLimits, DrawdownLimits, CircuitBreakerLimits
    from risk.limits import KillSwitchConfig, OrderLimits

    return RiskLimits(
        position=PositionLimits(
            max_single_stock_pct=5.0,
            min_position_pct=0.5,
            max_positions=30,
            min_order_value=5000,
            max_order_value=2_000_000,
        ),
        sector=SectorLimits(
            max_sector_exposure_pct=20.0,
            min_sector_stocks=2,
        ),
        liquidity=LiquidityLimits(
            max_adv_participation_pct=5.0,
            min_adv_crore=5.0,
            adv_lookback_days=10,
        ),
        portfolio=PortfolioLimits(
            target_vol_annual=0.10,
            half_kelly=True,
            max_leverage=1.0,
        ),
        drawdown=DrawdownLimits(
            drawdown_alert_pct=8.0,
            drawdown_kill_switch_pct=12.0,
            daily_loss_limit_pct=2.0,
            max_consecutive_loss_days=5,
        ),
        circuit=CircuitBreakerLimits(
            upper_circuit_buffer_pct=1.0,
            lower_circuit_buffer_pct=1.0,
        ),
        kill_switch=KillSwitchConfig(
            halt_file_path=".kill_switch_test",
            notify_on_trigger=False,
        ),
        orders=OrderLimits(
            max_orders_per_day=50,
            order_timeout_minutes=30,
        ),
    )
