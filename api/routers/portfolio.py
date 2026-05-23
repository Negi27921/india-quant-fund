"""Portfolio API — backed by Supabase (positions, P&L)."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Optional

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.middleware.security import require_internal_key
from data.storage import supabase_db as sdb

router = APIRouter()


# ── Mock fallback ──────────────────────────────────────────────────────────────

def _mock_pnl(days: int = 90) -> list[dict]:
    rng = random.Random(42)
    value = 1_000_000.0
    records, today = [], date.today()
    d = today - timedelta(days=days * 2)
    trading = []
    while len(trading) < days:
        if d.weekday() < 5:
            trading.append(d)
        d += timedelta(days=1)
    for dt in trading[:days]:
        pct = max(-3.0, min(3.0, rng.gauss(0.05, 1.2)))
        pnl = value * pct / 100
        value += pnl
        records.append({"date": dt.isoformat(), "pnl": round(pnl, 2),
                        "pnl_pct": round(pct, 4), "portfolio_value": round(value, 2)})
    return records


def _live_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch live prices via the unified market data layer (thread-safe, timeout-bounded)."""
    from core.market_data import get_prices_bulk
    return {t: p for t, p in get_prices_bulk(tickers, timeout_s=7.0).items() if p > 0}


def _validate_price(current: float, avg: float) -> float:
    """If yfinance returns a price that's clearly wrong (>80% off entry), fall back to entry."""
    if avg <= 0 or current <= 0:
        return avg
    ratio = current / avg
    if ratio < 0.20 or ratio > 15:  # >80% loss or 15x gain — clearly wrong
        return avg
    return current


