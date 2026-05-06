"""FastAPI dashboard backend — REST + WebSocket for real-time data."""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routers import portfolio, trades, risk, strategies, system, settings, market, chat, screener


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting up")
    yield
    logger.info("API shutting down")


app = FastAPI(
    title="India Quant Fund API",
    version="1.0.0",
    description="Real-time dashboard API for automated hedge fund",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
app.include_router(risk.router, prefix="/api/risk", tags=["Risk"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["Strategies"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(market.router,   prefix="/api/market",   tags=["Market"])
app.include_router(chat.router,     prefix="/api/chat",     tags=["Chat"])
app.include_router(screener.router, prefix="/api/screener", tags=["Screener"])


# ── WebSocket manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket) -> None:
        self.active.remove(ws)
        logger.info(f"WebSocket disconnected. Total: {len(self.active)}")

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send live updates every 5 seconds during market hours
            snapshot = await _get_live_snapshot()
            await websocket.send_json(snapshot)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def _get_live_snapshot() -> dict:
    """Fetch current portfolio snapshot for WebSocket broadcast."""
    from data.storage import db
    try:
        pnl = db.query_df(
            "SELECT * FROM daily_pnl ORDER BY date DESC LIMIT 1"
        )
        positions = db.query_df("SELECT * FROM positions")
        return {
            "type": "snapshot",
            "timestamp": datetime.now().isoformat(),
            "portfolio_value": float(pnl["portfolio_value"].iloc[0]) if not pnl.empty else 0,
            "day_pnl": float(pnl["day_pnl"].iloc[0]) if not pnl.empty else 0,
            "day_pnl_pct": float(pnl["day_pnl_pct"].iloc[0]) if not pnl.empty else 0,
            "drawdown_pct": float(pnl["drawdown_pct"].iloc[0]) if not pnl.empty else 0,
            "n_positions": len(positions),
        }
    except Exception as e:
        return {"type": "error", "message": str(e), "timestamp": datetime.now().isoformat()}


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )
