"""Reporting agent — generates daily/weekly HTML/PDF reports."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from data.storage import db


class ReportingAgent(BaseAgent):
    name = "reporting"
    model = "gemini-2.0-flash"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        report_type = context.get("type", "daily")
        metrics = context.get("metrics", {})
        trades = context.get("trades", [])
        positions = context.get("positions", [])

        if report_type == "daily":
            html = self._generate_daily(metrics, trades, positions)
        else:
            html = self._generate_weekly(metrics, trades, positions)

        # Save report
        out_dir = Path("./reports")
        out_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        report_path = out_dir / f"{report_type}_{date_str}.html"
        report_path.write_text(html)

        # Convert to PDF
        pdf_path = str(report_path).replace(".html", ".pdf")
        try:
            import weasyprint
            weasyprint.HTML(string=html).write_pdf(pdf_path)
        except Exception:
            pass

        return {
            "report_type": report_type,
            "html_path": str(report_path),
            "pdf_path": pdf_path,
            "generated_at": datetime.now().isoformat(),
        }

    def _generate_daily(self, metrics: dict, trades: list, positions: list) -> str:
        user_msg = f"""
Generate a daily fund report HTML for:
- Date: {datetime.now().strftime('%B %d, %Y')}
- Day PnL: ₹{metrics.get('day_pnl', 0):,.0f} ({metrics.get('day_pnl_pct', 0):.2f}%)
- Portfolio Value: ₹{metrics.get('portfolio_value', 0):,.0f}
- Drawdown: {metrics.get('drawdown_pct', 0):.2f}%
- Positions: {len(positions)}
- Trades Today: {len(trades)}
- Best Performer: {metrics.get('best_performer', 'N/A')}
- Worst Performer: {metrics.get('worst_performer', 'N/A')}
- Benchmark (Nifty 500): {metrics.get('benchmark_ret', 0):.2f}%

Generate clean, professional HTML with inline styles. Dark theme (#0A0B0D background).
"""
        html_content = self._call_llm(user_msg)
        if not html_content or not html_content.strip().startswith("<"):
            html_content = self._fallback_daily_html(metrics)
        return html_content

    def _generate_weekly(self, metrics: dict, trades: list, positions: list) -> str:
        user_msg = f"""
Generate a weekly fund performance report HTML for week ending {datetime.now().strftime('%B %d, %Y')}:
- Week Return: {metrics.get('week_return', 0):.2f}%
- Nifty 500 Week Return: {metrics.get('benchmark_week', 0):.2f}%
- Alpha: {metrics.get('alpha', 0):.2f}%
- Win Rate: {metrics.get('win_rate', 0):.1%}
- Profit Factor: {metrics.get('profit_factor', 0):.2f}
- Max Drawdown This Week: {metrics.get('max_dd_week', 0):.2f}%
- Total Trades: {len(trades)}

Generate professional 4-page HTML report. Dark theme.
"""
        html_content = self._call_llm(user_msg)
        if not html_content or not html_content.strip().startswith("<"):
            html_content = self._fallback_weekly_html(metrics)
        return html_content

    def _fallback_daily_html(self, metrics: dict) -> str:
        pnl = metrics.get('day_pnl', 0)
        pnl_pct = metrics.get('day_pnl_pct', 0)
        color = "#10B981" if pnl >= 0 else "#EF4444"
        return f"""<!DOCTYPE html>
<html><head><style>
body{{font-family:Inter,sans-serif;background:#0A0B0D;color:#F9FAFB;padding:2rem;}}
h1{{color:#3B82F6;}} .metric{{background:#111318;padding:1rem;border-radius:8px;margin:0.5rem;}}
</style></head><body>
<h1>Daily Report — {datetime.now().strftime('%B %d, %Y')}</h1>
<div class="metric"><strong>Day PnL:</strong> <span style="color:{color}">₹{pnl:,.0f} ({pnl_pct:+.2f}%)</span></div>
<div class="metric"><strong>Portfolio:</strong> ₹{metrics.get('portfolio_value',0):,.0f}</div>
<div class="metric"><strong>Drawdown:</strong> {metrics.get('drawdown_pct',0):.2f}%</div>
</body></html>"""

    def _fallback_weekly_html(self, metrics: dict) -> str:
        return f"""<!DOCTYPE html>
<html><head><style>body{{font-family:Inter,sans-serif;background:#0A0B0D;color:#F9FAFB;padding:2rem;}}</style></head>
<body><h1>Weekly Report</h1><p>Week Return: {metrics.get('week_return',0):.2f}%</p></body></html>"""
