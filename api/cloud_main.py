"""FastAPI entry point for Vercel (cloud) deployment.

All persistent state uses Supabase (no DuckDB, no WebSocket).
System endpoints return lightweight stubs — monitoring is done via Supabase dashboards.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api._config import API_TITLE, API_VERSION, CORS_CONFIG, get_allowed_origins
from api.middleware.security import SecurityHeadersMiddleware, require_internal_key
from api.routers import (
    chat, journal, market, portfolio, risk,
    screener, settings, strategies, telegram_bot, trades, watchlist,
)
from api.routers import profile as profile_router

# ── System router (Supabase-compatible stubs) ─────────────────────────────────
# The full system.py uses DuckDB which is not available on Vercel.
# These lightweight endpoints keep the frontend kill-switch and health checks alive.
_system = APIRouter()


@_system.get("/health")
async def system_health() -> dict[str, Any]:
    return {
        "database": "supabase",
        "api": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "cloud",
    }


@_system.get("/kill-switch/status")
async def kill_switch_status() -> dict[str, Any]:
    try:
        import json as _json
        from data.storage import supabase_db as sdb
        rows = sdb.select("app_config", cols="value", filters={"key": "kill_switch"}, limit=1)
        if rows:
            data = rows[0].get("value") or {}
            if isinstance(data, str):
                data = _json.loads(data)
            return {
                "active": bool(data.get("active", False)),
                "triggered_at": data.get("triggered_at"),
                "reason": data.get("reason"),
            }
    except Exception:
        pass
    return {"active": False, "triggered_at": None, "reason": None}


@_system.post("/kill-switch")
async def set_kill_switch(
    body: dict[str, Any],
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    try:
        from data.storage import supabase_db as sdb
        value = {
            "active":       bool(body.get("active", False)),
            "triggered_at": body.get("triggered_at") or datetime.now(timezone.utc).isoformat(),
            "reason":       body.get("reason"),
        }
        existing = sdb.select("app_config", cols="key", filters={"key": "kill_switch"}, limit=1)
        if existing:
            sdb.update("app_config", {"value": value}, {"key": "kill_switch"})
        else:
            sdb.insert("app_config", {"key": "kill_switch", "value": value})
        return {"ok": True, **value}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@_system.get("/audit-log")
async def audit_log() -> list[Any]:
    return []


# ── App factory ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[type-arg]
    yield  # nothing to start/stop on Vercel serverless


app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    docs_url=None,
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
app.include_router(market.router, prefix="/api/market", tags=["Market"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(screener.router, prefix="/api/screener", tags=["Screener"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
app.include_router(risk.router, prefix="/api/risk", tags=["Risk"])
app.include_router(telegram_bot.router, prefix="/api/telegram", tags=["Telegram"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["Strategies"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(journal.router, prefix="/api/journal", tags=["Journal"])
app.include_router(watchlist.router, prefix="/api/watchlists", tags=["Watchlist"])
app.include_router(profile_router.router, prefix="/api", tags=["Profile"])
app.include_router(_system, prefix="/api/system", tags=["System"])


@app.get("/health", tags=["System"])
async def root_health() -> dict[str, str]:
    """Root health check — used by Vercel deployment validation."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat(), "mode": "cloud"}