def _enrich_positions(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    # Support both 'ticker' and 'symbol' column names, and 'shares' vs 'quantity'
    normalized = []
    for r in rows:
        ticker = r.get("ticker") or r.get("symbol") or ""
        qty = int(r.get("quantity") or r.get("shares") or 0)
        avg = float(r.get("avg_buy_price") or r.get("entry_price") or 0)
        normalized.append({**r, "ticker": ticker, "_qty": qty, "_avg": avg})

    yf_tickers = [r["ticker"] if "." in r["ticker"] else f"{r['ticker']}.NS" for r in normalized]
    prices = _live_prices(yf_tickers)

    total_cost = sum(r["_qty"] * r["_avg"] for r in normalized)
    result = []
    today = date.today()
    for r in normalized:
        avg = r["_avg"]
        qty = r["_qty"]
        ticker = r["ticker"]
        key = ticker if "." in ticker else f"{ticker}.NS"
        raw_price = prices.get(key, 0)
        current = _validate_price(raw_price, avg) if raw_price else avg
        cost = qty * avg
        unreal = qty * (current - avg)
        try:
            days_held = (today - date.fromisoformat(str(r.get("buy_date") or r.get("entry_date") or ""))).days
        except Exception:
            days_held = 0
        result.append({
            "id": r.get("id"), "ticker": ticker, "name": r.get("name", ticker),
            "sector": r.get("sector", ""), "quantity": qty,
            "avg_buy_price": round(avg, 2), "current_price": round(current, 2),
            "unrealized_pnl": round(unreal, 2),
            "pnl_pct": round((current - avg) / avg * 100, 2) if avg else 0.0,
            "weight": round(cost / total_cost * 100, 2) if total_cost else 0.0,
            "strategy": r.get("strategy", ""),
            "buy_date": str(r.get("buy_date") or r.get("entry_date") or ""),
            "days_held": days_held, "notes": r.get("notes", ""),
        })
    return sorted(result, key=lambda x: abs(x["unrealized_pnl"]), reverse=True)


# ── P&L endpoints ──────────────────────────────────────────────────────────────

@router.get("/summary")
async def portfolio_summary():
    INITIAL_CAPITAL = 1_000_000.0
    try:
        rows = sdb.select("daily_pnl", order="-date", limit=1)
        equity_rows = sdb.select("daily_pnl", cols="date,portfolio_value,day_pnl_pct,drawdown_pct",
                                  order="-date", limit=252)
        # Fetch paper trades for enriched stats
        paper_rows = []
        try:
            paper_rows = sdb.select("paper_trades", limit=500)
        except Exception:
            pass
        n_open = sum(1 for r in paper_rows if r.get("status") == "OPEN")
        n_closed = sum(1 for r in paper_rows if r.get("status") == "CLOSED")
        total_paper_pnl = sum(float(r.get("pnl") or 0) for r in paper_rows if r.get("status") == "CLOSED")

        if rows:
            r = rows[0]
            return {
                "portfolio_value": float(r.get("portfolio_value", 0)),
                "cash": float(r.get("cash", 0)),
                "invested": float(r.get("invested", 0)),
                "day_pnl": float(r.get("day_pnl", 0)),
                "day_pnl_pct": float(r.get("day_pnl_pct", 0)),
                "drawdown_pct": float(r.get("drawdown_pct", 0)),
                "n_positions": r.get("n_positions") or n_open or 0,
                "equity_curve": list(reversed(equity_rows)),
                "n_open_paper_trades": n_open,
                "n_closed_paper_trades": n_closed,
                "total_paper_pnl": round(total_paper_pnl, 2),
            }

        # Fallback: derive portfolio value from paper trades when daily_pnl is empty
        if paper_rows:
            portfolio_value = INITIAL_CAPITAL + total_paper_pnl
            return {
                "portfolio_value": round(portfolio_value, 2),
                "cash": round(INITIAL_CAPITAL * 0.2, 2),
                "invested": round(portfolio_value * 0.8, 2),
                "day_pnl": 0.0,
                "day_pnl_pct": 0.0,
                "drawdown_pct": 0.0,
                "n_positions": n_open,
                "equity_curve": [],
                "n_open_paper_trades": n_open,
                "n_closed_paper_trades": n_closed,
                "total_paper_pnl": round(total_paper_pnl, 2),
            }
    except Exception:
        pass
    mock = _mock_pnl(90)
    return {
        "portfolio_value": mock[-1]["portfolio_value"] if mock else 0,
        "cash": 200000, "invested": 800000,
        "day_pnl": mock[-1]["pnl"] if mock else 0,
        "day_pnl_pct": mock[-1]["pnl_pct"] if mock else 0,
        "drawdown_pct": -3.2, "n_positions": 6,
        "equity_curve": mock,
        "n_open_paper_trades": 0,
        "n_closed_paper_trades": 0,
        "total_paper_pnl": 0.0,
    }


@router.get("/equity-curve")
async def equity_curve(days: int = Query(252, ge=5, le=1260)):
    try:
        rows = sdb.select("daily_pnl",
                          cols="date,portfolio_value,day_pnl_pct,drawdown_pct,benchmark_ret",
                          order="-date", limit=days)
        if rows:
            return list(reversed(rows))
    except Exception:
        pass
    return _mock_pnl(min(days, 90))


@router.get("/pnl-calendar")
async def pnl_calendar(
    year: int = Query(datetime.now().year),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    try:
        rows = sdb.select("daily_pnl", cols="date,day_pnl,day_pnl_pct,portfolio_value",
                          order="date", limit=1000)
        if rows:
            filtered = [
                {"date": r["date"], "pnl": r["day_pnl"],
                 "pnl_pct": r["day_pnl_pct"], "portfolio_value": r["portfolio_value"]}
                for r in rows
                if str(r["date"]).startswith(str(year))
                and (month is None or int(str(r["date"])[5:7]) == month)
            ]
            if filtered:
                return filtered
    except Exception:
        pass
    mock = _mock_pnl(90)
    return [r for r in mock if r["date"].startswith(str(year))
            and (month is None or int(r["date"][5:7]) == month)] or mock[-30:]


@router.get("/pnl-stats")
async def pnl_stats():
    try:
        rows = sdb.select("daily_pnl", cols="date,day_pnl,day_pnl_pct,portfolio_value",
                          order="date", limit=1000)
        records = [{"date": r["date"], "pnl": float(r["day_pnl"]),
                    "pnl_pct": float(r["day_pnl_pct"]),
                    "portfolio_value": float(r["portfolio_value"])} for r in rows]
        if not records:
            raise ValueError("empty")
    except Exception:
        records = _mock_pnl(90)

    pnls = [r["pnl"] for r in records]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    streak = 0
    if pnls:
        sign = 1 if pnls[-1] >= 0 else -1
        for p in reversed(pnls):
            if (p >= 0 and sign == 1) or (p < 0 and sign == -1):
                streak += sign
            else:
                break

    monthly: dict[str, dict] = {}
    for r in records:
        k = str(r["date"])[:7]
        monthly.setdefault(k, {"pnl": 0.0, "pnl_pct": 0.0})
        monthly[k]["pnl"] += r["pnl"]
        monthly[k]["pnl_pct"] += r["pnl_pct"]

    start_val = records[0]["portfolio_value"] - records[0]["pnl"]
    end_val = records[-1]["portfolio_value"]
    total_pnl = end_val - start_val

    return {
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / start_val * 100, 4) if start_val else 0,
        "win_days": len(wins), "loss_days": len(losses),
        "best_day": round(max(pnls), 2) if pnls else 0,
        "worst_day": round(min(pnls), 2) if pnls else 0,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "streak": streak,
        "monthly": [{"month": k, "pnl": round(v["pnl"], 2),
                     "pnl_pct": round(v["pnl_pct"], 4)}
                    for k, v in sorted(monthly.items())],
    }


# ── Position endpoints ─────────────────────────────────────────────────────────

class PositionRequest(BaseModel):
    ticker: str
    quantity: int
    avg_buy_price: float
    buy_date: str
    name: Optional[str] = None
    sector: Optional[str] = None
    notes: Optional[str] = None


class ExitRequest(BaseModel):
    quantity: Optional[int] = None
    exit_price: Optional[float] = None


def _normalize_ticker(t: str) -> str:
    t = t.upper().strip()
    return t if "." in t else f"{t}.NS"


@router.get("/positions")
async def positions():
    """Unified positions: live first, fall back to paper_positions, then paper_trades (OPEN)."""
    try:
        live = sdb.select("live_positions", order="-created_at")
        if live:
            return _enrich_positions(live)
        paper = sdb.select("paper_positions", order="-created_at")
        if paper:
            return _enrich_positions(paper)
        # Derive from open paper_trades (shares column = quantity)
        trades = sdb.select("paper_trades", order="-entry_date", limit=200)
        open_trades = [t for t in trades if t.get("status", "").upper() == "OPEN"]
        if open_trades:
            rows = [{
                "ticker": t.get("ticker") or t.get("symbol", ""),
                "name": t.get("name", t.get("ticker", "")),
                "quantity": int(t.get("shares") or t.get("quantity") or 0),
                "avg_buy_price": float(t.get("entry_price") or 0),
                "buy_date": t.get("entry_date", ""),
                "sector": t.get("sector", ""),
                "strategy": t.get("strategy", ""),
                "notes": t.get("notes", ""),
            } for t in open_trades]
            return _enrich_positions(rows)
    except Exception:
        pass
    return []


@router.get("/paper-positions")
async def paper_positions():
    try:
        rows = sdb.select("paper_positions", order="-created_at")
        return _enrich_positions(rows)
    except Exception:
        return []


@router.post("/paper-positions")
async def add_paper_position(req: PositionRequest, _: None = Depends(require_internal_key)):
    ticker = _normalize_ticker(req.ticker)
    existing = sdb.select("paper_positions", filters={"ticker": ticker})
    entry = {
        "ticker": ticker, "name": req.name or ticker,
        "sector": req.sector or "", "quantity": req.quantity,
        "avg_buy_price": req.avg_buy_price, "buy_date": req.buy_date,
        "strategy": "paper_trading", "notes": req.notes or "",
    }
    if existing:
        sdb.update("paper_positions", entry, {"ticker": ticker})
    else:
        sdb.insert("paper_positions", entry)
    return {"status": "ok", "ticker": ticker}


@router.delete("/paper-positions/{ticker}")
async def delete_paper_position(ticker: str, _: None = Depends(require_internal_key)):
    t = _normalize_ticker(ticker)
    # Try paper_positions first, fall back to paper_trades
    rows = sdb.select("paper_positions", filters={"ticker": t})
    if rows:
        sdb.delete("paper_positions", {"ticker": t})
        return {"status": "deleted", "ticker": t}
    # Check paper_trades (ticker stored without .NS suffix usually)
    bare = t.replace(".NS", "").replace(".BO", "")
    trade_rows = sdb.select("paper_trades", filters={"ticker": bare})
    if trade_rows:
        for r in trade_rows:
            sdb.update("paper_trades", {"status": "CLOSED"}, {"id": r["id"]})
        return {"status": "deleted", "ticker": t, "source": "paper_trades"}
    raise HTTPException(404, f"{ticker} not found")


@router.put("/paper-positions/{ticker}/exit")
async def exit_paper_position(ticker: str, req: ExitRequest, _: None = Depends(require_internal_key)):
    t = _normalize_ticker(ticker)
    # Try paper_positions first, fall back to paper_trades
    rows = sdb.select("paper_positions", filters={"ticker": t})
    if rows:
        pos = rows[0]
        exit_qty = req.quantity or pos["quantity"]
        remaining = pos["quantity"] - exit_qty
        if remaining <= 0:
            sdb.delete("paper_positions", {"ticker": t})
        else:
            sdb.update("paper_positions", {"quantity": remaining}, {"ticker": t})
        return {"status": "exited", "ticker": t, "exited_qty": exit_qty, "remaining": max(0, remaining)}
    # Fall back: mark paper_trades as CLOSED
    bare = t.replace(".NS", "").replace(".BO", "")
    trade_rows = [r for r in sdb.select("paper_trades", filters={"ticker": bare})
                  if r.get("status", "").upper() == "OPEN"]
    if trade_rows:
        pos = trade_rows[0]
        qty = int(pos.get("shares") or pos.get("quantity") or 0)
        exit_qty = req.quantity or qty
        sdb.update("paper_trades", {
            "status": "CLOSED",
            "exit_price": req.exit_price or float(pos.get("entry_price") or 0),
            "exit_date": date.today().isoformat(),
        }, {"id": pos["id"]})
        return {"status": "exited", "ticker": t, "exited_qty": exit_qty, "remaining": 0, "source": "paper_trades"}
    raise HTTPException(404, f"{ticker} not found")


@router.get("/live-positions")
async def live_positions():
    try:
        rows = sdb.select("live_positions", order="-created_at")
        return _enrich_positions(rows)
    except Exception:
        return []


@router.post("/live-positions")
async def add_live_position(req: PositionRequest, _: None = Depends(require_internal_key)):
    ticker = _normalize_ticker(req.ticker)
    existing = sdb.select("live_positions", filters={"ticker": ticker})
    entry = {
        "ticker": ticker, "name": req.name or ticker,
        "sector": req.sector or "", "quantity": req.quantity,
        "avg_buy_price": req.avg_buy_price, "buy_date": req.buy_date,
        "strategy": "live", "notes": req.notes or "",
    }
    if existing:
        sdb.update("live_positions", entry, {"ticker": ticker})
    else:
        sdb.insert("live_positions", entry)
    return {"status": "ok", "ticker": ticker}


@router.delete("/live-positions/{ticker}")
async def delete_live_position(ticker: str, _: None = Depends(require_internal_key)):
    t = _normalize_ticker(ticker)
    rows = sdb.select("live_positions", filters={"ticker": t})
    if not rows:
        raise HTTPException(404, f"{ticker} not found")
    sdb.delete("live_positions", {"ticker": t})
    return {"status": "deleted", "ticker": t}


@router.put("/live-positions/{ticker}/exit")
async def exit_live_position(ticker: str, req: ExitRequest, _: None = Depends(require_internal_key)):
    t = _normalize_ticker(ticker)
    rows = sdb.select("live_positions", filters={"ticker": t})
    if not rows:
        raise HTTPException(404, f"{ticker} not found")
    pos = rows[0]
    exit_qty = req.quantity or pos["quantity"]
    remaining = pos["quantity"] - exit_qty
    if remaining <= 0:
        sdb.delete("live_positions", {"ticker": t})
    else:
        sdb.update("live_positions", {"quantity": remaining}, {"ticker": t})
    return {"status": "exited", "ticker": t, "exited_qty": exit_qty, "remaining": max(0, remaining)}


@router.get("/paper-trades")
async def paper_trades_list(status: str = "all", limit: int = 100):
    """All paper trades with P&L, sorted newest first."""
    try:
        rows = sdb.select("paper_trades", order="-entry_date", limit=limit)
        if status != "all":
            rows = [r for r in rows if r.get("status", "").upper() == status.upper()]
        return rows
    except Exception as e:
        return []


@router.get("/strategy-pnl")
async def strategy_pnl():
    """Aggregate P&L grouped by strategy from paper_trades."""
    try:
        rows = sdb.select("paper_trades", limit=1000)
        if not rows:
            return []
        stats = {}
        for r in rows:
            s = r.get("strategy", "unknown")
            pnl = float(r.get("pnl") or 0)
            pnl_pct = float(r.get("pnl_pct") or 0)
            status = r.get("status", "OPEN")
            if s not in stats:
                stats[s] = {"strategy": s, "total_trades": 0, "closed_trades": 0,
                            "wins": 0, "losses": 0, "total_pnl": 0.0, "avg_pnl_pct": 0.0,
                            "pnl_pcts": [], "open_trades": 0}
            stats[s]["total_trades"] += 1
            if status == "CLOSED":
                stats[s]["closed_trades"] += 1
                stats[s]["total_pnl"] += pnl
                stats[s]["pnl_pcts"].append(pnl_pct)
                if pnl > 0:
                    stats[s]["wins"] += 1
                else:
                    stats[s]["losses"] += 1
            elif status == "OPEN":
                stats[s]["open_trades"] += 1
        result = []
        for s, d in stats.items():
            pcts = d.pop("pnl_pcts")
            d["avg_pnl_pct"] = round(sum(pcts) / len(pcts), 2) if pcts else 0.0
            d["win_rate"] = round(d["wins"] / d["closed_trades"] * 100, 1) if d["closed_trades"] else 0.0
            d["total_pnl"] = round(d["total_pnl"], 2)
            result.append(d)
        return sorted(result, key=lambda x: -x["total_pnl"])
    except Exception:
        return []


@router.get("/sector-exposure")
async def sector_exposure():
    rows = sdb.select("live_positions", cols="ticker,sector,quantity,avg_buy_price")
    if not rows:
        rows = sdb.select("paper_positions", cols="ticker,sector,quantity,avg_buy_price")
    if not rows:
        return []
    total = sum(r["quantity"] * float(r["avg_buy_price"]) for r in rows)
    sectors: dict[str, float] = {}
    for r in rows:
        s = r.get("sector") or "Other"
        w = r["quantity"] * float(r["avg_buy_price"]) / total * 100
        sectors[s] = sectors.get(s, 0) + w
    return [{"sector": k, "weight": round(v, 2)} for k, v in sorted(sectors.items(), key=lambda x: -x[1])]
