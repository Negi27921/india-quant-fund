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
                "id":      "nvidia",
                "label":   "NVIDIA NIM — Nemotron 49B",
                "tier":    "free",
                "model":   os.getenv("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"),
                "has_key": _has_key("NVIDIA_API_KEY"),
                "url":     "https://build.nvidia.com",
                "models":  [
                    "nvidia/llama-3.3-nemotron-super-49b-v1",
                    "meta/llama-3.3-70b-instruct",
                    "meta/llama-3.1-405b-instruct",
                    "mistralai/mistral-large-2-instruct",
                ],
            },
            {
                "id":      "groq",
                "label":   "Groq (Fallback 1)",
                "tier":    "free",
                "model":   os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "has_key": _has_key("GROQ_API_KEY"),
                "url":     "https://console.groq.com",
                "models":  ["llama-3.3-70b-versatile", "qwen-qwq-32b", "mixtral-8x7b-32768", "gemma2-9b-it"],
            },
            {
                "id":      "gemini",
                "label":   "Gemini (Fallback 2)",
                "tier":    "free",
                "model":   os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                "has_key": _has_key("GEMINI_API_KEY"),
                "url":     "https://aistudio.google.com",
                "models":  ["gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"],
            },
            {
                "id":      "qwen",
                "label":   "OpenRouter (Fallback 3)",
                "tier":    "free",
                "model":   os.getenv("OPENROUTER_MODEL", "qwen/qwen3-235b-a22b:free"),
                "has_key": _has_key("OPENROUTER_API_KEY"),
                "url":     "https://openrouter.ai",
                "models":  [
                    "nvidia/nemotron-3-super-120b-a12b:free",
                    "meta-llama/llama-3.3-70b-instruct:free",
                    "qwen/qwen3-235b-a22b:free",
                    "google/gemma-3-27b-it:free",
                ],
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
    from core.config import settings as cfg
    return {
        "env":             os.getenv("ENV", "development"),
        "paper_trading":   cfg.ENABLE_PAPER_TRADING,
        "live_trading":    cfg.ENABLE_LIVE_TRADING,
        "initial_capital": float(os.getenv("INITIAL_CAPITAL", "100000")),
        "llm_provider":    cfg.AI_PROVIDER,
        "market_provider": cfg.MARKET_PROVIDER,
        "cache_provider":  cfg.CACHE_PROVIDER,
        "notify_provider": cfg.NOTIFY_PROVIDER,
        "deployment_mode": cfg.DEPLOYMENT_MODE,
        "log_level":       os.getenv("LOG_LEVEL", "INFO"),
        "websocket":       cfg.ENABLE_WEBSOCKET,
    }


@router.get("/system-info")
async def get_system_info():
    """Full provider configuration status — used by the dashboard Settings page."""
    from core.providers.registry import provider_info
    from core.config import settings as cfg
    return {
        **provider_info(),
        "brokers": {
            "dhan":    cfg.has_dhan,
            "kite":    cfg.has_kite,
            "shoonya": _has_key("SHOONYA_USER_ID"),
        },
        "notifications": {
            "telegram": _has_key("TELEGRAM_BOT_TOKEN"),
            "email":    _has_key("RESEND_API_KEY"),
        },
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


# ── Paper Execution Config ─────────────────────────────────────────────────────

_PAPER_DEFAULTS = {
    "enabled":            True,
    "capital":            500_000,
    "max_open_trades":    20,
    "trade_amount":       25_000,
    "min_confidence":     60,
    "auto_exit_target":   True,
    "auto_exit_sl":       True,
    "fill_mode":          "cmp",       # "cmp" = current market price at scan time
    "check_exits_every":  30,          # minutes
    "strategies": ["vcp", "breakout", "golden_cross", "multibagger", "ipo_base", "rocket_base", "rsi_reversal"],
}

_LIVE_DEFAULTS = {
    "enabled":            False,       # ENABLE_LIVE_TRADING=false default
    "broker":             "dhan",
    "capital":            1_000_000,
    "max_open_trades":    10,
    "trade_amount":       50_000,
    "min_confidence":     80,
    "risk_pct_per_trade": 2.0,
    "kill_drawdown":      10.0,
    "require_confirmation": True,
    "strategies": ["vcp", "breakout"],
}


@router.get("/paper-config")
async def get_paper_config():
    """Return paper trading execution configuration."""
    cfg = dict(_PAPER_DEFAULTS)
    try:
        from data.storage import supabase_db as sdb
        import json
        rows = sdb.select("app_config", cols="value", filters={"key": "paper_config"}, limit=1)
        if rows:
            stored = rows[0].get("value") or {}
            if isinstance(stored, str):
                stored = json.loads(stored)
            cfg.update(stored)
    except Exception:
        pass
    return cfg


@router.put("/paper-config")
async def update_paper_config(body: dict, _: None = Depends(require_internal_key)):
    """Persist paper trading execution config."""
    ALLOWED = {
        "enabled", "capital", "max_open_trades", "trade_amount", "min_confidence",
        "auto_exit_target", "auto_exit_sl", "fill_mode", "check_exits_every", "strategies",
    }
    update = {k: v for k, v in body.items() if k in ALLOWED}
    try:
        from data.storage import supabase_db as sdb
        existing = sdb.select("app_config", cols="key", filters={"key": "paper_config"}, limit=1)
        if existing:
            sdb.update("app_config", {"value": update}, {"key": "paper_config"})
        else:
            sdb.insert("app_config", {"key": "paper_config", "value": update})
        return {"ok": True, "saved": update}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/live-config")
async def get_live_config():
    """Return live trading execution configuration."""
    env_enabled = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
    cfg = {**_LIVE_DEFAULTS, "enabled": env_enabled}
    try:
        from data.storage import supabase_db as sdb
        import json
        rows = sdb.select("app_config", cols="value", filters={"key": "live_config"}, limit=1)
        if rows:
            stored = rows[0].get("value") or {}
            if isinstance(stored, str):
                stored = json.loads(stored)
            cfg.update(stored)
    except Exception:
        pass
    # env var always wins on enabled flag — prevent accidental DB override
    cfg["enabled"] = env_enabled
    return cfg


@router.put("/live-config")
async def update_live_config(body: dict, _: None = Depends(require_internal_key)):
    """Persist live trading execution config. Cannot override ENABLE_LIVE_TRADING env var."""
    ALLOWED = {
        "broker", "capital", "max_open_trades", "trade_amount", "min_confidence",
        "risk_pct_per_trade", "kill_drawdown", "require_confirmation", "strategies",
    }
    update = {k: v for k, v in body.items() if k in ALLOWED}
    # Never let the API enable live trading — that must come from env var
    update.pop("enabled", None)
    try:
        from data.storage import supabase_db as sdb
        existing = sdb.select("app_config", cols="key", filters={"key": "live_config"}, limit=1)
        if existing:
            sdb.update("app_config", {"value": update}, {"key": "live_config"})
        else:
            sdb.insert("app_config", {"key": "live_config", "value": update})
        return {"ok": True, "saved": update}
    except Exception as e:
        return {"ok": False, "error": str(e)}
