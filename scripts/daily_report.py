"""
Daily Report Agent — One Piece Quant

Runs at 10 PM IST. Compiles a comprehensive daily report:
  • Screener hits per strategy (today)
  • Paper trading P&L (today's exits + open positions)
  • 30-day win rates per strategy
  • Strategy agent insights
  • Tomorrow's top picks (≥95% confidence)

Sends to Telegram + Email. Falls back to the other channel on failure.

Schedule: daily 10 PM IST (4:30 PM UTC) Monday–Friday
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
sys.path.insert(0, str(Path(__file__).parent.parent))

SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY     = os.getenv("SUPABASE_KEY", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
RESEND_API_KEY   = os.getenv("RESEND_API_KEY", "")
REPORT_EMAIL     = os.getenv("REPORT_EMAIL", "negi2950@gmail.com")

STRATEGY_LABELS = {
    "vcp":          "VCP",
    "ipo_base":     "IPO Base",
    "rocket_base":  "Rocket Base",
    "breakout":     "Breakout",
    "rsi_reversal": "RSI Reversal",
    "golden_cross": "Golden Cross",
    "multibagger":  "Multibagger",
    "custom":       "Custom",
}

DASHBOARD_URL = "https://luffy-labs.vercel.app"


# ── Supabase helpers ───────────────────────────────────────────────────────────

def sb_get(table: str, params: str = "") -> list[dict]:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "User-Agent":    "curl/8.4.0",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            r = json.loads(resp.read().decode())
            return r if isinstance(r, list) else []
    except Exception as e:
        print(f"  SB GET {table}: {e}")
        return []


# ── Data gathering ─────────────────────────────────────────────────────────────

def get_screener_hits() -> dict[str, int]:
    """Count screener hits per strategy from today's cache."""
    hits: dict[str, int] = {}
    for strategy in STRATEGY_LABELS:
        rows = sb_get(
            "screener_cache",
            f"strategy=eq.{strategy}&select=results,scanned_at&limit=1",
        )
        if rows:
            raw = rows[0].get("results")
            items = json.loads(raw) if isinstance(raw, str) else (raw or [])
            hits[strategy] = len([i for i in items if i.get("confidence", 0) >= 95])
        else:
            hits[strategy] = 0
    return hits


def get_paper_pnl_today() -> dict:
    """Get today's paper trading P&L stats."""
    today = date.today().isoformat()
    closed = sb_get("paper_trades", f"exit_date=eq.{today}&select=*")
    open_t = sb_get("paper_trades", "status=eq.open&select=*")

    if not closed:
        return {
            "closed_today":  0,
            "wins":          0,
            "losses":        0,
            "total_pnl":     0.0,
            "win_rate":      0.0,
            "open_trades":   len(open_t),
            "open_exposure": sum(float(t.get("trade_amount") or 0) for t in open_t),
        }

    wins    = [t for t in closed if float(t.get("pnl") or 0) > 0]
    losses  = [t for t in closed if float(t.get("pnl") or 0) <= 0]
    total   = sum(float(t.get("pnl") or 0) for t in closed)

    return {
        "closed_today":  len(closed),
        "wins":          len(wins),
        "losses":        len(losses),
        "total_pnl":     round(total, 2),
        "win_rate":      round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "open_trades":   len(open_t),
        "open_exposure": round(sum(float(t.get("trade_amount") or 0) for t in open_t), 2),
        "best_trade":    max(closed, key=lambda x: float(x.get("pnl") or 0), default={}),
        "worst_trade":   min(closed, key=lambda x: float(x.get("pnl") or 0), default={}),
    }


def get_30d_win_rates() -> dict[str, dict]:
    """30-day win rates per strategy."""
    since = (date.today() - timedelta(days=30)).isoformat()
    rows = sb_get("paper_trades", f"entry_date=gte.{since}&status=neq.open&select=strategy,pnl")

    by_s: dict[str, dict] = {}
    for r in rows:
        s = r.get("strategy", "unknown")
        if s not in by_s:
            by_s[s] = {"total": 0, "wins": 0, "pnl": 0.0}
        by_s[s]["total"] += 1
        p = float(r.get("pnl") or 0)
        if p > 0:
            by_s[s]["wins"] += 1
        by_s[s]["pnl"] += p

    return {
        s: {
            "trades":   d["total"],
            "win_rate": round(d["wins"] / d["total"] * 100, 1) if d["total"] else 0,
            "pnl":      round(d["pnl"], 2),
        }
        for s, d in by_s.items()
    }


