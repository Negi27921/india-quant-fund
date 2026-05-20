"""FastAPI entry point for local development (DuckDB + WebSocket).

This module is NOT deployed to Vercel. The cloud entry point is api/cloud_main.py.
Use this for local development with full WebSocket support and DuckDB-backed system endpoints.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api._config import API_TITLE, API_VERSION, CORS_CONFIG, get_allowed_origins
from api.middleware.security import SecurityHeadersMiddleware
from api.routers import (
    chat, journal, market, portfolio, risk,
    screener, settings, strategies, system, trades,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("IQF API starting — local mode (DuckDB + WebSocket)")
    yield
    logger.info("IQF API shutting down")


app = FastAPI(
    title=f"{API_TITLE} (Local)",
    version=API_VERSION,
    description="Local development server — includes WebSocket and DuckDB endpoints",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    **CORS_CONFIG,
)

# Routers (local adds system router with real DuckDB queries)
app.include_router(market.router,       prefix="/api/market",     tags=["Market"])
app.include_router(chat.router,         prefix="/api/chat",       tags=["Chat"])
app.include_router(screener.router,     prefix="/api/screener",   tags=["Screener"])
app.include_router(portfolio.router,    prefix="/api/portfolio",  tags=["Portfolio"])
app.include_router(trades.router,       prefix="/api/trades",     tags=["Trades"])
app.include_router(risk.router,         prefix="/api/risk",       tags=["Risk"])
app.include_router(strategies.router,   prefix="/api/strategies", tags=["Strategies"])
app.include_router(system.router,       prefix="/api/system",     tags=["System"])
app.include_router(settings.router,     prefix="/api/settings",   tags=["Settings"])
app.include_router(journal.router,      prefix="/api/journal",    tags=["Journal"])


# ── WebSocket (local only — Vercel doesn't support persistent connections) ────

_WS_MAX = int(os.getenv("WS_MAX_CONNECTIONS", "50"))


class _ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> bool:
        if len(self.active) >= _WS_MAX:
            await ws.close(code=1008, reason="Connection limit reached")
            return False
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WS connected — {len(self.active)} active")
        return True

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws) if hasattr(self.active, "discard") else (ws in self.active and self.active.remove(ws))
        logger.info(f"WS disconnected — {len(self.active)} active")

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.active:
                self.active.remove(ws)


_manager = _ConnectionManager()


async def _live_snapshot() -> dict:
    """Current portfolio snapshot for WebSocket broadcast."""
    try:
        from data.storage import db
        pnl = db.query_df("SELECT * FROM daily_pnl ORDER BY date DESC LIMIT 1")
        positions = db.query_df("SELECT * FROM positions")
        return {
            "type": "snapshot",
            "timestamp": datetime.now().isoformat(),
            "portfolio_value": float(pnl["portfolio_value"].iloc[0]) if not pnl.empty else 0,
            "day_pnl":         float(pnl["day_pnl"].iloc[0])         if not pnl.empty else 0,
            "day_pnl_pct":     float(pnl["day_pnl_pct"].iloc[0])     if not pnl.empty else 0,
            "drawdown_pct":    float(pnl["drawdown_pct"].iloc[0])     if not pnl.empty else 0,
            "n_positions":     len(positions),
        }
    except Exception as exc:
        logger.warning(f"WS snapshot error: {exc}")
        return {"type": "error", "message": "snapshot unavailable", "timestamp": datetime.now().isoformat()}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not await _manager.connect(websocket):
        return
    try:
        while True:
            await websocket.send_json(await _live_snapshot())
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        _manager.disconnect(websocket)
    except Exception:
        _manager.disconnect(websocket)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "mode": "local"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )
