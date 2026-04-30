"""Backtest runner CLI — `python -m backtest.runner --strategy momentum_st`"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from backtest.engine.india_equity import IndiaEquityEngine
from backtest.engine.metrics import compute_metrics
from backtest.validators.walk_forward import WalkForwardValidator
from data.pipeline.loaders.registry import fetch_universe_ohlcv
from data.pipeline.transformers.universe import get_nifty100, get_nifty500
from data.storage import db
from strategies.factor.composite import FactorStrategy
from strategies.momentum.medium_term import MediumTermMomentum
from strategies.momentum.short_term import ShortTermMomentum
from strategies.mean_reversion.rsi_reversion import RSIMeanReversion

app = typer.Typer()
console = Console()

STRATEGY_MAP = {
    "momentum_st": ShortTermMomentum,
    "momentum_mt": MediumTermMomentum,
    "mean_reversion": RSIMeanReversion,
    "factor": FactorStrategy,
}


@app.command()
def main(
    strategy: str = typer.Option("momentum_st", help="Strategy name"),
    start: str = typer.Option(None, help="Start date YYYY-MM-DD"),
    end: str = typer.Option(None, help="End date YYYY-MM-DD"),
    universe: str = typer.Option("nifty100", help="nifty50 | nifty100 | nifty500"),
    capital: float = typer.Option(1_000_000, help="Initial capital ₹"),
    walk_forward: bool = typer.Option(False, help="Run walk-forward validation"),
    save: bool = typer.Option(True, help="Save results to database"),
    output_dir: str = typer.Option("./backtest_results", help="Output directory"),
):
    """Run backtest for a given strategy and print results."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=365 * 5)

    console.print(f"\n[bold blue]Backtest: {strategy}[/bold blue]")
    console.print(f"Period: {start_date} → {end_date} | Capital: ₹{capital:,.0f}")

    # Get universe
    if universe == "nifty500":
        tickers = get_nifty500()
    elif universe == "nifty50":
        from data.pipeline.transformers.universe import get_nifty50
        tickers = get_nifty50()
    else:
        tickers = get_nifty100()

    console.print(f"Universe: {len(tickers)} tickers ({universe})")

    # Fetch data
    console.print("[dim]Fetching OHLCV data...[/dim]")
    result = fetch_universe_ohlcv(tickers, start_date, end_date)
    data = result.data
    console.print(f"Data fetched: {len(data)} tickers ({result.success_rate:.0%} success rate)")

    if len(data) < 20:
        console.print("[red]Insufficient data. Aborting.[/red]")
        raise typer.Exit(1)

    # Get strategy class
    strategy_cls = STRATEGY_MAP.get(strategy)
    if not strategy_cls:
        console.print(f"[red]Unknown strategy: {strategy}[/red]")
        raise typer.Exit(1)

    strat = strategy_cls()

    if walk_forward:
        console.print("[bold]Running walk-forward validation...[/bold]")
        validator = WalkForwardValidator()

        def signal_fn(data_slice):
            signals_raw = strat.generate(data_slice)
            return {
                t: _score_to_signal(s, data_slice[t])
                for t, s in signals_raw.items()
                if t in data_slice
            }

        wf_result = validator.validate(signal_fn, data, capital)
        _print_walk_forward(wf_result)
        if not wf_result.passed:
            console.print(f"[red]Walk-forward FAILED: {wf_result.failure_reasons}[/red]")
        return

    # Single backtest
    console.print("[dim]Generating signals...[/dim]")
    raw_signals = strat.generate(data)
    signals = {
        t: _score_to_signal(s, data[t])
        for t, s in raw_signals.items()
        if t in data
    }
    console.print(f"Signals generated: {len(signals)} tickers")

    engine = IndiaEquityEngine(initial_capital=capital)
    bt_result = engine.run(signals, data, strategy)

    _print_metrics(bt_result.metrics)

    # Save to file and DB
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    bt_result.equity_curve.to_csv(out_path / f"{strategy}_equity_curve.csv")

    if save:
        try:
            db.execute("""
                INSERT INTO backtest_results
                (strategy, start_date, end_date, total_return, annual_return,
                 sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown,
                 win_rate, profit_factor, num_trades, params, equity_curve)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                strategy, str(start_date), str(end_date),
                bt_result.metrics.get("total_return"),
                bt_result.metrics.get("annual_return"),
                bt_result.metrics.get("sharpe_ratio"),
                bt_result.metrics.get("sortino_ratio"),
                bt_result.metrics.get("calmar_ratio"),
                bt_result.metrics.get("max_drawdown"),
                bt_result.metrics.get("win_rate"),
                bt_result.metrics.get("profit_factor"),
                bt_result.metrics.get("num_trades"),
                json.dumps(strat.params),
                json.dumps(bt_result.equity_curve.to_dict()),
            ])
            console.print("[green]Results saved to database[/green]")
        except Exception as e:
            logger.warning(f"Failed to save backtest results: {e}")


def _score_to_signal(score: float, df: pd.DataFrame) -> pd.Series:
    """Convert a static signal score to a time series (all 1s if score > 0)."""
    import pandas as pd
    return pd.Series(1.0 if score > 0 else 0.0, index=df.index)


def _print_metrics(metrics: dict) -> None:
    table = Table(title="Backtest Results", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    rows = [
        ("Total Return", f"{metrics.get('total_return', 0):.1%}"),
        ("Annual Return", f"{metrics.get('annual_return', 0):.1%}"),
        ("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.3f}"),
        ("Sortino Ratio", f"{metrics.get('sortino_ratio', 0):.3f}"),
        ("Calmar Ratio", f"{metrics.get('calmar_ratio', 0):.3f}"),
        ("Max Drawdown", f"{metrics.get('max_drawdown', 0):.1%}"),
        ("Win Rate", f"{metrics.get('win_rate', 0):.1%}"),
        ("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}"),
        ("Avg Hold Days", f"{metrics.get('avg_hold_days', 0):.1f}"),
        ("Num Trades", str(metrics.get("num_trades", 0))),
        ("Final Value", f"₹{metrics.get('final_value', 0):,.0f}"),
    ]
    for name, val in rows:
        table.add_row(name, val)

    console.print(table)


def _print_walk_forward(result) -> None:
    table = Table(title="Walk-Forward Validation", show_header=True, header_style="bold cyan")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    agg = result.aggregate_metrics
    for k, v in agg.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)
    status = "[green]PASSED[/green]" if result.passed else "[red]FAILED[/red]"
    console.print(f"Walk-Forward: {status}")


if __name__ == "__main__":
    import pandas as pd
    app()
