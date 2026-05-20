"""Alert system — Telegram + email notifications."""
from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests
from loguru import logger


class AlertManager:
    """Sends alerts via Telegram and email."""

    def __init__(self):
        self._tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
        self._smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self._smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self._smtp_user = os.getenv("SMTP_USER", "")
        self._smtp_pass = os.getenv("SMTP_PASSWORD", "")
        self._alert_email = os.getenv("ALERT_EMAIL", "")

    def send(self, message: str, level: str = "info") -> None:
        """Send alert to all configured channels."""
        prefix = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(level, "📢")
        full_msg = f"{prefix} [One Piece]\n{datetime.now().strftime('%H:%M:%S IST')}\n{message}"
        self._send_telegram(full_msg)
        if level == "critical":
            self._send_email(f"CRITICAL: {message[:60]}", full_msg)

    def send_critical(self, message: str) -> None:
        self.send(message, level="critical")

    def send_warning(self, message: str) -> None:
        self.send(message, level="warning")

    def send_info(self, message: str) -> None:
        self.send(message, level="info")

    def send_report(self, subject: str, html_content: str) -> None:
        self._send_email(subject, html_content, html=True)

    def _send_telegram(self, message: str) -> bool:
        if not self._tg_token or not self._tg_chat:
            logger.debug("Telegram not configured, skipping")
            return False
        try:
            url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": self._tg_chat,
                "text": message[:4096],
                "parse_mode": "HTML",
            }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")
            return False

    def _send_email(self, subject: str, body: str, html: bool = False) -> bool:
        if not self._smtp_user or not self._alert_email:
            logger.debug("Email not configured, skipping")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._smtp_user
            msg["To"] = self._alert_email
            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type))

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._smtp_user, self._smtp_pass)
                smtp.sendmail(self._smtp_user, self._alert_email, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email alert failed: {e}")
            return False


_alerts: Optional[AlertManager] = None


def get_alerts() -> AlertManager:
    global _alerts
    if _alerts is None:
        _alerts = AlertManager()
    return _alerts
