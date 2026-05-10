"""Security middleware, dependencies, and helpers shared across all routers."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

# ── Internal API key (for destructive / admin endpoints) ─────────────────────
_INTERNAL_KEY = os.getenv("INTERNAL_API_KEY", "")


def require_internal_key(x_api_key: str = Header(default="")) -> None:
    """FastAPI dependency — enforce INTERNAL_API_KEY on sensitive endpoints."""
    if not _INTERNAL_KEY:
        return  # not configured → skip (backward compat for local dev)
    if not x_api_key or x_api_key != _INTERNAL_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Security response headers ─────────────────────────────────────────────────
_SEC_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in _SEC_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


# ── Lightweight in-process rate limiter (per-IP, per-path) ───────────────────
# NOTE: serverless = per-instance; use Redis (Upstash) for cluster-wide limiting.
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()

RATE_LIMIT_DEFAULT = int(os.getenv("RATE_LIMIT_RPM", "60"))   # requests per minute
RATE_LIMIT_CHAT    = int(os.getenv("RATE_LIMIT_CHAT_RPM", "10"))
RATE_LIMIT_SCAN    = int(os.getenv("RATE_LIMIT_SCAN_RPM", "5"))


def _check_rate(key: str, limit: int, window: int = 60) -> None:
    now = time.monotonic()
    with _rate_lock:
        hits = _rate_store[key]
        _rate_store[key] = [t for t in hits if now - t < window]
        if len(_rate_store[key]) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded — slow down.")
        _rate_store[key].append(now)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or request.client.host if request.client else "unknown"


def rate_limit(request: Request, limit: int = RATE_LIMIT_DEFAULT) -> None:
    """FastAPI dependency — call with Depends(rate_limit)."""
    ip = _client_ip(request)
    path = request.url.path
    _check_rate(f"{ip}:{path}", limit)


def rate_limit_chat(request: Request) -> None:
    rate_limit(request, RATE_LIMIT_CHAT)


def rate_limit_scan(request: Request) -> None:
    rate_limit(request, RATE_LIMIT_SCAN)
