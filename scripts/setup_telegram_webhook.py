"""
One-time script: register the Telegram webhook URL.

Usage (run once after deploying to Vercel):
  python scripts/setup_telegram_webhook.py

Or call the live endpoint manually:
  curl https://onepiece-labs.vercel.app/api/telegram/setup
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "8632500920:AAE0anjkFiYDsm1-g3dU3JF3Y_GLbZC1tm8")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://luffy-labs.vercel.app/api/telegram")


def _tg(method: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    print(f"Setting webhook → {WEBHOOK_URL}")
    result = _tg("setWebhook", {
        "url":                  WEBHOOK_URL,
        "allowed_updates":      ["message", "callback_query"],
        "drop_pending_updates": True,
    })
    print(f"Response: {result}")

    info = _tg("getWebhookInfo", {})
    print(f"\nWebhook info:")
    print(f"  url:             {info.get('result', {}).get('url')}")
    print(f"  pending_updates: {info.get('result', {}).get('pending_update_count')}")
    print(f"  last_error:      {info.get('result', {}).get('last_error_message', 'none')}")


if __name__ == "__main__":
    main()
