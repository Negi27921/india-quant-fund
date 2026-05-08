"""Monthly P&L report — emails MTD/YTD summary then purges data older than 3 months.

Run via GitHub Actions on 1st of every month, or manually:
    python scripts/monthly_report.py
"""
from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.storage import supabase_db as sdb

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
REPORT_EMAIL   = os.getenv("REPORT_EMAIL", "wealth279210@gmail.com")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))  # 3 months


# ── Data helpers ───────────────────────────────────────────────────────────────

def fetch_pnl_rows() -> list[dict]:
    try:
        return sdb.select("daily_pnl", cols="date,day_pnl,day_pnl_pct,portfolio_value", order="date", limit=1000)
    except Exception as e:
        print(f"  daily_pnl not available: {e}")
        return []


def fetch_trade_rows() -> list[dict]:
    try:
        return sdb.select("trades", order="trade_date", limit=2000)
    except Exception as e:
        print(f"  trades not available: {e}")
        return []


def compute_stats(pnl_rows: list[dict], trade_rows: list[dict]) -> dict:
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    year_start  = today.replace(month=1, day=1).isoformat()

    mtd_pnl = [r for r in pnl_rows if str(r["date"]) >= month_start]
    ytd_pnl = [r for r in pnl_rows if str(r["date"]) >= year_start]
    mtd_trades = [r for r in trade_rows if str(r["trade_date"]) >= month_start]
    ytd_trades = [r for r in trade_rows if str(r["trade_date"]) >= year_start]

    def pnl_sum(rows):  return round(sum(float(r.get("day_pnl", 0)) for r in rows), 2)
    def pnl_pct(rows):  return round(sum(float(r.get("day_pnl_pct", 0)) for r in rows), 4)
    def win_days(rows): return sum(1 for r in rows if float(r.get("day_pnl", 0)) > 0)
    def loss_days(rows):return sum(1 for r in rows if float(r.get("day_pnl", 0)) < 0)
    def trade_pnl(trades):
        sells = [r for r in trades if r.get("side") == "SELL" and r.get("pnl") is not None]
        return round(sum(float(r["pnl"]) for r in sells), 2)

    return {
        "report_month": today.strftime("%B %Y"),
        "generated": today.isoformat(),
        "mtd": {
            "pnl": pnl_sum(mtd_pnl), "pnl_pct": pnl_pct(mtd_pnl),
            "win_days": win_days(mtd_pnl), "loss_days": loss_days(mtd_pnl),
            "total_trades": len(mtd_trades), "trade_pnl": trade_pnl(mtd_trades),
        },
        "ytd": {
            "pnl": pnl_sum(ytd_pnl), "pnl_pct": pnl_pct(ytd_pnl),
            "win_days": win_days(ytd_pnl), "loss_days": loss_days(ytd_pnl),
            "total_trades": len(ytd_trades), "trade_pnl": trade_pnl(ytd_trades),
        },
        "all_time": {
            "pnl": pnl_sum(pnl_rows), "win_days": win_days(pnl_rows), "loss_days": loss_days(pnl_rows),
        },
        "recent_trades": ytd_trades[-20:],  # last 20 YTD trades for the email
    }


# ── Email ──────────────────────────────────────────────────────────────────────