def get_agent_insights() -> list[dict]:
    """Fetch latest strategy agent insights."""
    return sb_get("strategy_notes", "select=*&order=updated_at.desc&limit=8")


def get_top_picks() -> list[dict]:
    """Get tomorrow's top picks (≥95% conf) across all screeners."""
    picks: list[dict] = []
    for strategy in STRATEGY_LABELS:
        rows = sb_get("screener_cache", f"strategy=eq.{strategy}&select=results&limit=1")
        if rows:
            raw = rows[0].get("results")
            items = json.loads(raw) if isinstance(raw, str) else (raw or [])
            for item in items:
                if item.get("confidence", 0) >= 97:
                    picks.append({
                        "ticker":     item.get("ticker", ""),
                        "strategy":   strategy,
                        "confidence": item.get("confidence", 0),
                        "ltp":        item.get("ltp", 0),
                    })

    picks.sort(key=lambda x: -x["confidence"])
    seen: set[str] = set()
    unique: list[dict] = []
    for p in picks:
        if p["ticker"] not in seen:
            seen.add(p["ticker"])
            unique.append(p)
    return unique[:10]


# ── Telegram report ────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    """Escape special chars for MarkdownV2."""
    for c in r"_*[]()~`>#+-=|{}.!":
        s = s.replace(c, f"\\{c}")
    return s


def build_telegram_report(
    hits: dict[str, int],
    pnl: dict,
    win_rates: dict[str, dict],
    insights: list[dict],
    picks: list[dict],
) -> str:
    today = date.today().strftime("%-d %b %Y")
    lines = [
        "🏴‍☠️ *ONE PIECE QUANT — Daily Report*",
        f"_{_esc(today)} · 10 PM IST_",
        "",
    ]

    # Screener hits
    lines += ["*📊 SCREENER HITS TODAY \\(≥95% conf\\)*", "```"]
    lines.append(f"{'STRATEGY':<15} {'HITS':>5}")
    lines.append("─" * 22)
    total_hits = 0
    for strategy, label in STRATEGY_LABELS.items():
        h = hits.get(strategy, 0)
        total_hits += h
        lines.append(f"{label:<15} {h:>5}")
    lines.append("─" * 22)
    lines.append(f"{'TOTAL':<15} {total_hits:>5}")
    lines.append("```\n")

    # Paper P&L
    lines.append("*💰 PAPER TRADING TODAY*")
    lines.append("```")
    lines.append(f"Exits:     {pnl['closed_today']} trades")
    if pnl["closed_today"] > 0:
        lines.append(f"Wins:      {pnl['wins']} ({pnl['win_rate']:.0f}%)")
        lines.append(f"Losses:    {pnl['losses']}")
        sign = "+" if pnl["total_pnl"] >= 0 else ""
        lines.append(f"Net PNL:   ₹{pnl['total_pnl']:+,.0f}")
    lines.append(f"Open pos:  {pnl['open_trades']} (₹{pnl['open_exposure']:,.0f} exposure)")
    lines.append("```\n")

    # 30-day win rates
    if win_rates:
        lines.append("*📈 30\\-DAY WIN RATES*")
        lines.append("```")
        lines.append(f"{'STRATEGY':<14} {'TRADES':>6} {'WIN%':>5} {'PNL':>10}")
        lines.append("─" * 38)
        for strategy, data in sorted(win_rates.items(), key=lambda x: -x[1]["win_rate"]):
            label = STRATEGY_LABELS.get(strategy, strategy)[:13]
            wr    = data["win_rate"]
            flag  = "✅" if wr >= 60 else ("⚠️" if wr >= 40 else "❌")
            lines.append(
                f"{flag}{label:<13} {data['trades']:>6} {wr:>4.0f}% ₹{data['pnl']:>+8,.0f}"
            )
        lines.append("```\n")

    # Agent insights
    if insights:
        lines.append("*🤖 AGENT INSIGHTS*")
        for ins in insights[:4]:
            strategy = STRATEGY_LABELS.get(ins.get("strategy", ""), ins.get("strategy", ""))
            insight  = ins.get("insight", "")[:80]
            wr       = ins.get("win_rate")
            wr_str   = f" \\({wr:.0f}%\\)" if wr else ""
            lines.append(f"• *{_esc(strategy)}*{wr_str}: {_esc(insight)}")
        lines.append("")

    # Top picks
    if picks:
        lines.append("*🔝 TOP PICKS \\(≥97% CONFIDENCE\\)*")
        lines.append("```")
        lines.append(f"{'TICKER':<10} {'STRATEGY':<14} {'CONF':>5} {'LTP':>8}")
        lines.append("─" * 40)
        for p in picks[:8]:
            label = STRATEGY_LABELS.get(p["strategy"], p["strategy"])[:12]
            lines.append(
                f"{p['ticker']:<10} {label:<14} {p['confidence']:>4}% "
                f"₹{p['ltp']:>6,.0f}"
            )
        lines.append("```\n")

    lines.append(f"[📊 Dashboard]({_esc(DASHBOARD_URL)})  _Not financial advice_")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("  Telegram not configured")
        return False
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            print("  Telegram: sent OK")
            return True
        print(f"  Telegram error: {result.get('description')}")
        return False
    except Exception as e:
        print(f"  Telegram failed: {e}")
        return False


