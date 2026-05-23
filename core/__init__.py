"""One Piece Quant — core provider infrastructure.

This package provides provider-agnostic abstractions for every external
dependency (market data, AI/LLM, cache, notifications).  Swap providers
by changing environment variables — no business-logic changes required.

Quick reference
---------------
from core.config import settings
from core.providers.registry import get_market_provider, get_ai_provider, get_cache

settings.MARKET_PROVIDER   # "yfinance" | "nse" | "kite" | "mock"
settings.AI_PROVIDER       # "groq" | "gemini" | "openrouter"
settings.CACHE_PROVIDER    # "memory" | "supabase" | "redis"
"""
