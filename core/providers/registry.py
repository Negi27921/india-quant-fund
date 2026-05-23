"""Provider registry — creates and caches provider singletons.

Usage
-----
from core.providers.registry import (
    get_market_provider,
    get_ai_provider,
    get_cache,
    get_notifier,
)

provider = get_market_provider()
quote = provider.get_quote("RELIANCE")

Switching providers
-------------------
Set env vars before the process starts — no code changes required:

  MARKET_PROVIDER=nse       # "yfinance" | "nse" | "kite" | "dhan" | "mock"
  AI_PROVIDER=gemini        # "groq" | "gemini" | "openrouter" | "mock"
  CACHE_PROVIDER=redis      # "memory" | "supabase" | "redis"
  NOTIFY_PROVIDER=both      # "telegram" | "email" | "both" | "none"
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.providers.base import (
        AIProvider, CacheProvider, MarketDataProvider, NotificationProvider
    )


# ── Market Data ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_market_provider() -> "MarketDataProvider":
    from core.config import settings
    name = settings.MARKET_PROVIDER.lower()

    if name == "nse":
        from core.providers.market.nse_provider import NSEProvider
        return NSEProvider()
    if name in ("mock", "test"):
        from core.providers.market.mock_provider import MockMarketProvider
        return MockMarketProvider()
    # default — yfinance
    from core.providers.market.yfinance_provider import YFinanceProvider
    return YFinanceProvider()


# ── AI / LLM ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_ai_provider() -> "AIProvider":
    from core.config import settings
    name = settings.AI_PROVIDER.lower()

    if name in ("nvidia", "deepseek"):
        from core.providers.ai.nvidia_provider import NvidiaProvider
        p = NvidiaProvider()
        if p.is_available():
            return p

    if name == "groq":
        from core.providers.ai.groq_provider import GroqProvider
        p = GroqProvider()
        if p.is_available():
            return p

    if name == "gemini":
        from core.providers.ai.gemini_provider import GeminiProvider
        p = GeminiProvider()
        if p.is_available():
            return p

    if name == "openrouter":
        from core.providers.ai.openrouter_provider import OpenRouterProvider
        p = OpenRouterProvider()
        if p.is_available():
            return p

    if name in ("mock", "test"):
        from core.providers.ai.mock_provider import MockAIProvider
        return MockAIProvider()

    # Default: cascade through all configured providers
    from core.providers.ai.chain_provider import AIChainProvider
    return AIChainProvider()


@lru_cache(maxsize=1)
def get_ai_chain() -> "AIProvider":
    """Always return the cascading chain (ignores AI_PROVIDER for resilience)."""
    from core.providers.ai.chain_provider import AIChainProvider
    return AIChainProvider()


# ── Cache ─────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_cache() -> "CacheProvider":
    from core.config import settings
    name = settings.CACHE_PROVIDER.lower()

    if name == "redis":
        from core.providers.cache.redis_cache import RedisCache
        c = RedisCache()
        if c.is_connected():
            return c
        # Redis configured but not reachable — fall through to memory

    if name == "supabase":
        from core.providers.cache.supabase_cache import SupabaseCache
        return SupabaseCache()

    # default — in-process memory
    from core.providers.cache.memory_cache import MemoryCache
    return MemoryCache()


# ── Notifications ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_notifier() -> "NotificationProvider":
    from core.config import settings
    name = settings.NOTIFY_PROVIDER.lower()

    if name == "telegram":
        from core.providers.notifications.telegram_provider import TelegramProvider
        return TelegramProvider()

    if name == "email":
        from core.providers.notifications.email_provider import EmailProvider
        return EmailProvider()

    if name in ("both", "multi", "all"):
        from core.providers.notifications.multi_provider import MultiNotificationProvider
        return MultiNotificationProvider()

    if name == "none":
        from core.providers.notifications.telegram_provider import TelegramProvider
        # Return telegram but it will no-op if not configured
        return TelegramProvider()

    # Default: telegram
    from core.providers.notifications.telegram_provider import TelegramProvider
    return TelegramProvider()


# ── Convenience re-export ─────────────────────────────────────────────────────

def provider_info() -> dict:
    """Return a summary of all active providers (for /api/settings/system-info)."""
    from core.config import settings
    return {
        "market":   settings.MARKET_PROVIDER,
        "ai":       settings.AI_PROVIDER,
        "ai_chain": settings.AI_FALLBACK_CHAIN,
        "cache":    settings.CACHE_PROVIDER,
        "notify":   settings.NOTIFY_PROVIDER,
        "has_kite":      settings.has_kite,
        "has_dhan":      settings.has_dhan,
        "has_nvidia":    settings.has_nvidia,
        "has_groq":      settings.has_groq,
        "has_gemini":    settings.has_gemini,
        "has_redis":     settings.has_redis,
        "live_trading":  settings.ENABLE_LIVE_TRADING,
        "paper_trading": settings.ENABLE_PAPER_TRADING,
        "websocket":     settings.ENABLE_WEBSOCKET,
        "deployment":    settings.DEPLOYMENT_MODE,
    }
