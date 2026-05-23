"""NVIDIA NIM AI provider — DeepSeek R1 via NVIDIA's OpenAI-compatible API.

NVIDIA's API is fully OpenAI-compatible:
  Base URL: https://integrate.api.nvidia.com/v1
  Auth:     Bearer NVIDIA_API_KEY
  Models:   deepseek-ai/deepseek-r1 (default)
            deepseek-ai/deepseek-r1-distill-llama-70b
            deepseek-ai/deepseek-r1-distill-qwen-32b

Env vars:
  NVIDIA_API_KEY    — required (nvapi-...)
  NVIDIA_MODEL      — optional, default deepseek-ai/deepseek-r1
  NVIDIA_TIMEOUT    — optional, default 12.0s
"""
from __future__ import annotations

import os
from typing import Any

from core.providers.base import AIProvider

_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaProvider(AIProvider):
    DEFAULT_MODEL = "deepseek-ai/deepseek-r1"

    def __init__(self) -> None:
        self._key = os.getenv("NVIDIA_API_KEY", "")
        self._model = os.getenv("NVIDIA_MODEL", self.DEFAULT_MODEL)
        self._timeout = float(os.getenv("NVIDIA_TIMEOUT", "12.0"))

    def is_available(self) -> bool:
        return bool(self._key)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.6,
    ) -> str:
        if not self._key:
            raise RuntimeError("NVIDIA_API_KEY not configured")

        import json, urllib.request

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        req = urllib.request.Request(
            f"{_BASE_URL}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as ctx:
            resp = json.loads(ctx.read().decode())

        content = resp["choices"][0]["message"]["content"]
        # DeepSeek R1 wraps reasoning in <think>...</think> — strip it for concise replies
        if "<think>" in content and "</think>" in content:
            after = content.split("</think>", 1)[-1].strip()
            if after:
                content = after

        return content

    def name(self) -> str:
        return "nvidia"
