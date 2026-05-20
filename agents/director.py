"""Director agent — daily regime detection and strategy weight allocation."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agents.base import BaseAgent
from strategies.portfolio.allocator import BASE_ALLOCATION


class DirectorOutput(BaseModel):
    regime: str                           # trending|range_bound|high_vol|risk_off
    risk_posture: str                     # normal|defensive|halt_new_positions
    strategy_weights: dict[str, float]
    position_size_scale: float
    rationale: str


class DirectorAgent(BaseAgent):
    name = "director"
    model = "deepseek-chat"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        pnl_pct = context.get("day_pnl_pct", 0.0)
        drawdown = context.get("drawdown_pct", 0.0)
        vix = context.get("vix_india", 15.0)
        strategy_sharpes = context.get("strategy_sharpes_30d", {})

        user_msg = f"""
Daily context for One Piece:
- Day PnL: {pnl_pct:.2f}%
- Current drawdown from peak: {drawdown:.2f}%
- India VIX: {vix:.1f}
- 30-day rolling Sharpe by strategy: {strategy_sharpes}
- Base allocation: {BASE_ALLOCATION}

Determine today's market regime and optimal strategy weights.
Force risk_off if drawdown > 10%.
"""
        result = self._call_llm_json(user_msg, DirectorOutput)

        if result is None:
            self.log("LLM failed, using base allocation", "warning")
            return {
                "regime": "range_bound",
                "risk_posture": "normal",
                "strategy_weights": BASE_ALLOCATION.copy(),
                "position_size_scale": 1.0,
                "rationale": "Fallback — LLM unavailable",
            }

        # Safety override: never allow new positions if drawdown > 10%
        if abs(drawdown) >= 10.0:
            result.risk_posture = "halt_new_positions"
            result.position_size_scale = 0.0
            self.log("Overriding to halt_new_positions — drawdown >= 10%", "warning")

        # Safety: VIX override
        if vix >= 35:
            result.position_size_scale = 0.0
            result.risk_posture = "risk_off"

        return result.model_dump()
