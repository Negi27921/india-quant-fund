"""Kill switch — global trading halt with automatic flatten."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from risk.limits import RiskLimits

_HALT_FILE = Path(".kill_switch_active")


class KillSwitch:
    """
    When triggered:
    1. Writes halt file to disk (survives restarts)
    2. Calls all registered flatten callbacks
    3. Sends critical alerts
    4. Blocks all further order submissions
    """

    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self._triggered: bool = _HALT_FILE.exists()
        self._triggered_at: datetime | None = None
        self._reason: str = ""
        self._flatten_callbacks: list[Callable] = []
        self._alert_callbacks: list[Callable] = []

    def register_flatten_callback(self, cb: Callable) -> None:
        self._flatten_callbacks.append(cb)

    def register_alert_callback(self, cb: Callable) -> None:
        self._alert_callbacks.append(cb)

    def trigger(self, reason: str = "Unknown") -> None:
        if self._triggered:
            return  # Already triggered

        self._triggered = True
        self._triggered_at = datetime.now()
        self._reason = reason

        # Write halt file
        _HALT_FILE.write_text(
            f"triggered={self._triggered_at.isoformat()}\nreason={reason}\n"
        )

        logger.critical(f"🚨 KILL SWITCH TRIGGERED: {reason}")

        # Execute flatten callbacks
        for cb in self._flatten_callbacks:
            try:
                cb()
                logger.info(f"Flatten callback executed: {cb.__name__}")
            except Exception as e:
                logger.error(f"Flatten callback failed: {e}")

        # Send alerts
        for cb in self._alert_callbacks:
            try:
                cb(f"KILL SWITCH: {reason}")
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def reset(self, reason: str = "Manual reset") -> None:
        """Reset kill switch — requires explicit manual action."""
        if _HALT_FILE.exists():
            _HALT_FILE.unlink()
        self._triggered = False
        self._triggered_at = None
        self._reason = ""
        logger.warning(f"Kill switch RESET: {reason}")

    def is_triggered(self) -> bool:
        # Double check file (handles restarts)
        if not self._triggered and _HALT_FILE.exists():
            self._triggered = True
        return self._triggered

    def status(self) -> dict:
        return {
            "triggered": self._triggered,
            "triggered_at": self._triggered_at.isoformat() if self._triggered_at else None,
            "reason": self._reason,
        }

    def check_and_trigger_if_needed(
        self,
        drawdown_pct: float,
        daily_loss_pct: float,
        consecutive_failures: int = 0,
    ) -> bool:
        limits = self.limits.kill_switch
        if abs(drawdown_pct) >= limits.drawdown_pct:
            self.trigger(f"Drawdown {drawdown_pct:.1f}% exceeded limit {limits.drawdown_pct}%")
            return True
        if abs(daily_loss_pct) >= limits.daily_loss_pct:
            self.trigger(f"Daily loss {daily_loss_pct:.1f}% exceeded limit {limits.daily_loss_pct}%")
            return True
        if consecutive_failures >= limits.consecutive_failed_orders:
            self.trigger(f"{consecutive_failures} consecutive order failures")
            return True
        return False
