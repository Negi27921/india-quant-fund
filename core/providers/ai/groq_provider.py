"""Groq LLM provider (primary for speed — Llama 3.3 70B)."""
from __future__ import annotations

import os
from typing import Any

from core.providers.base import AIProvider


class GroqProvider(AIProvider):
    MODEL = "llama-3.3-70b-versatile"
    TIMEOUT = 8.0

    def __init__(self) -> None:
        self._key = os.getenv("GROQ_API_KEY", "")

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
            raise RuntimeError("GROQ_API_KEY not configured")
        import urllib.request, json, urllib.error
        payload = {
            "model": self.MODEL,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        import socket
        ctx = urllib.request.urlopen(req, timeout=self.TIMEOUT)
        resp = json.loads(ctx.read().decode())
        return resp["choices"][0]["message"]["content"]

    def name(self) -> str:
        return "groq"
