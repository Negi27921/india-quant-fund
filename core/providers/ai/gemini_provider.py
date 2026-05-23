"""Google Gemini LLM provider (fallback #1)."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from core.providers.base import AIProvider


class GeminiProvider(AIProvider):
    MODEL = "gemini-2.0-flash"
    TIMEOUT = 8.0

    def __init__(self) -> None:
        self._key = os.getenv("GEMINI_API_KEY", "")

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
            raise RuntimeError("GEMINI_API_KEY not configured")

        parts = [{"text": f"[SYSTEM]\n{system_prompt}\n\n[CONVERSATION]"}]
        for m in messages:
            role = m.get("role", "user")
            parts.append({"text": f"[{role.upper()}]\n{m.get('content', '')}"})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.MODEL}:generateContent?key={self._key}"
        )
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        ctx = urllib.request.urlopen(req, timeout=self.TIMEOUT)
        resp = json.loads(ctx.read().decode())
        return resp["candidates"][0]["content"]["parts"][0]["text"]

    def name(self) -> str:
        return "gemini"
