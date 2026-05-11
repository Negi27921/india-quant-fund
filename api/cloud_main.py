"""Slim FastAPI app for cloud deployment — all endpoints backed by Supabase."""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import market, chat, screener, portfolio, trades, risk, telegram_bot, strategies, settings
from api.middleware.security import SecurityHeadersMiddleware

_ALLOWED_ORIGINS = [
    "https://luffy-labs.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

app = FastAPI(title="IQF Cloud API", version="2.0.0", docs_url=None, redoc_url=None)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

app.include_router(market.router,        prefix="/api/market",    tags=["Market"])
app.include_router(chat.router,          prefix="/api/chat",      tags=["Chat"])
app.include_router(screener.router,      prefix="/api/screener",  tags=["Screener"])
app.include_router(portfolio.router,     prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(trades.router,        prefix="/api/trades",    tags=["Trades"])
app.include_router(risk.router,          prefix="/api/risk",      tags=["Risk"])
app.include_router(telegram_bot.router,  prefix="/api/telegram",  tags=["Telegram"])
app.include_router(strategies.router,    prefix="/api/strategies", tags=["Strategies"])
app.include_router(settings.router,      prefix="/api/settings",   tags=["Settings"])

# Lightweight system stubs — the local system.py uses DuckDB which isn't on Vercel.
# These return safe cloud-compatible responses so the frontend doesn't 404.
_system = APIRouter()

@_system.get("/health")
async def system_health():
    return {"database": "supabase", "api": "ok", "timestamp": datetime.now().isoformat(), "paper_trading": True}

@_system.get("/kill-switch/status")
async def kill_switch_status():
    return {"active": False, "triggered_at": None, "reason": None}

@_system.get("/audit-log")
async def audit_log():
    return []

app.include_router(_system, prefix="/api/system", tags=["System"])


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "mode": "cloud"}
