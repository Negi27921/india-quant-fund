"""Cascading AI provider — tries providers in order until one succeeds.

Usage
-----
from core.providers.ai.chain_provider import AIChainProvider
chain = AIChainProvider()
response = chain.complete(system, messages)
# chain.last_provider shows which provider answered
"""
from __future__ import annotations

from typing import Any

from core.config import settings
from core.providers.base import AIProvider


def _build_provider(name: str) -> AIProvider | None:
    try:
        if name in ("nvidia", "deepseek"):
            from core.providers.ai.nvidia_provider import NvidiaProvider
            p = NvidiaProvider()
            return p if p.is_available() else None
        if name == "groq":
            from core.providers.ai.groq_provider import GroqProvider
            p = GroqProvider()
            return p if p.is_available() else None
        if name == "gemini":
            from core.providers.ai.gemini_provider import GeminiProvider
            p = GeminiProvider()
            return p if p.is_available() else None
        if name == "openrouter":
            from core.providers.ai.openrouter_provider import OpenRouterProvider
            p = OpenRouterProvider()
            return p if p.is_available() else None
        if name == "mock":
            from core.providers.ai.mock_provider import MockAIProvider
            return MockAIProvider()
    except Exception:
        pass
    return None


class AIChainProvider(AIProvider):
    """Cascades through a list of providers, returning the first success.

    The chain order is read from settings.AI_FALLBACK_CHAIN (env var
    AI_FALLBACK_CHAIN, comma-separated, default: groq,gemini,openrouter).
    """

    def __init__(self) -> None:
        self.last_provider: str = "none"
        self._chain = settings.AI_FALLBACK_CHAIN

    def is_available(self) -> bool:
        return any(_build_provider(n) is not None for n in self._chain)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        last_exc: Exception = RuntimeError("No AI provider configured or available")
        for name in self._chain:
            provider = _build_provider(name)
            if provider is None:
                continue
            try:
                result = provider.complete(system_prompt, messages, max_tokens, temperature)
                self.last_provider = name
                return result
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc

    def name(self) -> str:
        return f"chain({','.join(self._chain)})"
