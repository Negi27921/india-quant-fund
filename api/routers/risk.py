"""Risk metrics API."""
from fastapi import APIRouter
from data.storage import db
from risk.limits import get_limits
from risk.kill_switch import KillSwitch

router = APIRouter()


@router.get("/metrics")
async def risk_metrics():
    try:
        limits = get_limits()
        pnl = db.query_df("SELECT * FROM daily_pnl ORDER BY date DESC LIMIT 1")
        recent = db.query_df("SELECT day_pnl_pct FROM daily_pnl ORDER BY date DESC LIMIT 63")

        import numpy as np
        returns = recent["day_pnl_pct"].values / 100 if not recent.empty else []
        sharpe = float(np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252)) if len(returns) > 5 else 0

        return {
            "drawdown_pct": float(pnl["drawdown_pct"].iloc[0]) if not pnl.empty else 0,
            "drawdown_alert": limits.drawdown.drawdown_alert_pct,
            "drawdown_limit": limits.drawdown.drawdown_kill_switch_pct,
            "daily_loss_pct": float(pnl["day_pnl_pct"].iloc[0]) if not pnl.empty else 0,
            "daily_loss_limit": limits.drawdown.daily_loss_limit_pct,
            "rolling_sharpe_63d": round(sharpe, 3),
            "max_position_pct": limits.position.max_single_stock_pct,
            "max_sector_pct": limits.sector.max_sector_exposure_pct,
            "kill_switch_active": KillSwitch(limits).is_triggered(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/limits")
async def get_risk_limits():
    limits = get_limits()
    return {
        "position": limits.position.__dict__,
        "sector": limits.sector.__dict__,
        "drawdown": limits.drawdown.__dict__,
        "liquidity": limits.liquidity.__dict__,
    }


@router.get("/drawdown-history")
async def drawdown_history(days: int = 90):
    try:
        df = db.query_df(f"""
            SELECT date, drawdown_pct, day_pnl_pct
            FROM daily_pnl ORDER BY date DESC LIMIT {days}
        """)
        return df.sort_values("date").to_dict("records")
    except Exception as e:
        return {"error": str(e)}