# ── Email report ───────────────────────────────────────────────────────────────

def build_email_html(
    hits: dict[str, int],
    pnl: dict,
    win_rates: dict[str, dict],
    insights: list[dict],
    picks: list[dict],
) -> str:
    today = date.today().strftime("%-d %b %Y")

    def _row(label: str, value: str, color: str = "#c8e8c8") -> str:
        return (
            f'<tr><td style="padding:6px 10px;color:#445544;font-size:11px">{label}</td>'
            f'<td style="padding:6px 10px;color:{color};font-weight:600;font-size:12px">{value}</td></tr>'
        )

    # Screener table
    screener_rows = ""
    for strategy, label in STRATEGY_LABELS.items():
        h = hits.get(strategy, 0)
        color = "#00ff41" if h > 0 else "#334433"
        screener_rows += (
            f'<tr style="border-bottom:1px solid #0a180a">'
            f'<td style="padding:6px 8px;color:#c8e8c8;font-size:11px">{label}</td>'
            f'<td style="padding:6px 8px;color:{color};font-weight:700;font-size:13px;text-align:center">{h}</td>'
            f'</tr>'
        )

    # Win rate table
    wr_rows = ""
    for strategy, data in sorted(win_rates.items(), key=lambda x: -x[1]["win_rate"]):
        label = STRATEGY_LABELS.get(strategy, strategy)
        wr    = data["win_rate"]
        pnl_v = data["pnl"]
        color = "#00ff41" if wr >= 60 else ("#f59e0b" if wr >= 40 else "#ff4444")
        pnl_c = "#00cc88" if pnl_v >= 0 else "#ff4444"
        wr_rows += (
            f'<tr style="border-bottom:1px solid #0a180a">'
            f'<td style="padding:6px 8px;color:#c8e8c8;font-size:11px">{label}</td>'
            f'<td style="padding:6px 8px;text-align:center;font-size:12px;font-weight:700">{data["trades"]}</td>'
            f'<td style="padding:6px 8px;color:{color};font-weight:700;font-size:12px;text-align:center">{wr:.0f}%</td>'
            f'<td style="padding:6px 8px;color:{pnl_c};font-size:12px;text-align:right">₹{pnl_v:+,.0f}</td>'
            f'</tr>'
        )

    # Picks table
    picks_rows = ""
    for p in picks[:8]:
        label = STRATEGY_LABELS.get(p["strategy"], p["strategy"])
        picks_rows += (
            f'<tr style="border-bottom:1px solid #0a180a">'
            f'<td style="padding:6px 8px;color:#00ff41;font-weight:700;font-size:12px">{p["ticker"]}</td>'
            f'<td style="padding:6px 8px;color:#c8e8c8;font-size:11px">{label}</td>'
            f'<td style="padding:6px 8px;color:#f59e0b;font-weight:700;font-size:12px;text-align:center">{p["confidence"]}%</td>'
            f'<td style="padding:6px 8px;color:#c8e8c8;font-size:12px;text-align:right">₹{p["ltp"]:,.0f}</td>'
            f'</tr>'
        )

    # Insights
    insights_html = ""
    for ins in insights[:5]:
        s  = STRATEGY_LABELS.get(ins.get("strategy", ""), ins.get("strategy", ""))
        insight = ins.get("insight", "")
        action  = ins.get("action", "")
        wr      = ins.get("win_rate")
        insights_html += (
            f'<div style="padding:10px 12px;border-left:2px solid #00ff4140;margin-bottom:8px">'
            f'<span style="color:#00ff41;font-weight:700;font-size:11px">{s}'
            f'{f" · {wr:.0f}%" if wr else ""}</span><br>'
            f'<span style="color:#c8e8c8;font-size:11px">{insight}</span>'
            f'{"<br><span style=color:#556655;font-size:10px>" + action + "</span>" if action else ""}'
            f'</div>'
        )

    pnl_color  = "#00cc88" if pnl["total_pnl"] >= 0 else "#ff4444"
    pnl_sign   = "+" if pnl["total_pnl"] >= 0 else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#060d06;font-family:'SF Mono',Monaco,monospace;color:#c8e8c8">
