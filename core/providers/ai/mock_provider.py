"""Mock AI provider — returns deterministic responses for dev/testing."""
from __future__ import annotations

from core.providers.base import AIProvider


class MockAIProvider(AIProvider):
    def is_available(self) -> bool:
        return True

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        last = messages[-1].get("content", "") if messages else ""
        return (
            f"[MOCK AI] Responding to: '{last[:80]}'. "
            "This is a deterministic mock response for development. "
            "Set AI_PROVIDER=groq (and GROQ_API_KEY) for real AI responses."
        )

    def name(self) -> str:
        return "mock"
