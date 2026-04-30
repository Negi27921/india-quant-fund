"""
Historical data backfill — loads 5 years of OHLCV data for the Nifty 500 universe.
Run with: python scripts/backfill.py [--years 5] [--universe nifty100]
"""
import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()


def parse_args():
    p = argparse.ArgumentParser(description="Backfill historical OHLCV data")
    p.add_argument("--years", type=int, default=5, help="Years of history to load")
    p.add_argument("--universe", choices=["nifty50", "nifty100", "nifty500"], default="nifty100")
    p.add_argument("--skip-existing", action="store_true", help="Skip tickers already in DB")
    return p.parse_args()


def main():
    args = parse_args()

    console.print(f"\n[bold blue]IQF Backfill[/bold blue] — {args.years}Y of {args.universe.upper()}\n")

    # Load universe
    from data.pipeline.transformers.universe import get_nifty500, apply_universe_filters
    from data.pipeline.loaders.registry import fetch_universe_ohlcv
    from data.pipeline.validators.ohlcv import validate_universe
    from data.pipeline.transformers.adjustments import apply_adjustments
    from data.pipeline.transformers.features import compute_features
    from data.storage.db import db

    universe = get_nifty500()
    if args.universe == "nifty50":
        universe = universe[:50]
    elif args.universe == "nifty100":
        universe = universe[:100]

    end = datetime.today()
    start = end - timedelta(days=args.years * 365 + 30)  # buffer

    console.print(f"Fetching [yellow]{len(universe)}[/yellow] tickers from "
                  f"[cyan]{start.strftime('%Y-%m-%d')}[/cyan] to "
                  f"[cyan]{end.strftime('%Y-%m-%d')}[/cyan]\n")

    # Fetch in batches of 50
    batch_size = 50
    all_data: list[pd.DataFrame] = []
    failed: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching OHLCV...", total=len(universe))

        for i in range(0, len(universe), batch_size):
            batch = universe[i : i + batch_size]
            progress.update(task, description=f"Fetching {batch[0]}…")

            result = fetch_universe_ohlcv(batch, str(start.date()), str(end.date()))
            if result.data is not None and not result.data.empty:
                all_data.append(result.data)
            failed.extend(result.failed_tickers)
            progress.advance(task, len(batch))

    if not all_data:
        console.print("[red]No data fetched. Check network and API keys.[/red]")
        sys.exit(1)

    combined = pd.concat(all_data, ignore_index=True)
    console.print(f"\n[green]✓[/green] Fetched {len(combined):,} rows across {combined['ticker'].nunique()} tickers")

    if failed:
        console.print(f"[yellow]⚠[/yellow] Failed: {len(failed)} tickers — {', '.join(failed[:10])}")

    # Validate
    console.print("\nValidating data quality…")
    from data.pipeline.validators.ohlcv import validate_universe
    validated, report = validate_universe(combined)
    console.print(f"[green]✓[/green] {len(validated):,} clean rows after validation")

    # Adjust for corporate actions
    console.print("Applying corporate action adjustments…")
    adjusted = apply_adjustments(validated)

    # Store OHLCV
    console.print("Writing to DuckDB…")
    db.upsert_df(
        adjusted,
        "ohlcv",
        conflict_cols=["ticker", "date"],
    )

    # Compute features
    console.print("Computing technical features…")
    tickers_done = 0
    for ticker in adjusted["ticker"].unique():
        ticker_df = adjusted[adjusted["ticker"] == ticker].copy()
        if len(ticker_df) < 30:
            continue
        try:
            feats = compute_features(ticker_df)
            db.upsert_df(feats, "features", conflict_cols=["ticker", "date"])
            tickers_done += 1
        except Exception as e:
            console.print(f"[yellow]Feature compute failed for {ticker}: {e}[/yellow]")

    console.print(f"[green]✓[/green] Features computed for {tickers_done} tickers")

    console.print("\n[bold green]Backfill complete![/bold green]")
    console.print(f"  OHLCV rows: {len(adjusted):,}")
    console.print(f"  Tickers: {adjusted['ticker'].nunique()}")
    console.print(f"  Date range: {adjusted['date'].min()} → {adjusted['date'].max()}\n")


if __name__ == "__main__":
    main()