<div style="max-width:700px;margin:0 auto;padding:24px 16px">

  <!-- Header -->
  <div style="border-bottom:1px solid #00ff4120;padding-bottom:16px;margin-bottom:24px;display:flex;align-items:center;gap:16px">
    <div>
      <div style="color:#00ff41;font-size:11px;font-weight:700;letter-spacing:.2em">🏴‍☠️ ONE PIECE QUANT TERMINAL</div>
      <div style="font-size:22px;font-weight:700;color:#e8ffe8;margin-top:4px">Daily Report</div>
      <div style="color:#556655;font-size:11px;margin-top:2px">{today} · 10:00 PM IST</div>
    </div>
  </div>

  <!-- Screener hits -->
  <div style="color:#00ff41;font-size:10px;font-weight:700;letter-spacing:.18em;margin-bottom:8px">SCREENER HITS TODAY (≥95% CONF)</div>
  <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
    <thead><tr style="border-bottom:1px solid #00ff4120;color:#445544;font-size:10px">
      <th style="text-align:left;padding:6px 8px">STRATEGY</th>
      <th style="text-align:center;padding:6px 8px">HITS</th>
    </tr></thead>
    <tbody>{screener_rows}</tbody>
  </table>

  <!-- Paper P&L -->
  <div style="color:#00ff41;font-size:10px;font-weight:700;letter-spacing:.18em;margin-bottom:8px">PAPER TRADING TODAY</div>
  <div style="background:#0a180a;border-radius:8px;padding:14px;margin-bottom:24px">
    <div style="display:flex;gap:24px;flex-wrap:wrap">
      <div><div style="font-size:24px;font-weight:700;color:{pnl_color}">₹{pnl['total_pnl']:+,.0f}</div>
           <div style="color:#445544;font-size:10px;margin-top:2px">TODAY'S PNL</div></div>
      <div><div style="font-size:24px;font-weight:700;color:#e8ffe8">{pnl['closed_today']}</div>
           <div style="color:#445544;font-size:10px;margin-top:2px">CLOSED</div></div>
      <div><div style="font-size:24px;font-weight:700;color:#00ff41">{pnl['win_rate']:.0f}%</div>
           <div style="color:#445544;font-size:10px;margin-top:2px">WIN RATE</div></div>
      <div><div style="font-size:24px;font-weight:700;color:#f59e0b">{pnl['open_trades']}</div>
           <div style="color:#445544;font-size:10px;margin-top:2px">OPEN POSITIONS</div></div>
    </div>
  </div>

  <!-- 30-day win rates -->
  <div style="color:#00ff41;font-size:10px;font-weight:700;letter-spacing:.18em;margin-bottom:8px">30-DAY WIN RATES BY STRATEGY</div>
  <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:11px">
    <thead><tr style="border-bottom:1px solid #00ff4120;color:#445544;font-size:10px">
      <th style="text-align:left;padding:6px 8px">STRATEGY</th>
      <th style="text-align:center;padding:6px 8px">TRADES</th>
      <th style="text-align:center;padding:6px 8px">WIN%</th>
      <th style="text-align:right;padding:6px 8px">PNL</th>
    </tr></thead>
    <tbody>{wr_rows if wr_rows else '<tr><td colspan="4" style="padding:12px;color:#334433;text-align:center">No completed trades yet</td></tr>'}</tbody>
  </table>

  <!-- Agent insights -->
  {f'<div style="color:#00ff41;font-size:10px;font-weight:700;letter-spacing:.18em;margin-bottom:8px">🤖 AGENT INSIGHTS</div>{insights_html}<br>' if insights_html else ""}

  <!-- Top picks -->
  {f'''<div style="color:#00ff41;font-size:10px;font-weight:700;letter-spacing:.18em;margin-bottom:8px">🔝 TOP PICKS (≥97% CONFIDENCE)</div>
  <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:11px">
    <thead><tr style="border-bottom:1px solid #00ff4120;color:#445544;font-size:10px">
      <th style="text-align:left;padding:6px 8px">TICKER</th>
      <th style="text-align:left;padding:6px 8px">STRATEGY</th>
      <th style="text-align:center;padding:6px 8px">CONF</th>
      <th style="text-align:right;padding:6px 8px">LTP</th>
    </tr></thead>
    <tbody>{picks_rows}</tbody>
  </table>''' if picks else ""}

  <!-- Footer -->
  <div style="margin-top:24px;padding-top:12px;border-top:1px solid #ffffff08;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px">
    <a href="{DASHBOARD_URL}" style="color:#00ff41;text-decoration:none;font-size:11px;font-weight:700">→ Open Dashboard</a>
    <span style="color:#334433;font-size:10px">Not financial advice · {today} · One Piece Quant Terminal</span>
  </div>
