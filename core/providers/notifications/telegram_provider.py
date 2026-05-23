"""Telegram notification provider."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from core.providers.base import NotificationProvider


class TelegramProvider(NotificationProvider):
    _API = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self) -> None:
        self._token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def is_configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(
        self,
        message: str,
        title: str = "",
        level: str = "info",
        parse_mode: str = "HTML",
        **kwargs: Any,
    ) -> bool:
        if not self.is_configured():
            return False
        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}.get(level, "📢")
        text = f"{emoji} <b>{title}</b>\n{message}" if title else f"{emoji} {message}"
        payload = {
            "chat_id":    self._chat_id,
            "text":       text[:4096],
            "parse_mode": parse_mode,
        }
        try:
            req = urllib.request.Request(
                self._API.format(token=self._token),
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    def name(self) -> str:
        return "telegram"
