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


def _paper_trade_to_order(r: dict) -> dict:
    """Map a paper_trades row to the frontend Order interface."""
    raw_status = r.get("status", "OPEN").upper()
    status = "FILLED" if raw_status == "CLOSED" else ("PENDING" if raw_status == "OPEN" else raw_status)
    return {
        "id": str(r.get("id", "")),
        "ticker": r.get("ticker", r.get("symbol", "")),
        "side": "BUY",
        "quantity": int(r.get("shares") or r.get("quantity") or r.get("qty") or 0),
        "order_type": "MARKET",
        "status": status,
        "limit_price": float(r.get("entry_price") or 0),
        "avg_fill_price": float(r.get("exit_price") or r.get("entry_price") or 0),
        "strategy": r.get("strategy", ""),
        "created_at": str(r.get("created_at", r.get("entry_date", ""))),
        "filled_at": str(r.get("exit_date", "")) if r.get("exit_date") else None,
        "rejection_reason": None,
        "pnl": r.get("pnl"),
        "pnl_pct": r.get("pnl_pct"),
        "notes": r.get("notes", ""),
    }


@router.get("/orders")
async def orders(status: str = Query("all"), limit: int = Query(100, ge=1, le=500)):
    """Return paper_trades as order list — primary feed for Terminal / Trades page."""
    try:
        rows = sdb.select("paper_trades", order="-entry_date", limit=limit)
        result = [_paper_trade_to_order(r) for r in rows]
        if status.lower() != "all":
            result = [o for o in result if o["status"].lower() == status.lower()]
        return result
    except Exception:
        return []


@router.get("/fills")
async def fills(days: int = Query(30, ge=1, le=90)):
    """Closed paper trades as execution fills."""
    try:
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = sdb.select("paper_trades", order="-entry_date", limit=500)
        closed = [r for r in rows if r.get("status", "").upper() == "CLOSED"
                  and str(r.get("entry_date", "")) >= cutoff]
        return [_paper_trade_to_order(r) for r in closed]
    except Exception:
        return []


@router.get("/recent")
async def recent_trades(days: int = Query(30, ge=1, le=90)):
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = sdb.select("trades", order="-trade_date", limit=200)
        return [r for r in rows if str(r.get("trade_date", "")) >= cutoff]
    except Exception:
        return []


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
    """Return TradeStats shape matching frontend types.ts interface."""
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = sdb.select("paper_trades", order="-entry_date", limit=500)
        filtered = [r for r in rows if str(r.get("entry_date", "")) >= cutoff]
        closed = [r for r in filtered if r.get("status", "").upper() == "CLOSED"]
        prices = [float(r.get("entry_price") or 0) for r in filtered if r.get("entry_price")]
        return {
            "total_orders": len(filtered),
            "filled": len(closed),
            "rejected": 0,
            "buys": len(filtered),
            "sells": len(closed),
            "avg_fill_price": round(sum(prices) / len(prices), 2) if prices else 0,
            "total_pnl": round(sum(float(r.get("pnl") or 0) for r in closed), 2),
            "win_trades": len([r for r in closed if float(r.get("pnl") or 0) > 0]),
            "loss_trades": len([r for r in closed if float(r.get("pnl") or 0) < 0]),
        }
    except Exception:
        return {"total_orders": 0, "filled": 0, "rejected": 0, "buys": 0, "sells": 0, "avg_fill_price": 0}


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
