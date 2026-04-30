"""Signal agent — LLM sanity check on quantitative signals."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agents.base import BaseAgent


class SignalApproval(BaseModel):
    approved_tickers: list[str]
    rejected: list[dict]     # [{ticker, reason}]
    warnings: list[str]


class SignalAgent(BaseAgent):
    name = "signal"
    model = "deepseek-chat"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        signals = context.get("signals", {})
        news = context.get("news_headlines", [])
        earnings_calendar = context.get("earnings_calendar", [])
        circuit_stocks = context.get("circuit_stocks", [])
        fno_ban = context.get("fno_ban_stocks", [])

        if not signals:
            return {"approved_tickers": [], "rejected": [], "warnings": []}

        user_msg = f"""
Quantitative signal engine generated signals for these stocks:
{list(signals.keys())}

Recent news headlines (last 24h):
{news[:10]}

Earnings announcements in next 2 days (hold-off rule):
{earnings_calendar}

Stocks in circuit limit today (DO NOT trade):
{circuit_stocks}

Stocks in F&O ban period (avoid if possible):
{fno_ban}

Review each signal ticker and:
1. REJECT if: earnings in next 2 days, in circuit limit, major negative news
2. WARN if: F&O ban, high news uncertainty
3. APPROVE all others

Return your review as JSON.
"""
        result = self._call_llm_json(user_msg, SignalApproval)

        if result is None:
            # Fallback: approve everything minus known bad tickers
            bad = set(circuit_stocks) | set(earnings_calendar)
            approved = [t for t in signals.keys() if t not in bad]
            return {
                "approved_tickers": approved,
                "rejected": [{"ticker": t, "reason": "circuit/earnings"} for t in bad if t in signals],
                "warnings": ["Signal agent LLM unavailable — using rule-based fallback"],
            }

        return result.model_dump()
