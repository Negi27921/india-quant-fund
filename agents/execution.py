"""
Execution Agent — determines optimal order type, timing, and size adjustments
before orders are dispatched to the SmartOrderRouter.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from agents.base import BaseAgent, BaseLLMClient
from monitoring.audit import AuditLogger


class OrderParameters(BaseModel):
    ticker: str
    recommended_order_type: Literal["LIMIT", "MARKET"] = "LIMIT"
    limit_price_offset_pct: float = Field(
        default=0.1,
        description="Place limit this % from CMP (buy above, sell below)"
    )
    size_scale: float = Field(
        default=1.0,
        ge=0.1,
        le=1.0,
        description="Scale factor applied to computed quantity (0.1-1.0)"
    )
    reasoning: str = ""
    urgency: Literal["low", "medium", "high"] = "medium"


class ExecutionAgent(BaseAgent):
    """
    Decides order execution parameters given market microstructure context.

    Rule-based fallback:
    - Low liquidity (ADV < ₹50Cr): LIMIT, 0.15% offset, scale 0.7
    - Normal: LIMIT, 0.1% offset, scale 1.0
    - High urgency signals (event strategy): MARKET for sell, LIMIT for buy
    """

    def __init__(self):
        self.llm = BaseLLMClient()

    def get_order_params(
        self,
        ticker: str,
        side: str,
        signal_strength: float,
        adv_crore: float,
        strategy: str,
        vix: float | None = None,
        use_llm: bool = False,  # default off — rule-based is faster & cheaper
    ) -> OrderParameters:

        if use_llm:
            try:
                return self._llm_params(ticker, side, signal_strength, adv_crore, strategy, vix)
            except Exception:
                pass  # fall through to rules

        return self._rule_based_params(ticker, side, signal_strength, adv_crore, strategy, vix)

    def _rule_based_params(
        self,
        ticker: str,
        side: str,
        signal_strength: float,
        adv_crore: float,
        strategy: str,
        vix: float | None,
    ) -> OrderParameters:
        # Urgency: event strategy is highest urgency
        urgency = "high" if strategy == "event" else "medium" if signal_strength > 1.5 else "low"

        # Order type: market only for urgent sells in event strategy
        order_type: Literal["LIMIT", "MARKET"] = "LIMIT"
        if urgency == "high" and side == "SELL":
            order_type = "MARKET"

        # Offset: wider for illiquid stocks
        offset = 0.15 if adv_crore < 50 else 0.1

        # Size scale: reduce in high VIX or low liquidity
        scale = 1.0
        if vix and vix > 25:
            scale = max(0.5, 1.0 - (vix - 25) / 20)
        if adv_crore < 20:
            scale = min(scale, 0.7)

        return OrderParameters(
            ticker=ticker,
            recommended_order_type=order_type,
            limit_price_offset_pct=offset,
            size_scale=round(scale, 2),
            urgency=urgency,
            reasoning=f"Rule-based: ADV={adv_crore:.1f}Cr, VIX={vix}, strategy={strategy}",
        )

    def _llm_params(
        self,
        ticker: str,
        side: str,
        signal_strength: float,
        adv_crore: float,
        strategy: str,
        vix: float | None,
    ) -> OrderParameters:
        prompt = f"""
You are an execution specialist for Indian equity markets (NSE cash segment).

Order context:
- Ticker: {ticker}
- Side: {side}
- Strategy: {strategy}
- Signal strength: {signal_strength:.2f} (higher = stronger conviction)
- 10-day ADV: ₹{adv_crore:.1f} Cr
- VIX: {vix if vix else 'unknown'}

Decide the optimal execution parameters. Return JSON matching the schema.
"""
        result = self.llm.complete_json(prompt, OrderParameters)
        AuditLogger.log("EXECUTION_AGENT", "llm", "order_params", payload={
            "ticker": ticker, "side": side,
        })
        return result
