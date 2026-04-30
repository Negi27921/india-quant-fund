"""
Research Agent — weekly strategy improvement and market regime analysis.
Generates a Markdown research memo saved to reports/research_<date>.md.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from agents.base import BaseAgent, BaseLLMClient
from data.storage.db import db
from monitoring.audit import AuditLogger


RESEARCH_TEMPLATE = """
You are a quantitative researcher at a top-tier hedge fund focused on Indian equities.

## Weekly Research Memo — {date}

### Input Data

**Strategy Performance (last 63 days)**
{perf_table}

**Signal Hit Rate by Strategy**
{hit_rate_table}

**Recent Market Regime**
- Nifty 50 return (1M): {nifty_1m:.1f}%
- Nifty VIX (latest): {vix:.1f}
- FII flows (5d net): {fii_flows}

### Your Task

Write a 400-600 word research memo covering:
1. Which strategies are underperforming and why (cite specific metrics)
2. Regime assessment: risk-on, risk-off, or transitional
3. One concrete parameter tweak to improve the weakest strategy
4. Recommended allocation adjustment (% change per strategy)
5. Risks to monitor in the next week

Keep language precise and quantitative. Use INR crore notation for flows.
Format as Markdown with clear section headers.
"""


@dataclass
class ResearchMemo:
    date: date
    content: str
    strategies_reviewed: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    file_path: Path = field(default_factory=lambda: Path("reports"))


class ResearchAgent(BaseAgent):
    """
    Weekly research agent — runs every Saturday, saves a Markdown memo.
    Falls back to a structured template if LLM unavailable.
    """

    def __init__(self):
        self.llm = BaseLLMClient()

    def generate_weekly_memo(self) -> ResearchMemo:
        today = date.today()

        # Gather context from DB
        perf_df = self._load_strategy_perf()
        hit_rate_df = self._load_signal_hit_rates()
        regime_data = self._load_regime_data()

        # Build prompt
        prompt = RESEARCH_TEMPLATE.format(
            date=today.isoformat(),
            perf_table=perf_df.to_markdown(index=False) if not perf_df.empty else "No data",
            hit_rate_table=hit_rate_df.to_markdown(index=False) if not hit_rate_df.empty else "No data",
            nifty_1m=regime_data.get("nifty_1m", 0),
            vix=regime_data.get("vix", 20),
            fii_flows=regime_data.get("fii_flows", "N/A"),
        )

        try:
            content = self.llm.complete(prompt)
        except Exception as e:
            content = self._fallback_memo(perf_df, regime_data, str(e))

        # Save to disk
        out_dir = Path("reports")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"research_{today.isoformat()}.md"
        out_path.write_text(content)

        strategies = list(perf_df["strategy"].values) if not perf_df.empty else []
        AuditLogger.log("RESEARCH_AGENT", "weekly", "memo_generated", payload={
            "date": today.isoformat(),
            "strategies": strategies,
        })

        return ResearchMemo(
            date=today,
            content=content,
            strategies_reviewed=strategies,
            file_path=out_path,
        )

    def _load_strategy_perf(self) -> pd.DataFrame:
        try:
            return db.query_df("""
                SELECT strategy, sharpe_ratio, total_return, max_drawdown, win_rate, num_trades
                FROM backtest_results
                WHERE run_date >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY sharpe_ratio DESC
            """)
        except Exception:
            return pd.DataFrame()

    def _load_signal_hit_rates(self) -> pd.DataFrame:
        try:
            return db.query_df("""
                SELECT strategy,
                    COUNT(*) as total_signals,
                    SUM(CASE WHEN approved THEN 1 ELSE 0 END) as approved,
                    ROUND(AVG(CASE WHEN approved THEN 1.0 ELSE 0 END) * 100, 1) as approval_rate_pct
                FROM signals
                WHERE date >= CURRENT_DATE - INTERVAL '63 days'
                GROUP BY strategy
                ORDER BY approval_rate_pct DESC
            """)
        except Exception:
            return pd.DataFrame()

    def _load_regime_data(self) -> dict:
        try:
            row = db.query_df("""
                SELECT benchmark_ret, vix
                FROM daily_pnl
                ORDER BY date DESC
                LIMIT 21
            """)
            if row.empty:
                return {}
            return {
                "nifty_1m": float(row["benchmark_ret"].sum()),
                "vix": float(row["vix"].iloc[0]) if "vix" in row.columns else 20.0,
                "fii_flows": "Data unavailable",
            }
        except Exception:
            return {}

    def _fallback_memo(self, perf_df: pd.DataFrame, regime: dict, error: str) -> str:
        lines = [
            f"# Weekly Research Memo — {date.today().isoformat()}",
            "",
            "> Note: LLM unavailable — auto-generated summary",
            f"> Error: {error[:120]}",
            "",
            "## Strategy Performance",
        ]
        if not perf_df.empty:
            lines.append(perf_df.to_markdown(index=False))
        else:
            lines.append("No backtest data available.")

        lines += [
            "",
            "## Regime",
            f"- Nifty 1M return: {regime.get('nifty_1m', 'N/A')}%",
            f"- VIX: {regime.get('vix', 'N/A')}",
            "",
            "## Recommendations",
            "- Review parameter configurations manually",
            "- Check for data quality issues if signals are sparse",
        ]
        return "\n".join(lines)
