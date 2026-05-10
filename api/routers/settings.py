"""Settings and connectivity diagnostics API."""
from __future__ import annotations
import os
from fastapi import APIRouter

router = APIRouter()


def _has_key(env_var: str) -> bool:
    return bool(os.getenv(env_var, "").strip())


@router.get("/providers")
async def get_providers():
    """Return configured LLM providers and their key status (no key material)."""
    return {
        "active": os.getenv("LLM_PROVIDER", "groq"),
        "providers": [
            {
                "id":      "groq",
                "label":   "Groq",
                "tier":    "free",
                "model":   os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "has_key": _has_key("GROQ_API_KEY"),
                "url":     "https://console.groq.com",
                "models":  ["llama-3.3-70b-versatile", "qwen-qwq-32b", "mixtral-8x7b-32768", "gemma2-9b-it"],
            },
            {
                "id":      "deepseek",
                "label":   "DeepSeek",
                "tier":    "paid",
                "model":   os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "has_key": _has_key("DEEPSEEK_API_KEY"),
                "url":     "https://platform.deepseek.com",
                "models":  ["deepseek-chat", "deepseek-reasoner"],
            },
            {
                "id":      "gemini",
                "label":   "Gemini",
                "tier":    "free",
                "model":   os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
                "has_key": _has_key("GEMINI_API_KEY"),
                "url":     "https://aistudio.google.com",
                "models":  ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"],
            },
            {
                "id":      "qwen",
                "label":   "Qwen / OpenRouter",
                "tier":    "free",
                "model":   os.getenv("OPENROUTER_MODEL", "qwen/qwen3-235b-a22b:free"),
                "has_key": _has_key("OPENROUTER_API_KEY"),
                "url":     "https://openrouter.ai",
                "models":  [
                    "nvidia/nemotron-3-super-120b-a12b:free",
                    "openai/gpt-oss-120b:free",
                    "meta-llama/llama-3.3-70b-instruct:free",
                    "google/gemma-3-27b-it:free",
                    "qwen/qwen3-next-80b-a3b-instruct:free",
                ],
            },
            {
                "id":      "ollama",
                "label":   "Ollama (Local)",
                "tier":    "local",
                "model":   os.getenv("OLLAMA_MODEL", "llama3.2"),
                "has_key": True,
                "url":     "https://ollama.com",
                "models":  ["llama3.2", "qwen2.5", "mistral", "phi4"],
            },
        ],
    }


@router.post("/providers/probe")
async def probe_providers():
    """Live-test every configured LLM provider. Takes a few seconds."""
    from agents.base import BaseLLMClient
    client = BaseLLMClient()
    return client.probe_providers()


@router.get("/brokers")
async def get_brokers():
    """Return broker configuration status (no key material)."""
    return [
        {
            "id":      "dhan",
            "label":   "Dhan",
            "role":    "primary",
            "has_key": _has_key("DHAN_CLIENT_ID"),
            "url":     "https://dhanhq.co",
        },
        {
            "id":      "shoonya",
            "label":   "Shoonya / Finvasia",
            "role":    "failover",
            "has_key": _has_key("SHOONYA_USER"),
            "url":     "https://shoonya.finvasia.com",
        },
    ]


@router.get("/alerts")
async def get_alert_config():
    """Return alert channel configuration status (no key material)."""
    return {
        "telegram": {
            "configured": _has_key("TELEGRAM_BOT_TOKEN"),
            "chat_id_set": _has_key("TELEGRAM_CHAT_ID"),
        },
        "email": {
            "configured": _has_key("SMTP_USER"),
            "smtp_host": os.getenv("SMTP_HOST", ""),
        },
    }


@router.post("/alerts/test-telegram")
async def test_telegram():
    """Send a test message to the configured Telegram chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"}
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "✅ IQF Dashboard — Telegram connection test successful!"},
                timeout=8,
            )
        data = r.json()
        return {"ok": data.get("ok", False), "message_id": data.get("result", {}).get("message_id")}
    except Exception:
        return {"ok": False, "error": "telegram send failed"}


@router.get("/env")
async def get_env_summary():
    """Non-sensitive summary of current environment settings."""
    return {
        "env":             os.getenv("ENV", "development"),
        "paper_trading":   os.getenv("PAPER_TRADING", "true").lower() == "true",
        "initial_capital": float(os.getenv("INITIAL_CAPITAL", "100000")),
        "llm_provider":    os.getenv("LLM_PROVIDER", "groq"),
        "log_level":       os.getenv("LOG_LEVEL", "INFO"),
    }
