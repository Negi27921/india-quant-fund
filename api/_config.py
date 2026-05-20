"""Shared configuration for all IQF API entry points.

Single source of truth for CORS, versioning, and allowed origins.
Both cloud_main.py (Vercel) and main.py (local) import from here.
"""
from __future__ import annotations

import os

# ── Versioning ────────────────────────────────────────────────────────────────
API_TITLE   = "India Quant Fund API"
API_VERSION = "2.1.0"

# ── CORS ─────────────────────────────────────────────────────────────────────
# Production origins are hard-coded; add new domains via EXTRA_ORIGINS env var
# (comma-separated, e.g. "https://new-domain.vercel.app,https://staging.example.com")
_DEFAULT_ORIGINS = [
    "https://luffy-labs.vercel.app",
    "https://onepiece-labs.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

def get_allowed_origins() -> list[str]:
    extra = os.getenv("EXTRA_CORS_ORIGINS", "")
    additional = [o.strip() for o in extra.split(",") if o.strip()]
    return _DEFAULT_ORIGINS + additional

CORS_CONFIG = dict(
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# ── Router prefix map ─────────────────────────────────────────────────────────
# Single source of truth — both entry points register the same prefixes
ROUTER_PREFIXES = {
    "market":      "/api/market",
    "chat":        "/api/chat",
    "screener":    "/api/screener",
    "portfolio":   "/api/portfolio",
    "trades":      "/api/trades",
    "risk":        "/api/risk",
    "telegram":    "/api/telegram",
    "strategies":  "/api/strategies",
    "settings":    "/api/settings",
    "journal":     "/api/journal",
    "system":      "/api/system",
}
