"""Portfolio API endpoints."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from data.storage import db

router = APIRouter()


class PositionOut(BaseModel):
    ticker: str
    quantity: int
    avg_buy_price: float
    current_price: Optional[float]
    unrealized_pnl: Optional[float]
    pnl_pct: Optional[float]
    weight: Optional[float]
    strategy: Optional[str]
    sector: Optional[str]


@router.get("/summary")
async def portfolio_summary():
    """Current portfolio summary."""
    try:
        pnl = db.query_df("SELECT * FROM daily_pnl ORDER BY date DESC LIMIT 1")
        positions = db.query_df("SELECT * FROM positions")
        equity = db.query_df("""
            SELECT date, portfolio_value, day_pnl_pct, drawdown_pct
            FROM daily_pnl ORDER BY date DESC LIMIT 252
        """)

        total = float(pnl["portfolio_value"].iloc[0]) if not pnl.empty else 0
        n_pos = len(positions)

        return {
            "portfolio_value": total,
            "cash": float(pnl["cash"].iloc[0]) if not pnl.empty else 0,
            "invested": float(pnl["invested"].iloc[0]) if not pnl.empty else 0,
            "day_pnl": float(pnl["day_pnl"].iloc[0]) if not pnl.empty else 0,
            "day_pnl_pct": float(pnl["day_pnl_pct"].iloc[0]) if not pnl.empty else 0,
            "drawdown_pct": float(pnl["drawdown_pct"].iloc[0]) if not pnl.empty else 0,
            "n_positions": n_pos,
            "equity_curve": equity.to_dict("records") if not equity.empty else [],
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/positions")
async def get_positions():
    """All current open positions."""
    try:
        from data.pipeline.transformers.universe import get_sector
        positions = db.query_df("SELECT * FROM positions")
        if positions.empty:
            return []

        total_value = positions["quantity"].values * positions["avg_buy_price"].values
        portfolio_total = total_value.sum()

        result = []
        for _, row in positions.iterrows():
            pos_value = row["quantity"] * row["avg_buy_price"]
            current = row.get("current_price") or row["avg_buy_price"]
            unreal = row["quantity"] * (current - row["avg_buy_price"])
            result.append({
                "ticker": row["ticker"],
                "quantity": int(row["quantity"]),
                "avg_buy_price": round(float(row["avg_buy_price"]), 2),
                "current_price": round(float(current), 2),
                "unrealized_pnl": round(float(unreal), 2),
                "pnl_pct": round((current - row["avg_buy_price"]) / row["avg_buy_price"] * 100, 2),
                "weight": round(pos_value / portfolio_total * 100, 2) if portfolio_total else 0,
                "sector": get_sector(row["ticker"]),
                "strategy": row.get("strategy", ""),
            })
        return sorted(result, key=lambda x: abs(x["unrealized_pnl"]), reverse=True)
    except Exception as e:
        return {"error": str(e)}


@router.get("/equity-curve")
async def equity_curve(days: int = Query(252, ge=5, le=1260)):
    """Historical equity curve."""
    try:
        df = db.query_df(f"""
            SELECT date, portfolio_value, day_pnl_pct, drawdown_pct, benchmark_ret
            FROM daily_pnl
            ORDER BY date DESC
            LIMIT {days}
        """)
        return df.sort_values("date").to_dict("records")
    except Exception as e:
        return {"error": str(e)}


@router.get("/sector-exposure")
async def sector_exposure():
    """Current sector allocation."""
    try:
        from data.pipeline.transformers.universe import get_sector
        positions = db.query_df("SELECT ticker, quantity, avg_buy_price FROM positions")
        if positions.empty:
            return []

        total = (positions["quantity"] * positions["avg_buy_price"]).sum()
        sectors: dict[str, float] = {}
        for _, row in positions.iterrows():
            sector = get_sector(row["ticker"])
            weight = row["quantity"] * row["avg_buy_price"] / total * 100
            sectors[sector] = sectors.get(sector, 0) + weight

        return [{"sector": k, "weight": round(v, 2)} for k, v in sorted(sectors.items(), key=lambda x: -x[1])]
    except Exception as e:
        return {"error": str(e)}
