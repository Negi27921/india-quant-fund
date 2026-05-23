"""Unified application configuration — single source of truth for all env vars.

Usage
-----
from core.config import settings

settings.SUPABASE_URL
settings.GROQ_API_KEY
settings.MARKET_PROVIDER   # "yfinance" | "nse" | "kite" | "dhan" | "mock"
settings.AI_PROVIDER       # "groq" | "gemini" | "openrouter" | "mock"
settings.CACHE_PROVIDER    # "memory" | "supabase" | "redis"
settings.NOTIFY_PROVIDER   # "telegram" | "email" | "both" | "none"
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal


class Settings:
    """Reads all configuration from environment variables at import time.

    Designed to be backward-compatible: every env var that existed before
    still works.  New provider-selection vars default to the current
    (free-tier) behaviour so nothing breaks on upgrade.
    """

    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str = os.getenv(
        "SUPABASE_URL", "https://ohwgibzmaxfxivenbfhm.supabase.co"
    )
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # ── Auth ──────────────────────────────────────────────────────────────────
    INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY", "")
    AUTH_PHRASE: str = os.getenv("VITE_AUTH_PHRASE", "One piece is real")

    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

    # ── Email (Resend) ────────────────────────────────────────────────────────
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    REPORT_EMAIL: str = os.getenv("REPORT_EMAIL", "")
    EMAIL_FROM: str = os.getenv(
        "EMAIL_FROM", "One Piece Quant <onboarding@resend.dev>"
    )

    # ── AI / LLM ──────────────────────────────────────────────────────────────
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-r1")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

    # ── Broker credentials ────────────────────────────────────────────────────
    DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID", "")
    DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")
    SHOONYA_USER_ID: str = os.getenv("SHOONYA_USER_ID", "")
    SHOONYA_PASSWORD: str = os.getenv("SHOONYA_PASSWORD", "")
    SHOONYA_API_KEY: str = os.getenv("SHOONYA_API_KEY", "")
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_API_SECRET: str = os.getenv("KITE_API_SECRET", "")
    KITE_ACCESS_TOKEN: str = os.getenv("KITE_ACCESS_TOKEN", "")

    # ── Redis (optional — for distributed rate limiting / caching) ────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "")  # e.g. redis://localhost:6379/0
    UPSTASH_REDIS_URL: str = os.getenv("UPSTASH_REDIS_URL", "")
    UPSTASH_REDIS_TOKEN: str = os.getenv("UPSTASH_REDIS_TOKEN", "")

    # ── Provider selection ────────────────────────────────────────────────────
    # Switch any provider by setting the env var — no code changes needed.
    MARKET_PROVIDER: str = os.getenv(
        "MARKET_PROVIDER", "yfinance"
    )  # "yfinance" | "nse" | "kite" | "dhan" | "mock"

    AI_PROVIDER: str = os.getenv(
        "AI_PROVIDER", "nvidia"
    )  # "nvidia" | "groq" | "gemini" | "openrouter" | "mock"
    AI_FALLBACK_CHAIN: list[str] = [
        p.strip()
        for p in os.getenv("AI_FALLBACK_CHAIN", "nvidia,groq,gemini,openrouter").split(",")
        if p.strip()
    ]

    CACHE_PROVIDER: str = os.getenv(
        "CACHE_PROVIDER", "memory"
    )  # "memory" | "supabase" | "redis"

    NOTIFY_PROVIDER: str = os.getenv(
        "NOTIFY_PROVIDER", "telegram"
    )  # "telegram" | "email" | "both" | "none"

    # ── Rate limits ───────────────────────────────────────────────────────────
    RATE_LIMIT_RPM: int = int(os.getenv("RATE_LIMIT_RPM", "60"))
    RATE_LIMIT_CHAT_RPM: int = int(os.getenv("RATE_LIMIT_CHAT_RPM", "10"))
    RATE_LIMIT_SCAN_RPM: int = int(os.getenv("RATE_LIMIT_SCAN_RPM", "5"))

    # ── Screener / cache tuning ───────────────────────────────────────────────
    SCREENER_CACHE_TTL_H: int = int(os.getenv("SCREENER_CACHE_TTL_H", "6"))
    SCREENER_SB_CACHE_TTL_H: int = int(os.getenv("SCREENER_SB_CACHE_TTL_H", "24"))
    SCREENER_MIN_CONFIDENCE: int = int(os.getenv("MIN_CONFIDENCE", "70"))
    SCREENER_MAX_WORKERS: int = int(os.getenv("SCREENER_MAX_WORKERS", "20"))

    # ── CORS ──────────────────────────────────────────────────────────────────
    EXTRA_CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("EXTRA_CORS_ORIGINS", "").split(",")
        if o.strip()
    ]

    # ── Deployment ────────────────────────────────────────────────────────────
    DEPLOYMENT_MODE: str = os.getenv(
        "DEPLOYMENT_MODE", "cloud"
    )  # "cloud" | "local" | "fly" | "railway"
    DASHBOARD_URL: str = os.getenv(
        "DASHBOARD_URL", "https://luffy-labs.vercel.app"
    )
    API_URL: str = os.getenv("API_URL", "https://onepiece-labs.vercel.app")

    # ── Feature flags ─────────────────────────────────────────────────────────
    ENABLE_WEBSOCKET: bool = os.getenv("ENABLE_WEBSOCKET", "false").lower() == "true"
    ENABLE_PAPER_TRADING: bool = (
        os.getenv("ENABLE_PAPER_TRADING", "true").lower() == "true"
    )
    ENABLE_LIVE_TRADING: bool = (
        os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def redis_url(self) -> str:
        """Return the best available Redis URL (Upstash > REDIS_URL)."""
        if self.UPSTASH_REDIS_URL:
            return self.UPSTASH_REDIS_URL
        return self.REDIS_URL

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def has_nvidia(self) -> bool:
        return bool(self.NVIDIA_API_KEY)

    @property
    def has_groq(self) -> bool:
        return bool(self.GROQ_API_KEY)

    @property
    def has_gemini(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def has_kite(self) -> bool:
        return bool(self.KITE_API_KEY and self.KITE_ACCESS_TOKEN)

    @property
    def has_dhan(self) -> bool:
        return bool(self.DHAN_CLIENT_ID and self.DHAN_ACCESS_TOKEN)

    def provider_status(self) -> dict:
        """Return a dict of which optional providers are configured."""
        return {
            "market": self.MARKET_PROVIDER,
            "ai": self.AI_PROVIDER,
            "cache": self.CACHE_PROVIDER,
            "notify": self.NOTIFY_PROVIDER,
            "has_kite": self.has_kite,
            "has_dhan": self.has_dhan,
            "has_groq": self.has_groq,
            "has_gemini": self.has_gemini,
            "has_redis": self.has_redis,
            "live_trading": self.ENABLE_LIVE_TRADING,
            "websocket": self.ENABLE_WEBSOCKET,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
