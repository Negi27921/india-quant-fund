"""Trade history and active orders API."""
from fastapi import APIRouter, Query
from data.storage import db

router = APIRouter()


@router.get("/orders")
async def get_orders(status: str = Query("all"), limit: int = Query(50)):
    try:
        where = "" if status == "all" else f"WHERE status = '{status.upper()}'"
        df = db.query_df(f"SELECT * FROM orders {where} ORDER BY created_at DESC LIMIT {limit}")
        return df.to_dict("records") if not df.empty else []
    except Exception as e:
        return {"error": str(e)}


@router.get("/fills")
async def get_fills(days: int = Query(30)):
    try:
        df = db.query_df(f"""
            SELECT * FROM orders WHERE status = 'FILLED'
            AND created_at >= CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY filled_at DESC
        """)
        return df.to_dict("records") if not df.empty else []
    except Exception as e:
        return {"error": str(e)}


@router.get("/stats")
async def trade_stats(days: int = Query(30)):
    try:
        df = db.query_df(f"""
            SELECT
                COUNT(*) as total_orders,
                SUM(CASE WHEN status='FILLED' THEN 1 ELSE 0 END) as filled,
                SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) as rejected,
                SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END) as sells,
                AVG(avg_fill_price) as avg_fill_price
            FROM orders
            WHERE created_at >= CURRENT_DATE - INTERVAL '{days} days'
        """)
        return df.iloc[0].to_dict() if not df.empty else {}
    except Exception as e:
        return {"error": str(e)}
