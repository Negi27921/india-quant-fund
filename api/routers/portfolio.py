"""Portfolio API endpoints."""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from data.storage import db

router = APIRouter()

# ── Paper-position store (JSON file, lightweight) ──────────────────────────────
_PAPER_FILE = Path(__file__).parent.parent.parent / "data" / "paper_positions.json"
_PAPER_FILE.parent.mkdir(parents=True, exist_ok=True)

def _load_paper() -> list[dict]:
    if _PAPER_FILE.exists():
        try:
            return json.loads(_PAPER_FILE.read_text())
        except Exception:
            pass
    return []

def _save_paper(positions: list[dict]) -> None:
    _PAPER_FILE.write_text(json.dumps(positions, indent=2, default=str))


# ── Mock-data helpers ─────────────────────────────────────────────────────────

def _mock_pnl_calendar(days: int = 90) -> list[dict]:
    """Generate realistic daily P&L mock data for the last N trading days."""
    rng = random.Random(42)
    base_value = 1_000_000.0  # ₹10 lakh starting capital
    records = []
    today = date.today()
    trading_days = []
    d = today - timedelta(days=days * 2)
    while len(trading_days) < days:
        if d.weekday() < 5:  # Mon–Fri only
            trading_days.append(d)
        d += timedelta(days=1)
    trading_days = trading_days[:days]

    portfolio_value = base_value
    for dt in trading_days:
        # Slight upward drift with ±3% daily range
        pnl_pct = rng.gauss(0.05, 1.2)  # mean +0.05%, std 1.2%
        pnl_pct = max(-3.0, min(3.0, pnl_pct))
        pnl = portfolio_value * pnl_pct / 100
        portfolio_value += pnl
        records.append({
            "date": dt.isoformat(),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 4),
            "portfolio_value": round(portfolio_value, 2),
        })
    return records


