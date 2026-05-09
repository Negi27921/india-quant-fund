"""Slim FastAPI app for cloud deployment — all endpoints backed by Supabase."""
from __future__ import annotations

from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import market, chat, screener, portfolio, trades, risk, telegram_bot

app = FastAPI(title="IQF Cloud API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router,        prefix="/api/market",    tags=["Market"])
app.include_router(chat.router,          prefix="/api/chat",      tags=["Chat"])
app.include_router(screener.router,      prefix="/api/screener",  tags=["Screener"])
app.include_router(portfolio.router,     prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(trades.router,        prefix="/api/trades",    tags=["Trades"])
app.include_router(risk.router,          prefix="/api/risk",      tags=["Risk"])
app.include_router(telegram_bot.router,  prefix="/api/telegram",  tags=["Telegram"])


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "mode": "cloud"}
