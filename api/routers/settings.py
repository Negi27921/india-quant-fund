"""Settings and connectivity diagnostics API."""
from __future__ import annotations
import os
from fastapi import APIRouter, Depends

from api.middleware.security import require_internal_key

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
                "id":      "openai",
                "label":   "OpenAI (Agent Router)",
                "tier":    "paid",
                "model":   os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "has_key": _has_key("OPENAI_API_KEY"),
                "url":     "https://platform.openai.com",
                "models":  ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            },
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
async def probe_providers(_: None = Depends(require_internal_key)):
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
async def test_telegram(_: None = Depends(require_internal_key)):
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
                json={"chat_id": chat_id, "text": "✅ One Piece Dashboard — Telegram connection test successful!"},
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


@router.get("/agent-config")
async def get_agent_config():
    """Return trading agent configuration from Supabase or defaults."""
    defaults = {
        "min_confidence":    95,
        "trade_amount":      25000,
        "max_open_trades":   30,
        "kill_drawdown":     15.0,
        "risk_pct_per_trade": 2.0,
        "strategies": ["vcp", "breakout", "golden_cross", "multibagger", "ipo_base", "rocket_base", "rsi_reversal"],
        "strategy_params": {
            "vcp":          {"target_pct": 8.0,  "sl_pct": 4.0,  "hold_days": 15},
            "ipo_base":     {"target_pct": 12.0, "sl_pct": 5.0,  "hold_days": 20},
            "rocket_base":  {"target_pct": 15.0, "sl_pct": 6.0,  "hold_days": 10},
            "breakout":     {"target_pct": 7.0,  "sl_pct": 3.0,  "hold_days": 10},
            "rsi_reversal": {"target_pct": 6.0,  "sl_pct": 3.0,  "hold_days": 7},
            "golden_cross": {"target_pct": 10.0, "sl_pct": 4.0,  "hold_days": 20},
            "multibagger":  {"target_pct": 20.0, "sl_pct": 7.0,  "hold_days": 30},
        },
    }
    try:
        from data.storage import supabase_db as sdb
        import json
        rows = sdb.select("app_config", cols="value", filters={"key": "agent_config"}, limit=1)
        if rows:
            raw = rows[0].get("value") or {}
            stored = json.loads(raw) if isinstance(raw, str) else raw
            defaults.update(stored)
    except Exception:
        pass
    return defaults


@router.put("/agent-config")
async def update_agent_config(body: dict, _: None = Depends(require_internal_key)):
    """Persist trading agent configuration to Supabase app_config table."""
    import json as _json
    ALLOWED = {
        "min_confidence", "trade_amount", "max_open_trades",
        "kill_drawdown", "risk_pct_per_trade", "strategies", "strategy_params",
    }
    update = {k: v for k, v in body.items() if k in ALLOWED}
    try:
        from data.storage import supabase_db as sdb
        existing = sdb.select("app_config", cols="key", filters={"key": "agent_config"}, limit=1)
        if existing:
            sdb.update("app_config", {"value": update}, {"key": "agent_config"})
        else:
            sdb.insert("app_config", {"key": "agent_config", "value": update})
        return {"ok": True, "saved": update}
    except Exception as e:
        return {"ok": False, "error": str(e)}
