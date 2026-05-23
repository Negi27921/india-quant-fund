"""OpenRouter LLM provider (fallback #2 — multi-model gateway)."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from core.providers.base import AIProvider


class OpenRouterProvider(AIProvider):
    MODEL = "meta-llama/llama-3.3-70b-instruct"
    TIMEOUT = 8.0

    def __init__(self) -> None:
        self._key = os.getenv("OPENROUTER_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._key)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        if not self._key:
            raise RuntimeError("OPENROUTER_API_KEY not configured")
        payload = {
            "model": self.MODEL,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://luffy-labs.vercel.app",
                "X-Title": "One Piece Quant",
            },
            method="POST",
        )
        ctx = urllib.request.urlopen(req, timeout=self.TIMEOUT)
        resp = json.loads(ctx.read().decode())
        return resp["choices"][0]["message"]["content"]

    def name(self) -> str:
        return "openrouter"