</div></body></html>"""


def send_email(html: str, subject: str) -> bool:
    if not RESEND_API_KEY:
        print("  RESEND_API_KEY not set — email skipped")
        return False
    payload = json.dumps({
        "from":    "One Piece Quant <onboarding@resend.dev>",
        "to":      [REPORT_EMAIL],
        "subject": subject,
        "html":    html,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type":  "application/json",
            "User-Agent":    "curl/8.4.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            res = json.loads(resp.read())
        print(f"  Email sent → {REPORT_EMAIL} (id={res.get('id')})")
        return True
    except urllib.error.HTTPError as e:
        print(f"  Email failed: {e.code} {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"  Email failed: {e}")
        return False


def send_failure_alert(channel: str, error: str) -> None:
    """Send alert on the OTHER channel when one fails."""
    msg = (
        f"⚠️ *ONE PIECE QUANT — Delivery Failure*\n"
        f"_{channel} notification failed at 10PM IST_\n"
        f"`{error[:200]}`"
    )
    if channel == "email":
        # Email failed — alert via Telegram
        send_telegram(msg.replace("_", r"\_").replace("*", r"\*"))
    else:
        # Telegram failed — alert via email
        send_email(
            f"<p>{msg}</p>",
            f"⚠️ ONE PIECE QUANT — Telegram Delivery Failed · {date.today()}",
        )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    now = datetime.now(IST)
    print("=" * 60)
    print(f"  One Piece Quant — Daily Report  [{now.strftime('%Y-%m-%d %H:%M')} IST]")
    print("=" * 60)

    # 1. Run strategy agent
    print("\n[1/6] Running strategy agent...")
    try:
        from scripts.strategy_agent import run_and_report, get_latest_insights
        run_and_report()
    except Exception as e:
        print(f"  Strategy agent skipped: {e}")

    # 2. Gather data
    print("\n[2/6] Gathering screener hits...")
    hits = get_screener_hits()
    print(f"  Total hits: {sum(hits.values())}")

    print("\n[3/6] Paper trading P&L...")
    pnl = get_paper_pnl_today()
    print(f"  Today: {pnl['closed_today']} closed | PNL ₹{pnl['total_pnl']:+,.0f} | {pnl['win_rate']:.0f}% win")

    print("\n[4/6] 30-day win rates...")
    win_rates = get_30d_win_rates()
    print(f"  Data for {len(win_rates)} strategies")

    print("\n[5/6] Agent insights...")
    insights = get_latest_insights()
    print(f"  {len(insights)} insights loaded")

    print("\n[6/6] Top picks...")
    picks = get_top_picks()
    print(f"  {len(picks)} picks ≥97% confidence")

    # Build reports
    today     = date.today().strftime("%-d %b %Y")
    total_pnl = pnl["total_pnl"]
    subject   = (
        f"🏴‍☠️ One Piece Quant Daily Report — {today} | "
        f"PNL ₹{total_pnl:+,.0f} | {pnl['win_rate']:.0f}% win rate"
    )

    # Send Telegram
    tg_text = build_telegram_report(hits, pnl, win_rates, insights, picks)
    tg_ok   = send_telegram(tg_text)
    if not tg_ok:
        send_failure_alert("telegram", "Telegram API returned error")

    # Send email
    html    = build_email_html(hits, pnl, win_rates, insights, picks)
    email_ok = send_email(html, subject)
    if not email_ok:
        send_failure_alert("email", "Resend API call failed")

    print(f"\n  Telegram: {'✅' if tg_ok else '❌'}  |  Email: {'✅' if email_ok else '❌'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
