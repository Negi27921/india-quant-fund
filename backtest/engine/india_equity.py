"""India equity backtest engine — T+1 settlement, NSE costs, circuit rules."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from backtest.engine.metrics import compute_metrics

# ── Cost constants (as of 2024) ───────────────────────────────────────────────
BROKERAGE_PER_ORDER = 20.0          # ₹20 flat per order
STT_SELL_PCT = 0.001                # 0.1% STT on sell side (delivery)
EXCHANGE_CHARGE_PCT = 0.0000297     # NSE transaction charge
SEBI_CHARGE_PCT = 0.000001
STAMP_DUTY_BUY_PCT = 0.00015        # 0.015% on buy
GST_ON_BROKERAGE = 0.18
SLIPPAGE_PCT = 0.0010               # 10 bps round-trip slippage estimate


@dataclass
class Position:
    ticker: str
    quantity: float
    avg_price: float
    buy_date: date
    strategy: str = ""


@dataclass
class Trade:
    ticker: str
    entry_date: date
    exit_date: date | None
    entry_price: float
    exit_price: float | None
    quantity: float
    side: str               # 'LONG'
    strategy: str
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    costs: float = 0.0
    hold_days: int = 0


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list[Trade]
    metrics: dict[str, Any]
    positions_hist: list[dict]


class IndiaEquityEngine:
    """
    Vectorized event-driven backtest engine for Indian equity cash segment.
    Applies: T+1 settlement, STT, exchange charges, stamp duty, slippage.
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000,
        slippage_pct: float = SLIPPAGE_PCT,
        brokerage: float = BROKERAGE_PER_ORDER,
        benchmark_ticker: str = "NIFTY500",
    ):
        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.brokerage = brokerage
        self.benchmark_ticker = benchmark_ticker

    def run(
        self,
        signals: dict[str, pd.Series],        # {ticker: signal_series (1/0)}
        data: dict[str, pd.DataFrame],         # {ticker: OHLCV DataFrame}
        strategy_name: str = "strategy",
        target_weights: dict[str, pd.Series] | None = None,
    ) -> BacktestResult:
        """
        signals: {ticker: pd.Series(index=DatetimeIndex, values=1 or 0)}
        data:    {ticker: pd.DataFrame with OHLC, volume columns}
        target_weights: optional {ticker: weight_series} for weight-based execution
        """
        # Align all tickers on common date index
        all_dates = self._get_trading_dates(data)
        if len(all_dates) < 10:
            raise ValueError("Insufficient data for backtest (< 10 trading days)")

        cash = self.initial_capital
        positions: dict[str, Position] = {}
        trades: list[Trade] = []
        equity_curve: list[tuple[date, float]] = []
        positions_hist: list[dict] = []
        buy_dates: dict[str, date] = {}  # T+1 tracking

        for i, today in enumerate(all_dates):
            today_date = today.date() if hasattr(today, "date") else today

            # Get today's prices
            prices = self._get_prices(data, today)

            # Mark-to-market portfolio value
            portfolio_value = cash
            for ticker, pos in positions.items():
                price = prices.get(ticker, pos.avg_price)
                portfolio_value += pos.quantity * price

            equity_curve.append((today_date, portfolio_value))

            if i == 0:
                continue  # No trading on first day

            # Process exits first (T+1: can only sell stocks bought on T-1 or earlier)
            exits = self._find_exits(signals, positions, prices, today, buy_dates, today_date)
            for ticker in exits:
                pos = positions.pop(ticker)
                exit_price = prices.get(ticker, pos.avg_price)
                exit_price *= (1 - self.slippage_pct / 2)  # slippage on sell
                proceeds, cost = self._calc_sell_costs(pos.quantity, exit_price)
                cash += proceeds
                pnl = proceeds - (pos.quantity * pos.avg_price) - cost
                trades.append(Trade(
                    ticker=ticker,
                    entry_date=pos.buy_date,
                    exit_date=today_date,
                    entry_price=pos.avg_price,
                    exit_price=exit_price,
                    quantity=pos.quantity,
                    side="LONG",
                    strategy=strategy_name,
                    gross_pnl=pos.quantity * (exit_price - pos.avg_price),
                    net_pnl=pnl,
                    costs=cost,
                    hold_days=(today_date - pos.buy_date).days,
                ))

            # Process entries
            entries = self._find_entries(signals, positions, prices, today, today_date)
            for ticker in entries:
                # Target weight or equal weight
                if target_weights and ticker in target_weights:
                    tw = target_weights[ticker]
                    weight = float(tw.get(today, tw.iloc[-1]) if hasattr(tw, 'get') else 0.05)
                else:
                    n_new = len(entries)
                    weight = min(0.05, 0.80 / max(n_new, 1))  # max 5%, spread across entries

                buy_value = portfolio_value * weight
                price = prices.get(ticker, 0)
                if price <= 0 or buy_value < 5000:
                    continue

                buy_price = price * (1 + self.slippage_pct / 2)
                cost, qty = self._calc_buy_costs(buy_value, buy_price)
                if qty < 1 or cost > cash * 0.95:
                    continue

                cash -= cost
                buy_dates[ticker] = today_date
                positions[ticker] = Position(
                    ticker=ticker,
                    quantity=qty,
                    avg_price=buy_price,
                    buy_date=today_date,
                    strategy=strategy_name,
                )

            positions_hist.append({
                "date": today_date,
                "n_positions": len(positions),
                "cash": cash,
                "portfolio_value": portfolio_value,
            })

        # Close all remaining positions at end
        last_prices = self._get_prices(data, all_dates[-1])
        for ticker, pos in positions.items():
            exit_price = last_prices.get(ticker, pos.avg_price)
            proceeds, cost = self._calc_sell_costs(pos.quantity, exit_price)
            cash += proceeds
            trades.append(Trade(
                ticker=ticker,
                entry_date=pos.buy_date,
                exit_date=all_dates[-1].date(),
                entry_price=pos.avg_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                side="LONG",
                strategy=strategy_name,
                gross_pnl=pos.quantity * (exit_price - pos.avg_price),
                net_pnl=proceeds - (pos.quantity * pos.avg_price) - cost,
                costs=cost,
                hold_days=(all_dates[-1].date() - pos.buy_date).days,
            ))

        ec = pd.Series(
            {d: v for d, v in equity_curve},
            name="portfolio_value",
        )
        ec.index = pd.DatetimeIndex(ec.index)

        metrics = compute_metrics(ec, trades, self.initial_capital)
        logger.info(
            f"Backtest complete: Sharpe={metrics.get('sharpe_ratio', 0):.2f}, "
            f"MaxDD={metrics.get('max_drawdown', 0):.1%}, "
            f"Return={metrics.get('total_return', 0):.1%}"
        )

        return BacktestResult(
            equity_curve=ec,
            trades=trades,
            metrics=metrics,
            positions_hist=positions_hist,
        )

    def _get_trading_dates(self, data: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
        all_idx = pd.DatetimeIndex([])
        for df in data.values():
            if df is not None and not df.empty:
                all_idx = all_idx.union(df.index)
        return all_idx.sort_values()

    def _get_prices(self, data: dict[str, pd.DataFrame], dt: Any) -> dict[str, float]:
        prices = {}
        for ticker, df in data.items():
            if df is None or df.empty:
                continue
            try:
                prices[ticker] = float(df.loc[:dt].iloc[-1]["close"])
            except Exception:
                pass
        return prices

    def _find_exits(self, signals, positions, prices, today, buy_dates, today_date) -> list[str]:
        exits = []
        for ticker in list(positions.keys()):
            # T+1: cannot sell on same day as buy
            if buy_dates.get(ticker) == today_date:
                continue
            # Signal turned off
            sig = signals.get(ticker)
            if sig is None:
                exits.append(ticker)
                continue
            try:
                val = float(sig.get(today, sig.iloc[-1]) if hasattr(sig, 'get') else 0)
                if val == 0:
                    exits.append(ticker)
            except Exception:
                exits.append(ticker)
        return exits

    def _find_entries(self, signals, positions, prices, today, today_date) -> list[str]:
        entries = []
        for ticker, sig in signals.items():
            if ticker in positions:
                continue
            try:
                val = float(sig.loc[today] if today in sig.index else 0)
                if val > 0 and prices.get(ticker, 0) > 0:
                    entries.append(ticker)
            except Exception:
                pass
        return entries

    def _calc_buy_costs(self, buy_value: float, price: float) -> tuple[float, float]:
        qty = int(buy_value / price)
        if qty == 0:
            return 0, 0
        gross = qty * price
        stamp = gross * STAMP_DUTY_BUY_PCT
        exchange = gross * EXCHANGE_CHARGE_PCT
        sebi = gross * SEBI_CHARGE_PCT
        gst = self.brokerage * GST_ON_BROKERAGE
        total_cost = gross + stamp + exchange + sebi + self.brokerage + gst
        return total_cost, qty

    def _calc_sell_costs(self, qty: float, price: float) -> tuple[float, float]:
        gross = qty * price
        stt = gross * STT_SELL_PCT
        exchange = gross * EXCHANGE_CHARGE_PCT
        sebi = gross * SEBI_CHARGE_PCT
        gst = self.brokerage * GST_ON_BROKERAGE
        cost = stt + exchange + sebi + self.brokerage + gst
        proceeds = gross - cost
        return proceeds, cost
