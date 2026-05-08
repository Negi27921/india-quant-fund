"""Slim FastAPI app for cloud deployment — market data, screener, chat only.
Portfolio/trades/risk require local DuckDB and are excluded here.
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import market, chat, screener

app = FastAPI(title="IQF Cloud API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router,   prefix="/api/market",   tags=["Market"])
app.include_router(chat.router,     prefix="/api/chat",     tags=["Chat"])
app.include_router(screener.router, prefix="/api/screener", tags=["Screener"])


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "mode": "cloud"}


@app.get("/api/portfolio/summary")
async def portfolio_stub():
    return {"error": "portfolio requires local backend", "cloud": True}


@app.get("/api/trades/recent")
async def trades_stub():
    return {"trades": [], "cloud": True}


@app.get("/api/risk/metrics")
async def risk_stub():
    return {"error": "risk metrics require local backend", "cloud": True}
