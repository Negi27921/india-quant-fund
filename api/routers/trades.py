"""Trade history API — backed by Supabase."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from data.storage import supabase_db as sdb

router = APIRouter()


class TradeRequest(BaseModel):
    trade_date: str
    ticker: str
    name: Optional[str] = None
    side: str  # BUY | SELL
    quantity: int
    price: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    strategy: Optional[str] = None
    notes: Optional[str] = None


@router.get("/recent")
async def recent_trades(days: int = Query(30, ge=1, le=90)):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = sdb.select("trades", order="-trade_date", limit=200)
    return [r for r in rows if str(r.get("trade_date", "")) >= cutoff]


@router.get("/all")
async def all_trades(limit: int = Query(100, ge=1, le=500)):
    return sdb.select("trades", order="-trade_date", limit=limit)


@router.post("/")
async def add_trade(req: TradeRequest):
    entry = {
        "trade_date": req.trade_date,
        "ticker": req.ticker.upper(),
        "name": req.name or req.ticker.upper(),
        "side": req.side.upper(),
        "quantity": req.quantity,
        "price": req.price,
        "total_value": round(req.quantity * req.price, 2),
        "pnl": req.pnl,
        "pnl_pct": req.pnl_pct,
        "strategy": req.strategy or "manual",
        "notes": req.notes or "",
    }
    result = sdb.insert("trades", entry)
    return {"status": "ok", "id": result[0].get("id") if result else None}


@router.get("/stats")
async def trade_stats(days: int = Query(30, ge=1, le=90)):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = sdb.select("trades", order="-trade_date", limit=500)
    filtered = [r for r in rows if str(r.get("trade_date", "")) >= cutoff]
    if not filtered:
        return {"total": 0, "buys": 0, "sells": 0, "total_pnl": 0, "win_trades": 0, "loss_trades": 0}

    buys = [r for r in filtered if r["side"] == "BUY"]
    sells = [r for r in filtered if r["side"] == "SELL"]
    pnls = [float(r["pnl"]) for r in sells if r.get("pnl") is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    return {
        "total": len(filtered),
        "buys": len(buys),
        "sells": len(sells),
        "total_pnl": round(sum(pnls), 2),
        "win_trades": len(wins),
        "loss_trades": len(losses),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
    }


@router.get("/mtd")
async def mtd_trades():
    today = date.today()
    cutoff = today.replace(day=1).isoformat()
    rows = sdb.select("trades", order="-trade_date", limit=500)
    return [r for r in rows if str(r.get("trade_date", "")) >= cutoff]


@router.get("/ytd")
async def ytd_trades():
    cutoff = date.today().replace(month=1, day=1).isoformat()
    rows = sdb.select("trades", order="-trade_date", limit=1000)
    return [r for r in rows if str(r.get("trade_date", "")) >= cutoff]
