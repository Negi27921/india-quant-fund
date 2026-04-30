"""Real-time PnL tracker — portfolio valuation and performance metrics."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd
from loguru import logger

from data.storage import db
from execution.router import SmartOrderRouter


class PnLTracker:
    def __init__(self, router: SmartOrderRouter, initial_capital: float):
        self.router = router
        self.initial_capital = initial_capital
        self._peak_value = initial_capital
        self._day_start_value: float = initial_capital

    def snapshot(self) -> dict:
        """Take a portfolio valuation snapshot."""
        positions = self.router.get_all_positions()
        cash = self.router.get_portfolio_value()

        invested = sum(p.quantity * p.current_price for p in positions)
        unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        portfolio_value = cash + invested

        # Update peak
        if portfolio_value > self._peak_value:
            self._peak_value = portfolio_value

        drawdown_pct = (portfolio_value - self._peak_value) / self._peak_value * 100
        day_pnl = portfolio_value - self._day_start_value
        day_pnl_pct = day_pnl / self._day_start_value * 100 if self._day_start_value else 0

        total_return_pct = (portfolio_value - self.initial_capital) / self.initial_capital * 100

        snap = {
            "timestamp": datetime.now().isoformat(),
            "portfolio_value": round(portfolio_value, 2),
            "cash": round(cash, 2),
            "invested": round(invested, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "day_pnl": round(day_pnl, 2),
            "day_pnl_pct": round(day_pnl_pct, 4),
            "drawdown_pct": round(drawdown_pct, 4),
            "peak_value": round(self._peak_value, 2),
            "total_return_pct": round(total_return_pct, 4),
            "n_positions": len(positions),
            "positions": [
                {
                    "ticker": p.ticker,
                    "quantity": p.quantity,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "pnl_pct": (p.current_price - p.avg_price) / p.avg_price * 100 if p.avg_price else 0,
                }
                for p in positions
            ],
        }
        return snap

    def save_daily_snapshot(self, snap: dict) -> None:
        """Save end-of-day snapshot to DuckDB."""
        try:
            today = date.today()
            db.execute("""
                INSERT OR REPLACE INTO daily_pnl (
                    date, portfolio_value, cash, invested, day_pnl, day_pnl_pct,
                    unrealized_pnl, drawdown_pct, num_positions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                today,
                snap["portfolio_value"],
                snap["cash"],
                snap["invested"],
                snap["day_pnl"],
                snap["day_pnl_pct"],
                snap["unrealized_pnl"],
                snap["drawdown_pct"],
                snap["n_positions"],
            ])
        except Exception as e:
            logger.error(f"Failed to save daily PnL snapshot: {e}")

    def reset_day_start(self) -> None:
        snap = self.snapshot()
        self._day_start_value = snap["portfolio_value"]

    def get_equity_curve(self, days: int = 252) -> pd.DataFrame:
        """Return historical equity curve from DuckDB."""
        try:
            return db.query_df(f"""
                SELECT date, portfolio_value, day_pnl_pct, drawdown_pct
                FROM daily_pnl
                ORDER BY date DESC
                LIMIT {days}
            """)
        except Exception:
            return pd.DataFrame()
