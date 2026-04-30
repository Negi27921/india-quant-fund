"""Performance metrics — Sharpe, Sortino, Calmar, drawdown, win rate."""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backtest.engine.india_equity import Trade

TRADING_DAYS = 252
RISK_FREE_RATE = 0.065  # 6.5% RBI repo rate approximate


def compute_metrics(
    equity_curve: pd.Series,
    trades: list["Trade"],
    initial_capital: float,
) -> dict:
    if equity_curve.empty or len(equity_curve) < 2:
        return {}

    returns = equity_curve.pct_change().dropna()
    total_return = (equity_curve.iloc[-1] - initial_capital) / initial_capital
    n_years = len(equity_curve) / TRADING_DAYS
    annual_return = (1 + total_return) ** (1 / max(n_years, 0.001)) - 1

    # Sharpe
    excess = returns - RISK_FREE_RATE / TRADING_DAYS
    sharpe = (excess.mean() / (returns.std() + 1e-9)) * np.sqrt(TRADING_DAYS)

    # Sortino (downside deviation)
    downside = returns[returns < 0]
    sortino = (excess.mean() / (downside.std() + 1e-9)) * np.sqrt(TRADING_DAYS)

    # Max drawdown
    rolling_max = equity_curve.expanding().max()
    drawdowns = (equity_curve - rolling_max) / rolling_max
    max_drawdown = float(drawdowns.min())

    # Calmar
    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

    # Win rate & profit factor
    win_rate, profit_factor, avg_win, avg_loss, avg_hold = _trade_stats(trades)

    # Volatility
    annual_vol = float(returns.std() * np.sqrt(TRADING_DAYS))

    # Value at Risk (95%)
    var_95 = float(np.percentile(returns, 5)) if len(returns) > 10 else 0

    return {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "calmar_ratio": round(calmar, 3),
        "max_drawdown": round(max_drawdown, 4),
        "annual_volatility": round(annual_vol, 4),
        "var_95": round(var_95, 4),
        "win_rate": round(win_rate, 3),
        "profit_factor": round(profit_factor, 3),
        "avg_win_pct": round(avg_win, 4),
        "avg_loss_pct": round(avg_loss, 4),
        "avg_hold_days": round(avg_hold, 1),
        "num_trades": len(trades),
        "initial_capital": initial_capital,
        "final_value": round(float(equity_curve.iloc[-1]), 2),
    }


def _trade_stats(trades: list) -> tuple[float, float, float, float, float]:
    if not trades:
        return 0, 0, 0, 0, 0
    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl <= 0]
    win_rate = len(wins) / len(trades)
    total_win = sum(wins)
    total_loss = abs(sum(losses))
    profit_factor = total_win / max(total_loss, 1)
    avg_win_pct = np.mean([t.net_pnl / (t.entry_price * t.quantity) for t in trades if t.net_pnl > 0]) if wins else 0
    avg_loss_pct = np.mean([t.net_pnl / (t.entry_price * t.quantity) for t in trades if t.net_pnl < 0]) if losses else 0
    avg_hold = np.mean([t.hold_days for t in trades]) if trades else 0
    return win_rate, profit_factor, avg_win_pct, avg_loss_pct, avg_hold


def compute_drawdown_series(equity: pd.Series) -> pd.Series:
    rolling_max = equity.expanding().max()
    return (equity - rolling_max) / rolling_max


def compute_rolling_sharpe(returns: pd.Series, window: int = 63) -> pd.Series:
    excess = returns - RISK_FREE_RATE / TRADING_DAYS
    return (excess.rolling(window).mean() / (returns.rolling(window).std() + 1e-9)) * np.sqrt(TRADING_DAYS)
