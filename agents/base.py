"""Base agent — stateless LLM client with multi-provider fallback chain."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar

from loguru import logger
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Provider priority: first key with a value wins, then fallbacks in order
_PROVIDER_ORDER = ["gemini", "groq", "openai", "deepseek", "qwen", "ollama"]


class BaseLLMClient:
    """
    Unified LLM client supporting Groq (free), DeepSeek, Gemini, Qwen via
    OpenRouter, and Ollama (local). Falls back through the chain automatically.
    """

    def __init__(self, model: str | None = None):
        self._preferred_provider = os.getenv("LLM_PROVIDER", "groq").lower()
        self._model_override = model
        self._clients: dict[str, Any] = {}

    # ── Provider constructors ────────────────────────────────────────────────

    def _openai(self):
        if "openai" not in self._clients:
            from openai import OpenAI
            kwargs: dict = {"api_key": os.getenv("OPENAI_API_KEY", "")}
            base_url = os.getenv("OPENAI_BASE_URL", "").strip()
            if base_url:
                kwargs["base_url"] = base_url
            self._clients["openai"] = OpenAI(**kwargs)
        return self._clients["openai"]

    def _groq(self):
        if "groq" not in self._clients:
            from openai import OpenAI
            self._clients["groq"] = OpenAI(
                api_key=os.getenv("GROQ_API_KEY", ""),
                base_url="https://api.groq.com/openai/v1",
            )
        return self._clients["groq"]

    def _deepseek(self):
        if "deepseek" not in self._clients:
            from openai import OpenAI
            self._clients["deepseek"] = OpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )
        return self._clients["deepseek"]

    def _openrouter(self):
        if "openrouter" not in self._clients:
            from openai import OpenAI
            self._clients["openrouter"] = OpenAI(
                api_key=os.getenv("OPENROUTER_API_KEY", ""),
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/Negi27921/one-piece",
                    "X-Title": "One Piece",
                },
            )
        return self._clients["openrouter"]

    def _ollama(self):
        if "ollama" not in self._clients:
            from openai import OpenAI
            self._clients["ollama"] = OpenAI(
                api_key="ollama",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1",
            )
        return self._clients["ollama"]

    # ── Model names per provider ─────────────────────────────────────────────

    def _model_for(self, provider: str) -> str:
        if self._model_override:
            return self._model_override
        defaults = {
            "openai":    os.getenv("OPENAI_MODEL",      "gpt-4o-mini"),
            "groq":      os.getenv("GROQ_MODEL",        "llama-3.3-70b-versatile"),
            "deepseek":  os.getenv("DEEPSEEK_MODEL",    "deepseek-chat"),
            "gemini":    os.getenv("GEMINI_MODEL",      "gemini-2.0-flash"),
            "qwen":      os.getenv("OPENROUTER_MODEL",  "qwen/qwen3-235b-a22b:free"),
            "ollama":    os.getenv("OLLAMA_MODEL",      "llama3.2"),
        }
        return defaults.get(provider, "gpt-4o-mini")

    def _has_key(self, provider: str) -> bool:
        keys = {
            "openai":   "OPENAI_API_KEY",
            "groq":     "GROQ_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "gemini":   "GEMINI_API_KEY",
            "qwen":     "OPENROUTER_API_KEY",
            "ollama":   None,  # always available if server is running
        }
        env_key = keys.get(provider)
        if env_key is None:
            return True
        return bool(os.getenv(env_key, "").strip())

    # ── Core completion ──────────────────────────────────────────────────────

    def complete(
        self,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        # Build provider fallback order starting from preferred
        preferred = self._preferred_provider
        order = [preferred] + [p for p in _PROVIDER_ORDER if p != preferred]

        for provider in order:
            if not self._has_key(provider):
                continue
            try:
                result = self._call(provider, system, user, temperature, max_tokens)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"LLM provider '{provider}' failed: {e}")
                continue

        logger.error("All LLM providers failed — returning empty string")
        return ""

    def _call(
        self,
        provider: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        model = self._model_for(provider)

        if provider == "gemini":
            return self._gemini_call(system, user)

        client_map = {
            "openai":   self._openai,
            "groq":     self._groq,
            "deepseek": self._deepseek,
            "qwen":     self._openrouter,
            "ollama":   self._ollama,
        }
        client = client_map[provider]()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def _gemini_call(self, system: str, user: str) -> str:
        import google.generativeai as genai
        if "gemini" not in self._clients:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
            self._clients["gemini"] = genai.GenerativeModel(
                self._model_for("gemini")
            )
        resp = self._clients["gemini"].generate_content(f"{system}\n\n{user}")
        return resp.text or ""

    def complete_json(
        self,
        system: str,
        user: str,
        schema: Type[T],
        model: str | None = None,
    ) -> T | None:
        schema_hint = (
            f"\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{schema.model_json_schema()}"
        )
        response = self.complete(system + schema_hint, user, model=model)
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return schema.model_validate_json(text.strip())
        except Exception as e:
            logger.warning(f"JSON parse failed: {e} | response: {response[:200]}")
            return None

    # ── Diagnostics ─────────────────────────────────────────────────────────

    def probe_providers(self) -> dict[str, dict]:
        """Test each provider and return status. Used by the Settings API."""
        results = {}
        probe_msg = "Reply with exactly: ok"

        for provider in _PROVIDER_ORDER:
            if not self._has_key(provider):
                results[provider] = {"status": "no_key", "model": self._model_for(provider)}
                continue
            try:
                resp = self._call(provider, "You are a test assistant.", probe_msg, 0, 10)
                results[provider] = {
                    "status": "ok" if resp else "empty_response",
                    "model": self._model_for(provider),
                }
            except Exception as e:
                results[provider] = {
                    "status": "error",
                    "model": self._model_for(provider),
                    "error": str(e)[:120],
                }
        return results


class BaseAgent(ABC):
    name: str
    model: str | None = None

    def __init__(self):
        self.llm = BaseLLMClient(self.model)
        self._system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        from pathlib import Path
        prompt_path = Path(__file__).parent / "prompts" / f"{self.name}.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        return f"You are the {self.name} agent for an automated Indian equity hedge fund."

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]: ...

    def _call_llm(self, user_message: str) -> str:
        return self.llm.complete(system=self._system_prompt, user=user_message)

    def _call_llm_json(self, user_message: str, schema: Type[T]) -> T | None:
        return self.llm.complete_json(
            system=self._system_prompt, user=user_message, schema=schema
        )

    def log(self, message: str, level: str = "info") -> None:
        getattr(logger, level)(f"[{self.name}] {message}")
