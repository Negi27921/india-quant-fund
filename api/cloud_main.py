"""FastAPI entry point for Vercel (cloud) deployment.

All persistent state uses Supabase (no DuckDB, no WebSocket).
System endpoints return lightweight stubs — monitoring is done via Supabase dashboards.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api._config import API_TITLE, API_VERSION, CORS_CONFIG, get_allowed_origins
from api.middleware.security import SecurityHeadersMiddleware
from api.routers import (
    chat, journal, market, portfolio, risk,
    screener, settings, strategies, telegram_bot, trades,
)

# ── System router (Supabase-compatible stubs) ─────────────────────────────────
# The full system.py uses DuckDB which is not available on Vercel.
# These lightweight endpoints keep the frontend kill-switch and health checks alive.
from fastapi import APIRouter as _AR
from datetime import timezone as _tz

_system = _AR()

@_system.get("/health")
async def system_health():
    return {
        "database": "supabase",
        "api": "ok",
        "timestamp": datetime.now(_tz.utc).isoformat(),
        "mode": "cloud",
    }

@_system.get("/kill-switch/status")
async def kill_switch_status():
    # Cloud deployment does not run a local kill-switch daemon.
    # Use the Supabase dashboard or Telegram bot to manage risk limits.
    return {"active": False, "triggered_at": None, "reason": None}

@_system.get("/audit-log")
async def audit_log():
    return []


# ── App factory ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    yield  # nothing to start/stop on Vercel serverless


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    docs_url=None,    # Swagger UI disabled in production
    redoc_url=None,
    lifespan=lifespan,
)

# Middleware (order matters — security headers first, then CORS)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    **CORS_CONFIG,
)

# Routers
app.include_router(market.router,       prefix="/api/market",     tags=["Market"])
app.include_router(chat.router,         prefix="/api/chat",       tags=["Chat"])
app.include_router(screener.router,     prefix="/api/screener",   tags=["Screener"])
app.include_router(portfolio.router,    prefix="/api/portfolio",  tags=["Portfolio"])
app.include_router(trades.router,       prefix="/api/trades",     tags=["Trades"])
app.include_router(risk.router,         prefix="/api/risk",       tags=["Risk"])
app.include_router(telegram_bot.router, prefix="/api/telegram",   tags=["Telegram"])
app.include_router(strategies.router,   prefix="/api/strategies", tags=["Strategies"])
app.include_router(settings.router,     prefix="/api/settings",   tags=["Settings"])
app.include_router(journal.router,      prefix="/api/journal",    tags=["Journal"])
app.include_router(_system,             prefix="/api/system",     tags=["System"])


@app.get("/health", tags=["System"])
async def root_health():
    """Root health check — used by Vercel deployment validation."""
    return {"status": "ok", "timestamp": datetime.now(_tz.utc).isoformat(), "mode": "cloud"}