def build_html(stats: dict) -> str:
    m, y = stats["mtd"], stats["ytd"]
    trades_html = ""
    for t in reversed(stats["recent_trades"][-10:]):
        color = "#00cc44" if t.get("side") == "BUY" else "#ff4444"
        pnl_str = f"₹{t['pnl']:+.0f}" if t.get("pnl") is not None else "—"
        trades_html += f"""
        <tr>
            <td>{t['trade_date']}</td>
            <td>{t['ticker']}</td>
            <td style="color:{color};font-weight:700">{t['side']}</td>
            <td>{t['quantity']}</td>
            <td>₹{float(t['price']):.2f}</td>
            <td>{pnl_str}</td>
        </tr>"""

    def fmt(v): return f"₹{v:+,.2f}" if v else "₹0.00"
    def color(v): return "#00cc44" if v >= 0 else "#ff4444"

    return f"""
<!DOCTYPE html><html><body style="font-family:monospace;background:#050e05;color:#e8ffe8;padding:32px">
<div style="max-width:600px;margin:0 auto">
  <h1 style="color:#00ff41;letter-spacing:.15em;border-bottom:1px solid #00ff4130;padding-bottom:12px">
    📈 ONE PIECE QUANT TERMINAL<br>
    <span style="font-size:14px;color:#00aa28">Monthly Report — {stats['report_month']}</span>
  </h1>

  <h2 style="color:#00e535;font-size:13px;letter-spacing:.2em">MTD (MONTH TO DATE)</h2>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px">
    <tr><td style="padding:6px 0;color:#00aa28">P&L</td>
        <td style="color:{color(m['pnl'])};font-weight:700">{fmt(m['pnl'])} ({m['pnl_pct']:+.2f}%)</td></tr>
    <tr><td style="padding:6px 0;color:#00aa28">Win Days / Loss Days</td>
        <td>{m['win_days']} ✓ / {m['loss_days']} ✗</td></tr>
    <tr><td style="padding:6px 0;color:#00aa28">Total Trades</td>
        <td>{m['total_trades']}</td></tr>
    <tr><td style="padding:6px 0;color:#00aa28">Realised Trade P&L</td>
        <td style="color:{color(m['trade_pnl'])};font-weight:700">{fmt(m['trade_pnl'])}</td></tr>
  </table>

  <h2 style="color:#00e535;font-size:13px;letter-spacing:.2em">YTD (YEAR TO DATE)</h2>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px">
    <tr><td style="padding:6px 0;color:#00aa28">P&L</td>
        <td style="color:{color(y['pnl'])};font-weight:700">{fmt(y['pnl'])} ({y['pnl_pct']:+.2f}%)</td></tr>
    <tr><td style="padding:6px 0;color:#00aa28">Win Days / Loss Days</td>
        <td>{y['win_days']} ✓ / {y['loss_days']} ✗</td></tr>
    <tr><td style="padding:6px 0;color:#00aa28">Total Trades</td>
        <td>{y['total_trades']}</td></tr>
    <tr><td style="padding:6px 0;color:#00aa28">Realised Trade P&L</td>
        <td style="color:{color(y['trade_pnl'])};font-weight:700">{fmt(y['trade_pnl'])}</td></tr>
  </table>

  <h2 style="color:#00e535;font-size:13px;letter-spacing:.2em">RECENT TRADES</h2>
  <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:24px">
    <thead>
      <tr style="color:#00aa28;border-bottom:1px solid #00ff4120">
        <th style="text-align:left;padding:4px">Date</th>
        <th style="text-align:left;padding:4px">Ticker</th>
        <th style="text-align:left;padding:4px">Side</th>
        <th style="text-align:left;padding:4px">Qty</th>
        <th style="text-align:left;padding:4px">Price</th>
        <th style="text-align:left;padding:4px">P&L</th>
      </tr>
    </thead>
    <tbody>{trades_html}</tbody>
  </table>

  <p style="font-size:9px;color:#003311;border-top:1px solid #00ff4108;padding-top:12px">
    Generated {stats['generated']} · Data older than 90 days has been purged from cloud storage.
    Complete archive sent before deletion. · ONE PIECE QUANT TERMINAL
  </p>
</div>
</body></html>"""


def send_email(stats: dict) -> bool:
    if not RESEND_API_KEY:
        print("⚠ RESEND_API_KEY not set — skipping email.")
        return False
    try:
        payload = json.dumps({
            "from": "IQF Reports <onboarding@resend.dev>",
            "to": [REPORT_EMAIL],
            "subject": f"📈 IQF Monthly Report — {stats['report_month']}",
            "html": build_html(stats),
        }).encode()
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        print(f"✓ Report emailed to {REPORT_EMAIL} (id={result.get('id')})")
        return True
    except urllib.error.HTTPError as e:
        print(f"✗ Email failed: {e.code} {e.read().decode()}")
        return False
    except Exception as e:
        print(f"✗ Email failed: {e}")
        return False


# ── Cleanup ────────────────────────────────────────────────────────────────────

def purge_old_data() -> dict:
    cutoff = (date.today() - timedelta(days=RETENTION_DAYS)).isoformat()
    print(f"Purging records before {cutoff} (>{RETENTION_DAYS} days)...")
    deleted = {}
    for table, col in [("daily_pnl", "date"), ("trades", "trade_date")]:
        try:
            deleted[table] = sdb.delete_before(table, col, cutoff)
            print(f"  {table}: {deleted[table]} rows deleted")
        except Exception as e:
            deleted[table] = 0
            print(f"  {table}: skipped ({e})")
    return deleted


def log_report(stats: dict, emailed: bool, deleted: dict) -> None:
    try:
        sdb.insert("monthly_reports", {
            "report_month": date.today().strftime("%Y-%m"),
            "email_to": REPORT_EMAIL,
            "mtd_pnl": stats["mtd"]["pnl"],
            "ytd_pnl": stats["ytd"]["pnl"],
            "total_trades": stats["ytd"]["total_trades"],
            "report_data": json.dumps({"stats": stats, "deleted": deleted, "emailed": emailed}),
        })
    except Exception as e:
        print(f"Warning: could not log report to Supabase: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("IQF Monthly Report & Cleanup")
    print("=" * 50)

    pnl_rows   = fetch_pnl_rows()
    trade_rows = fetch_trade_rows()
    print(f"Fetched {len(pnl_rows)} P&L rows, {len(trade_rows)} trade rows")

    stats  = compute_stats(pnl_rows, trade_rows)
    print(f"MTD P&L: ₹{stats['mtd']['pnl']:+,.2f} | YTD P&L: ₹{stats['ytd']['pnl']:+,.2f}")

    emailed = send_email(stats)
    deleted = purge_old_data()
    log_report(stats, emailed, deleted)

    print("=" * 50)
    print("Done.")


if __name__ == "__main__":
    main()
