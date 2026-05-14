"""Strategy performance and signal log — Supabase-backed for cloud."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Query

from data.storage import supabase_db as sdb

router = APIRouter()


@router.get("/performance")
async def strategy_performance():
    """Return latest strategy performance from paper_trades."""
    try:
        from collections import defaultdict
        rows = sdb.select("paper_trades", cols="strategy,pnl,pnl_pct,entry_date,status", limit=500)
        if not rows:
            return []

        stats: dict[str, dict] = defaultdict(lambda: {
            "total_pnl": 0.0, "returns": [], "trades": 0, "wins": 0, "run_date": ""
        })
        for r in rows:
            s = r.get("strategy", "unknown")
            pnl_pct = float(r.get("pnl_pct") or 0)
            status = r.get("status", "open")
            if status != "open":
                stats[s]["total_pnl"] += float(r.get("pnl") or 0)
                stats[s]["returns"].append(pnl_pct)
                stats[s]["trades"] += 1
                if pnl_pct >= 0:
                    stats[s]["wins"] += 1
            if r.get("entry_date", "") > stats[s]["run_date"]:
                stats[s]["run_date"] = r.get("entry_date", "")

        import numpy as np
        result = []
        for strategy, st in stats.items():
            rets = st["returns"]
            arr = [r / 100 for r in rets]
            sharpe = float(np.mean(arr) / (np.std(arr) + 1e-9) * np.sqrt(252)) if len(arr) > 2 else 0.0
            total_ret = sum(rets)
            max_dd = min(rets) if rets else 0.0
            win_rate = st["wins"] / st["trades"] * 100 if st["trades"] > 0 else 0.0
            result.append({
                "strategy": strategy,
                "sharpe_ratio": round(sharpe, 3),
                "total_return": round(total_ret, 2),
                "max_drawdown": round(max_dd, 2),
                "win_rate": round(win_rate, 1),
                "num_trades": st["trades"],
                "run_date": st["run_date"],
            })
        result.sort(key=lambda x: -x["sharpe_ratio"])
        return result
    except Exception:
        return []


@router.get("/signals")
async def recent_signals(days: int = Query(5, ge=1, le=30)):
    """Return signals from screener_cache; falls back to paper_trades entries when cache is empty."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = sdb.select(
            "screener_cache",
            cols="strategy,scanned_at,results",
            order="-scanned_at",
            limit=20,
        )
        signals = []
        for row in rows:
            scanned_at = row.get("scanned_at", "")
            if scanned_at and scanned_at < cutoff:
                continue
            strategy = row.get("strategy", "")
            raw = row.get("results") or []
            results = json.loads(raw) if isinstance(raw, str) else raw
            date_str = scanned_at[:10] if scanned_at else ""
            for r in results[:25]:
                conf = int(r.get("confidence", 0))
                approved = conf >= 95
                signals.append({
                    "date": date_str,
                    "ticker": r.get("ticker", ""),
                    "strategy": strategy,
                    "signal": round(conf / 100, 2),
                    "approved": approved,
                    "rejection_reason": None if approved else f"confidence {conf}% < threshold",
                })

        # Fallback: derive signals from paper_trades when screener_cache is empty
        if not signals:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
            trades = sdb.select(
                "paper_trades",
                cols="ticker,strategy,entry_date,confidence,status",
                order="-entry_date",
                limit=100,
            )
            for t in trades:
                entry_date = t.get("entry_date", "")
                if entry_date and entry_date < cutoff_date:
                    continue
                conf = int(t.get("confidence") or 80)
                approved = conf >= 80
                status = t.get("status", "open").lower()
                signals.append({
                    "date": entry_date,
                    "ticker": t.get("ticker", ""),
                    "strategy": t.get("strategy", ""),
                    "signal": round(conf / 100, 2),
                    "approved": approved,
                    "rejection_reason": None if approved else f"confidence {conf}% < threshold",
                    "type": "BUY" if status == "open" else "CLOSED",
                })

        signals.sort(key=lambda x: (x["date"], -x["signal"]), reverse=True)
        return signals[:150]
    except Exception:
        return []


@router.get("/allocation")
async def strategy_allocation():
    """Strategy weights — from Supabase app_config or defaults."""
    defaults = {
        "vcp": 15.0, "breakout": 15.0, "golden_cross": 15.0,
        "multibagger": 20.0, "ipo_base": 10.0,
        "rocket_base": 10.0, "rsi_reversal": 15.0,
    }
    try:
        rows = sdb.select("app_config", cols="value", filters={"key": "strategy_weights"}, limit=1)
        if rows:
            raw = rows[0].get("value") or {}
            weights = json.loads(raw) if isinstance(raw, str) else raw
            return [{"strategy": k, "weight": round(float(v), 1)} for k, v in weights.items()]
    except Exception:
        pass
    return [{"strategy": k, "weight": v} for k, v in defaults.items()]
