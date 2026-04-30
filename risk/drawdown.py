"""Real-time drawdown monitor."""
from __future__ import annotations

from collections import deque
from datetime import date

from loguru import logger

from risk.limits import RiskLimits


class DrawdownMonitor:
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self._peak_value: float = 0.0
        self._current_value: float = 0.0
        self._daily_pnl: deque[float] = deque(maxlen=30)
        self._current_day_pnl: float = 0.0
        self._last_date: date = date.today()

    def update(self, portfolio_value: float, peak_value: float | None = None) -> None:
        self._current_value = portfolio_value
        if peak_value is not None:
            self._peak_value = peak_value
        elif portfolio_value > self._peak_value:
            self._peak_value = portfolio_value

    def update_pnl(self, pnl: float) -> None:
        today = date.today()
        if today != self._last_date:
            self._daily_pnl.append(self._current_day_pnl)
            self._current_day_pnl = 0.0
            self._last_date = today
        self._current_day_pnl += pnl

    @property
    def current_drawdown_pct(self) -> float:
        if self._peak_value <= 0:
            return 0.0
        return (self._current_value - self._peak_value) / self._peak_value * 100

    @property
    def daily_loss_pct(self) -> float:
        if self._peak_value <= 0:
            return 0.0
        return min(0, self._current_day_pnl / self._peak_value * 100)

    @property
    def consecutive_loss_days(self) -> int:
        count = 0
        for pnl in reversed(list(self._daily_pnl)):
            if pnl < 0:
                count += 1
            else:
                break
        return count

    def check_can_trade(self, side: str = "BUY") -> tuple[bool, str]:
        dd = self.current_drawdown_pct
        daily_loss = abs(self.daily_loss_pct)
        limits = self.limits.drawdown

        if side == "BUY":
            if abs(dd) >= limits.drawdown_reduce_pct:
                return False, f"Drawdown {dd:.1f}% at reduce threshold — no new longs"
            if daily_loss >= limits.daily_loss_limit_pct:
                return False, f"Daily loss {daily_loss:.1f}% at limit {limits.daily_loss_limit_pct}%"

        if abs(dd) >= limits.drawdown_kill_switch_pct:
            return False, f"Drawdown {dd:.1f}% at kill switch threshold"

        return True, ""

    def should_kill_switch(self) -> bool:
        return abs(self.current_drawdown_pct) >= self.limits.drawdown.drawdown_kill_switch_pct

    def should_alert(self) -> bool:
        return abs(self.current_drawdown_pct) >= self.limits.drawdown.drawdown_alert_pct

    def status(self) -> dict:
        return {
            "current_drawdown_pct": round(self.current_drawdown_pct, 2),
            "daily_loss_pct": round(self.daily_loss_pct, 2),
            "consecutive_loss_days": self.consecutive_loss_days,
            "peak_value": round(self._peak_value, 2),
            "current_value": round(self._current_value, 2),
        }
