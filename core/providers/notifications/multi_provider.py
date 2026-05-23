"""Multi-channel notification provider.

Sends to all configured channels.  Falls back to the next channel if one
fails.  Activate with NOTIFY_PROVIDER=both.
"""
from __future__ import annotations

from typing import Any

from core.providers.base import NotificationProvider


class MultiNotificationProvider(NotificationProvider):
    """Tries Telegram first, email second; always tries both on error."""

    def __init__(self) -> None:
        from core.providers.notifications.telegram_provider import TelegramProvider
        from core.providers.notifications.email_provider import EmailProvider
        self._providers = [
            p for p in [TelegramProvider(), EmailProvider()]
            if p.is_configured()
        ]

    def send(
        self,
        message: str,
        title: str = "",
        level: str = "info",
        **kwargs: Any,
    ) -> bool:
        results = [p.send(message, title, level, **kwargs) for p in self._providers]
        return any(results)

    def is_configured(self) -> bool:
        return bool(self._providers)

    def name(self) -> str:
        names = "+".join(p.name() for p in self._providers)
        return f"multi({names})"
