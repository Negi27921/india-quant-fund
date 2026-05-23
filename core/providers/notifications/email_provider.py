"""Email notification provider (via Resend API)."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from core.providers.base import NotificationProvider


class EmailProvider(NotificationProvider):
    _API = "https://api.resend.com/emails"

    def __init__(self) -> None:
        self._key   = os.getenv("RESEND_API_KEY", "")
        self._to    = os.getenv("REPORT_EMAIL", "")
        self._from  = os.getenv("EMAIL_FROM", "One Piece Quant <onboarding@resend.dev>")

    def is_configured(self) -> bool:
        return bool(self._key and self._to)

    def send(
        self,
        message: str,
        title: str = "One Piece Quant Alert",
        level: str = "info",
        html: str | None = None,
        to: str | None = None,
        **kwargs: Any,
    ) -> bool:
        if not self.is_configured():
            return False
        subject = f"[{level.upper()}] {title}" if level != "info" else title
        payload = {
            "from":    self._from,
            "to":      [to or self._to],
            "subject": subject,
            "html":    html or f"<pre>{message}</pre>",
        }
        try:
            req = urllib.request.Request(
                self._API,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type":  "application/json",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception:
            return False

    def name(self) -> str:
        return "email"