def _mock_paper_positions() -> list[dict]:
    """Return mock paper-trading positions for 6 key NSE stocks."""
    positions_data = [
        {"ticker": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Energy",  "qty": 10,  "avg": 2850.0,  "current": 2910.0},
        {"ticker": "TCS.NS",      "name": "TCS",                 "sector": "IT",      "qty": 5,   "avg": 3700.0,  "current": 3640.0},
        {"ticker": "HDFCBANK.NS", "name": "HDFC Bank",           "sector": "Bank",    "qty": 20,  "avg": 1620.0,  "current": 1680.0},
        {"ticker": "INFY.NS",     "name": "Infosys",             "sector": "IT",      "qty": 15,  "avg": 1480.0,  "current": 1510.0},
        {"ticker": "MARUTI.NS",   "name": "Maruti Suzuki",       "sector": "Auto",    "qty": 3,   "avg": 12200.0, "current": 12050.0},
        {"ticker": "SUNPHARMA.NS","name": "Sun Pharma",          "sector": "Pharma",  "qty": 12,  "avg": 1550.0,  "current": 1610.0},
    ]
    total_value = sum(p["qty"] * p["avg"] for p in positions_data)
    result = []
    for p in positions_data:
        cost = p["qty"] * p["avg"]
        unreal = p["qty"] * (p["current"] - p["avg"])
        result.append({
            "ticker": p["ticker"],
            "name": p["name"],
            "sector": p["sector"],
            "quantity": p["qty"],
            "avg_buy_price": p["avg"],
            "current_price": p["current"],
            "unrealized_pnl": round(unreal, 2),
            "pnl_pct": round((p["current"] - p["avg"]) / p["avg"] * 100, 2),
            "weight": round(cost / total_value * 100, 2),
            "strategy": "paper_trading",
        })
    return sorted(result, key=lambda x: abs(x["unrealized_pnl"]), reverse=True)


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


@router.get("/pnl-calendar")
async def pnl_calendar(
    year: int = Query(datetime.now().year, description="Year, e.g. 2026"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month 1-12 (optional)"),
):
    """Daily P&L for the given year/month from daily_pnl table (or mock data)."""
    try:
        if month:
            sql = f"""
                SELECT date, day_pnl AS pnl, day_pnl_pct AS pnl_pct, portfolio_value
                FROM daily_pnl
                WHERE YEAR(CAST(date AS DATE)) = {year}
                  AND MONTH(CAST(date AS DATE)) = {month}
                ORDER BY date
            """
        else:
            sql = f"""
                SELECT date, day_pnl AS pnl, day_pnl_pct AS pnl_pct, portfolio_value
                FROM daily_pnl
                WHERE YEAR(CAST(date AS DATE)) = {year}
                ORDER BY date
            """
        df = db.query_df(sql)
        if not df.empty:
            return df.to_dict("records")
    except Exception:
        pass

    # Fall back to mock data filtered to requested year/month
    all_mock = _mock_pnl_calendar(90)
    filtered = [
        r for r in all_mock
        if r["date"].startswith(str(year))
        and (month is None or int(r["date"][5:7]) == month)
    ]
    return filtered if filtered else all_mock[-30:]


@router.get("/pnl-stats")
async def pnl_stats():
    """Aggregate P&L statistics from daily_pnl table (or mock data)."""
    try:
        df = db.query_df("""
            SELECT date, day_pnl AS pnl, day_pnl_pct AS pnl_pct, portfolio_value
            FROM daily_pnl ORDER BY date
        """)
        if df.empty:
            raise ValueError("empty")
        records = df.to_dict("records")
    except Exception:
        records = _mock_pnl_calendar(90)

    if not records:
        return {}

    pnls = [r["pnl"] for r in records]
    pnl_pcts = [r["pnl_pct"] for r in records]
    win_days = sum(1 for p in pnls if p > 0)
    loss_days = sum(1 for p in pnls if p < 0)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    # Current streak
    streak = 0
    if pnls:
        sign = 1 if pnls[-1] >= 0 else -1
        for p in reversed(pnls):
            if (p >= 0 and sign == 1) or (p < 0 and sign == -1):
                streak += sign
            else:
                break

    # Monthly aggregates
    monthly: dict[str, dict] = {}
    for r in records:
        m_key = r["date"][:7]  # "YYYY-MM"
        if m_key not in monthly:
            monthly[m_key] = {"pnl": 0.0, "pnl_pct": 0.0, "count": 0}
        monthly[m_key]["pnl"] += r["pnl"]
        monthly[m_key]["pnl_pct"] += r["pnl_pct"]
        monthly[m_key]["count"] += 1

    monthly_list = [
        {
            "month": k,
            "pnl": round(v["pnl"], 2),
            "pnl_pct": round(v["pnl_pct"], 4),
        }
        for k, v in sorted(monthly.items())
    ]

    start_val = records[0]["portfolio_value"] - records[0]["pnl"]
    end_val = records[-1]["portfolio_value"]
    total_pnl = end_val - start_val
    total_pnl_pct = (total_pnl / start_val * 100) if start_val else 0.0

    return {
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 4),
        "win_days": win_days,
        "loss_days": loss_days,
        "best_day": round(max(pnls), 2),
        "worst_day": round(min(pnls), 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "streak": streak,
        "monthly": monthly_list,
    }


class AddPositionRequest(BaseModel):
    ticker: str
    quantity: int
    avg_buy_price: float
    buy_date: str  # ISO date string e.g. "2025-01-15"
    name: Optional[str] = None
    sector: Optional[str] = None
    notes: Optional[str] = None


@router.get("/paper-positions")
async def paper_positions():
    """Current paper trading positions with real-time P&L (live prices via yfinance)."""
    import yfinance as yf

    stored = _load_paper()
    if not stored:
        stored = _mock_paper_positions()

    # Fetch live prices for all tickers
    tickers = [p["ticker"] if "." in p["ticker"] else f"{p['ticker']}.NS" for p in stored]
    prices: dict[str, float] = {}
    try:
        for t in tickers:
            try:
                info = yf.Ticker(t).fast_info
                prices[t] = float(info.last_price or 0)
            except Exception:
                pass
    except Exception:
        pass

    total_cost = sum(p["quantity"] * p["avg_buy_price"] for p in stored)
    result = []
    today = date.today()
    for p in stored:
        avg = float(p["avg_buy_price"])
        qty = int(p["quantity"])
        ticker_key = p["ticker"] if "." in p["ticker"] else f"{p['ticker']}.NS"
        current = prices.get(ticker_key, avg)
        if current == 0:
            current = avg
        cost = qty * avg
        unreal = qty * (current - avg)
        buy_date_str = p.get("buy_date", today.isoformat())
        try:
            days_held = (today - date.fromisoformat(buy_date_str)).days
        except Exception:
            days_held = 0
        result.append({
            "ticker": p["ticker"],
            "name": p.get("name", p["ticker"]),
            "sector": p.get("sector", ""),
            "quantity": qty,
            "avg_buy_price": round(avg, 2),
            "current_price": round(current, 2),
            "unrealized_pnl": round(unreal, 2),
            "pnl_pct": round((current - avg) / avg * 100, 2) if avg else 0.0,
            "weight": round(cost / total_cost * 100, 2) if total_cost else 0.0,
            "strategy": p.get("strategy", "paper_trading"),
            "buy_date": buy_date_str,
            "days_held": days_held,
            "notes": p.get("notes", ""),
        })
    return sorted(result, key=lambda x: abs(x["unrealized_pnl"]), reverse=True)


@router.post("/paper-positions")
async def add_paper_position(req: AddPositionRequest):
    """Add or update a paper trading position."""
    stored = _load_paper()
    ticker = req.ticker.upper()
    # Update if ticker already exists
    existing = next((i for i, p in enumerate(stored) if p["ticker"].upper().replace(".NS", "") == ticker.replace(".NS", "")), None)
    entry = {
        "ticker": ticker if "." in ticker else f"{ticker}.NS",
        "quantity": req.quantity,
        "avg_buy_price": req.avg_buy_price,
        "buy_date": req.buy_date,
        "name": req.name or ticker,
        "sector": req.sector or "",
        "strategy": "paper_trading",
        "notes": req.notes or "",
    }
    if existing is not None:
        stored[existing] = entry
    else:
        stored.append(entry)
    _save_paper(stored)
    return {"status": "ok", "ticker": entry["ticker"]}


@router.delete("/paper-positions/{ticker}")
async def delete_paper_position(ticker: str):
    """Remove a paper trading position."""
    stored = _load_paper()
    clean = ticker.upper().replace(".NS", "").replace(".BO", "")
    new_stored = [p for p in stored if p["ticker"].upper().replace(".NS", "").replace(".BO", "") != clean]
    if len(new_stored) == len(stored):
        raise HTTPException(status_code=404, detail=f"{ticker} not found in paper positions")
    _save_paper(new_stored)
    return {"status": "deleted", "ticker": ticker}


class ExitPositionRequest(BaseModel):
    quantity: Optional[int] = None   # None = full exit
    exit_price: Optional[float] = None
    mode: str = "paper"  # "paper" or "live"


@router.put("/paper-positions/{ticker}/exit")
async def exit_paper_position(ticker: str, req: ExitPositionRequest):
    """Partially or fully exit a paper position."""
    stored = _load_paper()
    clean = ticker.upper().replace(".NS", "").replace(".BO", "")
    idx = next((i for i, p in enumerate(stored) if p["ticker"].upper().replace(".NS", "").replace(".BO", "") == clean), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{ticker} not found")
    pos = stored[idx]
    exit_qty = req.quantity if req.quantity else pos["quantity"]
    remaining = pos["quantity"] - exit_qty
    if remaining <= 0:
        stored.pop(idx)
    else:
        stored[idx]["quantity"] = remaining
    _save_paper(stored)
    return {"status": "exited", "ticker": ticker, "exited_qty": exit_qty, "remaining": max(0, remaining)}


# ── Live positions (for manual live tracking) ─────────────────────────────────
_LIVE_FILE = Path(__file__).parent.parent.parent / "data" / "live_positions.json"
_LIVE_FILE.parent.mkdir(parents=True, exist_ok=True)

def _load_live() -> list[dict]:
    if _LIVE_FILE.exists():
        try:
            return json.loads(_LIVE_FILE.read_text())
        except Exception:
            pass
    return []

def _save_live(positions: list[dict]) -> None:
    _LIVE_FILE.write_text(json.dumps(positions, indent=2, default=str))


@router.get("/live-positions")
async def live_positions():
    """Manually tracked live positions with real-time P&L."""
    import yfinance as yf
    stored = _load_live()
    if not stored:
        return []
    tickers = [p["ticker"] if "." in p["ticker"] else f"{p['ticker']}.NS" for p in stored]
    prices: dict[str, float] = {}
    for t in tickers:
        try:
            prices[t] = float(yf.Ticker(t).fast_info.last_price or 0)
        except Exception:
            pass
    total_cost = sum(p["quantity"] * p["avg_buy_price"] for p in stored)
    result = []
    today = date.today()
    for p in stored:
        avg = float(p["avg_buy_price"])
        qty = int(p["quantity"])
        ticker_key = p["ticker"] if "." in p["ticker"] else f"{p['ticker']}.NS"
        current = prices.get(ticker_key, avg) or avg
        cost = qty * avg
        unreal = qty * (current - avg)
        buy_date_str = p.get("buy_date", today.isoformat())
        try:
            days_held = (today - date.fromisoformat(buy_date_str)).days
        except Exception:
            days_held = 0
        result.append({
            "ticker": p["ticker"], "name": p.get("name", p["ticker"]),
            "sector": p.get("sector", ""), "quantity": qty,
            "avg_buy_price": round(avg, 2), "current_price": round(current, 2),
            "unrealized_pnl": round(unreal, 2),
            "pnl_pct": round((current - avg) / avg * 100, 2) if avg else 0.0,
            "weight": round(cost / total_cost * 100, 2) if total_cost else 0.0,
            "strategy": p.get("strategy", "live"), "buy_date": buy_date_str,
            "days_held": days_held, "notes": p.get("notes", ""),
        })
    return sorted(result, key=lambda x: abs(x["unrealized_pnl"]), reverse=True)


@router.post("/live-positions")
async def add_live_position(req: AddPositionRequest):
    stored = _load_live()
    ticker = req.ticker.upper()
    existing = next((i for i, p in enumerate(stored) if p["ticker"].upper().replace(".NS", "") == ticker.replace(".NS", "")), None)
    entry = {
        "ticker": ticker if "." in ticker else f"{ticker}.NS",
        "quantity": req.quantity, "avg_buy_price": req.avg_buy_price,
        "buy_date": req.buy_date, "name": req.name or ticker,
        "sector": req.sector or "", "strategy": "live", "notes": req.notes or "",
    }
    if existing is not None:
        stored[existing] = entry
    else:
        stored.append(entry)
    _save_live(stored)
    return {"status": "ok", "ticker": entry["ticker"]}


@router.put("/live-positions/{ticker}/exit")
async def exit_live_position(ticker: str, req: ExitPositionRequest):
    stored = _load_live()
    clean = ticker.upper().replace(".NS", "").replace(".BO", "")
    idx = next((i for i, p in enumerate(stored) if p["ticker"].upper().replace(".NS", "").replace(".BO", "") == clean), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"{ticker} not found in live positions")
    pos = stored[idx]
    exit_qty = req.quantity if req.quantity else pos["quantity"]
    remaining = pos["quantity"] - exit_qty
    if remaining <= 0:
        stored.pop(idx)
    else:
        stored[idx]["quantity"] = remaining
    _save_live(stored)
    return {"status": "exited", "ticker": ticker, "exited_qty": exit_qty, "remaining": max(0, remaining)}


@router.delete("/live-positions/{ticker}")
async def delete_live_position(ticker: str):
    stored = _load_live()
    clean = ticker.upper().replace(".NS", "").replace(".BO", "")
    new_stored = [p for p in stored if p["ticker"].upper().replace(".NS", "").replace(".BO", "") != clean]
    if len(new_stored) == len(stored):
        raise HTTPException(status_code=404, detail=f"{ticker} not found")
    _save_live(new_stored)
    return {"status": "deleted", "ticker": ticker}
