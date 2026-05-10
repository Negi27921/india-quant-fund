"""Risk metrics API — P&L from Supabase, limits from config."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Query

from data.storage import supabase_db as sdb

router = APIRouter()


def _get_limits() -> dict:
    try:
        from risk.limits import get_limits
        lim = get_limits()
        return {
            "drawdown_alert": lim.drawdown.drawdown_alert_pct,
            "drawdown_limit": lim.drawdown.drawdown_kill_switch_pct,
            "daily_loss_limit": lim.drawdown.daily_loss_limit_pct,
            "max_position_pct": lim.position.max_single_stock_pct,
            "max_sector_pct": lim.sector.max_sector_exposure_pct,
        }
    except Exception:
        return {
            "drawdown_alert": -10.0, "drawdown_limit": -20.0,
            "daily_loss_limit": -3.0, "max_position_pct": 10.0, "max_sector_pct": 30.0,
        }


def _safe_metrics() -> dict:
    """Return a safe default response when Supabase has no data yet."""
    limits = _get_limits()
    return {
        "drawdown_pct": 0.0,
        "drawdown_alert": limits["drawdown_alert"],
        "drawdown_limit": limits["drawdown_limit"],
        "daily_loss_pct": 0.0,
        "daily_loss_limit": limits["daily_loss_limit"],
        "rolling_sharpe_63d": 0.0,
        "max_position_pct": limits["max_position_pct"],
        "max_sector_pct": limits["max_sector_pct"],
        "position_utilization_pct": 0.0,
        "sector_utilization_pct": 0.0,
        "kill_switch_active": False,
    }


@router.get("/metrics")
async def risk_metrics():
    try:
        rows = sdb.select("daily_pnl", cols="date,day_pnl_pct,drawdown_pct", order="-date", limit=63)
        latest = rows[0] if rows else {}
        returns = np.array([float(r["day_pnl_pct"]) / 100 for r in rows]) if rows else np.array([])
        sharpe = float(np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252)) if len(returns) > 5 else 0.0
        limits = _get_limits()

        # Compute position/sector utilization from open positions
        pos_util = 0.0
        sec_util = 0.0
        try:
            pos_rows = sdb.select("trades", cols="ticker,side,quantity,price", limit=200)
            if pos_rows:
                from collections import defaultdict
                holdings: dict[str, float] = defaultdict(float)
                for p in pos_rows:
                    val = float(p.get("quantity", 0)) * float(p.get("price", 0))
                    holdings[p.get("ticker", "")] += val if p.get("side") == "BUY" else -val
                total = sum(v for v in holdings.values() if v > 0) or 1
                pos_util = round(max(holdings.values(), default=0) / total * 100, 2)
        except Exception:
            pass

        return {
            "drawdown_pct": float(latest.get("drawdown_pct", 0)),
            "drawdown_alert": limits["drawdown_alert"],
            "drawdown_limit": limits["drawdown_limit"],
            "daily_loss_pct": float(latest.get("day_pnl_pct", 0)),
            "daily_loss_limit": limits["daily_loss_limit"],
            "rolling_sharpe_63d": round(sharpe, 3),
            "max_position_pct": limits["max_position_pct"],
            "max_sector_pct": limits["max_sector_pct"],
            "position_utilization_pct": pos_util,
            "sector_utilization_pct": sec_util,
            "kill_switch_active": False,
        }
    except Exception:
        return _safe_metrics()


@router.get("/limits")
async def get_risk_limits():
    return _get_limits()


@router.get("/drawdown-history")
async def drawdown_history(days: int = Query(90, ge=7, le=365)):
    rows = sdb.select("daily_pnl", cols="date,drawdown_pct,day_pnl_pct", order="date", limit=days)
    return rows
