"""Prefect-based scheduler for all daily flows."""
from __future__ import annotations

import os
from datetime import date, time
from zoneinfo import ZoneInfo

from loguru import logger

IST = ZoneInfo("Asia/Kolkata")

try:
    from prefect import flow, task
    from prefect.schedules import CronSchedule
    HAS_PREFECT = True
except ImportError:
    HAS_PREFECT = False
    # Fallback: plain functions with schedule library
    logger.warning("Prefect not installed — using schedule fallback")


def _make_flow(fn):
    """Wrap function as Prefect flow if available."""
    if HAS_PREFECT:
        return flow(fn)
    return fn


@_make_flow
def daily_data_flow():
    from orchestration.flows.daily_pipeline import run_daily_data_pipeline
    result = run_daily_data_pipeline()
    if result.get("status") == "abort":
        raise RuntimeError(f"Data pipeline aborted: {result.get('reason')}")
    return result


@_make_flow
def signal_generation_flow():
    from orchestration.flows.signal_generation import run_signal_generation
    return run_signal_generation()


@_make_flow
def execution_flow():
    capital = float(os.getenv("INITIAL_CAPITAL", "100000"))
    from orchestration.flows.execution_flow import run_execution_flow
    return run_execution_flow(capital=capital)


@_make_flow
def eod_reporting_flow():
    from agents.reporting import ReportingAgent
    from data.storage import db

    # Pull today's metrics
    today = str(date.today())
    metrics_df = db.query_df(f"""
        SELECT * FROM daily_pnl WHERE date = '{today}'
    """)
    metrics = metrics_df.iloc[0].to_dict() if not metrics_df.empty else {}
    trades_df = db.query_df(f"SELECT * FROM orders WHERE DATE(created_at) = '{today}'")

    agent = ReportingAgent()
    result = agent.run({
        "type": "daily",
        "metrics": metrics,
        "trades": trades_df.to_dict("records"),
        "positions": [],
    })
    return result


def run_scheduler():
    """Run schedules using the schedule library (no Prefect required)."""
    import schedule
    import time as time_mod

    logger.info("Starting scheduler (IST timezone)")

    schedule.every().day.at("06:00").do(daily_data_flow)
    schedule.every().day.at("08:30").do(signal_generation_flow)
    schedule.every().day.at("09:10").do(execution_flow)
    schedule.every().day.at("16:05").do(eod_reporting_flow)

    logger.info("Scheduler started. Waiting for jobs...")
    while True:
        schedule.run_pending()
        time_mod.sleep(60)


if __name__ == "__main__":
    run_scheduler()
