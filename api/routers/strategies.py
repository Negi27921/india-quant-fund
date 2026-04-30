"""Strategy performance API."""
from fastapi import APIRouter, Query
from data.storage import db

router = APIRouter()


@router.get("/performance")
async def strategy_performance():
    try:
        df = db.query_df("""
            SELECT strategy, sharpe_ratio, total_return, max_drawdown, win_rate,
                   num_trades, run_date
            FROM backtest_results
            WHERE run_date = (SELECT MAX(run_date) FROM backtest_results)
            ORDER BY sharpe_ratio DESC
        """)
        return df.to_dict("records") if not df.empty else []
    except Exception as e:
        return {"error": str(e)}


@router.get("/signals")
async def recent_signals(days: int = Query(5)):
    try:
        df = db.query_df(f"""
            SELECT date, ticker, strategy, signal, approved, rejection_reason
            FROM signals
            WHERE date >= CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY date DESC, signal DESC
        """)
        return df.to_dict("records") if not df.empty else []
    except Exception as e:
        return {"error": str(e)}


@router.get("/allocation")
async def strategy_allocation():
    from strategies.portfolio.allocator import StrategyAllocator
    allocator = StrategyAllocator()
    weights = allocator.get_weights()
    return [{"strategy": k, "weight": round(v * 100, 1)} for k, v in weights.items()]
