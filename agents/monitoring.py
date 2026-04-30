"""Monitoring agent — continuous watchdog during market hours."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agents.base import BaseAgent
from risk.limits import get_limits


class MonitorAlert(BaseModel):
    level: str
    message: str
    action: str


class MonitorOutput(BaseModel):
    status: str
    alerts: list[MonitorAlert]
    trigger_kill_switch: bool
    positions_to_exit: list[str]


class MonitoringAgent(BaseAgent):
    name = "monitoring"
    model = "gemini-2.0-flash"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        limits = get_limits()
        portfolio_value = context.get("portfolio_value", 0)
        peak_value = context.get("peak_value", portfolio_value)
        drawdown_pct = context.get("drawdown_pct", 0)
        day_pnl_pct = context.get("day_pnl_pct", 0)
        vix = context.get("vix", 15)
        positions = context.get("positions", [])
        broker_latency_ms = context.get("broker_latency_ms", 100)
        data_lag_minutes = context.get("data_lag_minutes", 0)

        # Hard-coded kill switch check (no LLM needed for this)
        if abs(drawdown_pct) >= limits.drawdown.drawdown_kill_switch_pct:
            return {
                "status": "critical",
                "alerts": [{
                    "level": "critical",
                    "message": f"Drawdown {drawdown_pct:.1f}% reached kill switch threshold {limits.drawdown.drawdown_kill_switch_pct}%",
                    "action": "kill_switch",
                }],
                "trigger_kill_switch": True,
                "positions_to_exit": [],
            }

        user_msg = f"""
Current fund status:
- Portfolio value: ₹{portfolio_value:,.0f}
- Drawdown from peak: {drawdown_pct:.2f}%
- Day PnL: {day_pnl_pct:.2f}%
- India VIX: {vix:.1f}
- Broker API latency: {broker_latency_ms}ms
- Data feed lag: {data_lag_minutes} minutes

Active positions ({len(positions)}):
{positions[:10]}

Risk limits:
- Drawdown alert: {limits.drawdown.drawdown_alert_pct}%
- Kill switch: {limits.drawdown.drawdown_kill_switch_pct}%
- Daily loss limit: {limits.drawdown.daily_loss_limit_pct}%

Analyze and report system status. Flag any anomalies.
"""
        result = self._call_llm_json(user_msg, MonitorOutput)

        if result is None:
            # Rule-based fallback
            alerts = []
            kill = False
            if abs(drawdown_pct) >= limits.drawdown.drawdown_alert_pct:
                alerts.append({"level": "warning", "message": f"Drawdown {drawdown_pct:.1f}%", "action": "monitor"})
            if abs(day_pnl_pct) >= limits.drawdown.daily_loss_limit_pct:
                alerts.append({"level": "critical", "message": f"Daily loss {day_pnl_pct:.1f}%", "action": "halt_buys"})
            if broker_latency_ms > 3000:
                alerts.append({"level": "warning", "message": "Broker latency high", "action": "monitor"})
            return {
                "status": "warning" if alerts else "ok",
                "alerts": alerts,
                "trigger_kill_switch": kill,
                "positions_to_exit": [],
            }

        return result.model_dump()
