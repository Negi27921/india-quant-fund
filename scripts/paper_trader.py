"""
Paper Trading Agent — One Piece Quant

Runs on all 8 screeners (7 strategies + custom).
Each signal with ≥95% confidence gets a ₹25,000 paper trade.
Checks existing open trades for target/SL exit.
Stores everything in Supabase `paper_trades` table.

Schedule (GitHub Actions):
  9:30 AM IST  → open trades from morning screener
  3:15 PM IST  → check all open trades for exits before close

Modes:
  python scripts/paper_trader.py --open     # Open new trades from today's screener
  python scripts/paper_trader.py --check    # Check exits on open positions
  python scripts/paper_trader.py --both     # Open + check (default)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Config ─────────────────────────────────────────────────────────────────────
SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY     = os.getenv("SUPABASE_KEY", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MIN_CONFIDENCE   = int(os.getenv("MIN_CONFIDENCE", "95"))
TRADE_AMOUNT     = float(os.getenv("TRADE_AMOUNT", "25000"))  # INR per trade
MAX_OPEN_TRADES  = int(os.getenv("MAX_OPEN_TRADES", "30"))    # across all strategies
KILL_DRAWDOWN    = float(os.getenv("KILL_DRAWDOWN", "15.0"))  # % daily loss to halt

# ── Strategy parameters ────────────────────────────────────────────────────────
STRATEGY_PARAMS: dict[str, dict] = {
    "vcp":          {"target_pct": 8.0,  "sl_pct": 4.0,  "hold_days": 15},
    "ipo_base":     {"target_pct": 12.0, "sl_pct": 5.0,  "hold_days": 20},
    "rocket_base":  {"target_pct": 15.0, "sl_pct": 6.0,  "hold_days": 10},
    "breakout":     {"target_pct": 7.0,  "sl_pct": 3.0,  "hold_days": 10},
    "rsi_reversal": {"target_pct": 6.0,  "sl_pct": 3.0,  "hold_days": 7},
    "golden_cross": {"target_pct": 10.0, "sl_pct": 4.0,  "hold_days": 20},
    "multibagger":  {"target_pct": 20.0, "sl_pct": 7.0,  "hold_days": 30},
    "custom":       {"target_pct": 10.0, "sl_pct": 5.0,  "hold_days": 15},
}

ALL_STRATEGIES = list(STRATEGY_PARAMS.keys())


# ── Supabase helpers ───────────────────────────────────────────────────────────

def _sb(method: str, path: str, body: dict | None = None) -> dict | list:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {}
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body else b""
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
        "User-Agent":    "curl/8.4.0",
    }
    req = urllib.request.Request(url, data=data or None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  Supabase {method} {path} failed: {e}")
        return {} if method != "GET" else []


def sb_get(table: str, params: str = "") -> list:
    result = _sb("GET", f"{table}?{params}")
    return result if isinstance(result, list) else []


def sb_post(table: str, body: dict) -> dict:
    result = _sb("POST", table, body)
    if isinstance(result, list) and result:
        return result[0]
    return result if isinstance(result, dict) else {}


def sb_patch(table: str, params: str, body: dict) -> list:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    data = json.dumps(body).encode()
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
        "User-Agent":    "curl/8.4.0",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode())
            return result if isinstance(result, list) else [result]
    except Exception as e:
        print(f"  Supabase PATCH {table} failed: {e}")
        return []


# ── Screener cache read ────────────────────────────────────────────────────────

def fetch_screener_results(strategy: str) -> list[dict]:
    """Read latest screener results from Supabase cache."""
    for universe in ["full", "nifty500"]:
        rows = sb_get(
            "screener_cache",
            f"strategy=eq.{strategy}&universe=eq.{universe}&select=results,scanned_at&limit=1",
        )
        if rows:
            raw = rows[0].get("results")
            items = json.loads(raw) if isinstance(raw, str) else (raw or [])
            scanned = rows[0].get("scanned_at", "?")
            print(f"  {strategy} ({universe}): {len(items)} results, scanned {scanned[:16]}")
            return items
    return []


# ── Live price fetch ───────────────────────────────────────────────────────────

def get_ltp(ticker: str) -> float:
    """Fetch latest price via yfinance."""
    try:
        import yfinance as yf
        t = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        info = yf.Ticker(t).fast_info
        price = float(info.get("last_price") or info.get("regularMarketPrice") or 0)
        return price
    except Exception:
        return 0.0


def get_ltps_bulk(tickers: list[str]) -> dict[str, float]:
    """Bulk price fetch."""
    if not tickers:
        return {}
    try:
        import yfinance as yf
        ns_tickers = [t if t.endswith(".NS") else f"{t}.NS" for t in tickers]
        data = yf.download(
            ns_tickers, period="2d", interval="1d",
            auto_adjust=True, progress=False, threads=True,
        )
        closes = data["Close"] if "Close" in data else data
        ltps: dict[str, float] = {}
        for i, orig in enumerate(tickers):
            ns = ns_tickers[i]
            try:
                col = closes[ns] if ns in closes.columns else closes.iloc[:, i]
                ltps[orig] = float(col.dropna().iloc[-1])
            except Exception:
                ltps[orig] = 0.0
        return ltps
    except Exception as e:
        print(f"  Bulk LTP fetch failed: {e}")
        return {}


# ── Open trade management ──────────────────────────────────────────────────────

def get_open_trades() -> list[dict]:
    rows = sb_get("paper_trades", "status=eq.open&select=*")
    return rows


def get_daily_pnl_pct() -> float:
    """Calculate today's realised P&L % across all paper trades."""
    today = date.today().isoformat()
    closed = sb_get("paper_trades", f"exit_date=eq.{today}&select=pnl,trade_amount")
    if not closed:
        return 0.0
    total_invested = sum(float(r.get("trade_amount") or TRADE_AMOUNT) for r in closed)
    total_pnl = sum(float(r.get("pnl") or 0) for r in closed)
    return (total_pnl / total_invested * 100) if total_invested > 0 else 0.0


def check_exits(open_trades: list[dict], ltps: dict[str, float]) -> list[dict]:
    """Check each open trade against current price for target/SL/expiry."""
    closed_today: list[dict] = []
    today = date.today()

    for trade in open_trades:
        ticker   = trade.get("ticker", "")
        ltp      = ltps.get(ticker, 0)
        if ltp <= 0:
            ltp = get_ltp(ticker)
        if ltp <= 0:
            continue

        entry       = float(trade.get("entry_price") or 0)
        target      = float(trade.get("target_price") or 0)
        sl          = float(trade.get("sl_price") or 0)
        entry_date  = trade.get("entry_date", "")
        hold_days   = int(trade.get("hold_days") or 15)
        strategy    = trade.get("strategy", "")

        # Determine exit reason
        status = None
        if target > 0 and ltp >= target:
            status = "target_hit"
            exit_price = target
        elif sl > 0 and ltp <= sl:
            status = "sl_hit"
            exit_price = sl
        else:
            # Check expiry
            try:
                entry_dt = datetime.strptime(entry_date, "%Y-%m-%d").date()
                if (today - entry_dt).days >= hold_days:
                    status = "expired"
                    exit_price = ltp
            except Exception:
                pass

        if status:
            shares    = int(trade.get("shares") or 0)
            amount    = float(trade.get("trade_amount") or TRADE_AMOUNT)
            pnl       = round((exit_price - entry) * shares, 2) if shares > 0 else round((exit_price - entry) / entry * amount, 2)
            pnl_pct   = round((exit_price - entry) / entry * 100, 4) if entry > 0 else 0.0
            trade_id  = trade.get("id")

            if trade_id:
                sb_patch(
                    "paper_trades",
                    f"id=eq.{trade_id}",
                    {
                        "exit_date":  today.isoformat(),
                        "exit_price": round(exit_price, 2),
                        "pnl":        pnl,
                        "pnl_pct":    pnl_pct,
                        "status":     status,
                    },
                )

            closed_today.append({
                "ticker":  ticker,
                "strategy": strategy,
                "status":  status,
                "entry":   entry,
                "exit":    round(exit_price, 2),
                "pnl":     pnl,
                "pnl_pct": pnl_pct,
                "icon":    "✅" if pnl >= 0 else "❌",
            })
            print(f"  {status.upper()} {ticker} ({strategy}): "
                  f"entry ₹{entry:,.2f} → exit ₹{exit_price:,.2f} | PNL ₹{pnl:,.2f} ({pnl_pct:+.2f}%)")

    return closed_today


# ── Open new trades ────────────────────────────────────────────────────────────

def open_new_trades() -> list[dict]:
    """Read screener results, open paper trades for top ≥95% confidence picks."""
    today = date.today().isoformat()

    # Kill switch: check daily loss
    daily_pnl_pct = get_daily_pnl_pct()
    if daily_pnl_pct < -KILL_DRAWDOWN:
        print(f"  ⚠️  KILL SWITCH: Daily P&L {daily_pnl_pct:.1f}% exceeds -{KILL_DRAWDOWN}% limit")
        _notify_kill_switch(daily_pnl_pct)
        return []

    # Get already-open tickers to avoid duplicates
    open_trades = get_open_trades()
    held = {t.get("ticker") for t in open_trades}
    open_count = len(open_trades)

    print(f"\n  Open positions: {open_count} / {MAX_OPEN_TRADES}")
    if open_count >= MAX_OPEN_TRADES:
        print("  Max open trades reached — skipping new trades")
        return []

    new_trades: list[dict] = []
    seen_tickers: set[str] = set(held)

    for strategy in ALL_STRATEGIES:
        params = STRATEGY_PARAMS[strategy]
        results = fetch_screener_results(strategy)
        candidates = [r for r in results if r.get("confidence", 0) >= MIN_CONFIDENCE]
        candidates.sort(key=lambda x: -x.get("confidence", 0))

        for cand in candidates:
            if open_count + len(new_trades) >= MAX_OPEN_TRADES:
                break

            ticker = cand.get("ticker", "").replace(".NS", "")
            if ticker in seen_tickers:
                continue

            ltp        = float(cand.get("ltp") or 0)
            confidence = int(cand.get("confidence") or 0)
            if ltp <= 0:
                ltp = get_ltp(ticker)
            if ltp <= 0:
                print(f"  Skip {ticker}: no price data")
                continue

            target_pct = params["target_pct"]
            sl_pct     = params["sl_pct"]
            hold_days  = params["hold_days"]

            target_price = round(ltp * (1 + target_pct / 100), 2)
            sl_price     = round(ltp * (1 - sl_pct / 100), 2)
            shares       = max(int(TRADE_AMOUNT / ltp), 1)
            actual_amt   = round(shares * ltp, 2)

            # Check if already traded today for this ticker+strategy
            existing = sb_get(
                "paper_trades",
                f"ticker=eq.{ticker}&strategy=eq.{strategy}&entry_date=eq.{today}&select=id",
            )
            if existing:
                seen_tickers.add(ticker)
                continue

            row = sb_post("paper_trades", {
                "strategy":     strategy,
                "ticker":       ticker,
                "entry_date":   today,
                "entry_price":  round(ltp, 2),
                "target_price": target_price,
                "sl_price":     sl_price,
                "trade_amount": actual_amt,
                "shares":       shares,
                "confidence":   confidence,
                "hold_days":    hold_days,
                "status":       "open",
                "notes":        f"target={target_pct}% sl={sl_pct}%",
            })

            seen_tickers.add(ticker)
            new_trades.append({
                "ticker":       ticker,
                "strategy":     strategy,
                "ltp":          round(ltp, 2),
                "target":       target_price,
                "sl":           sl_price,
                "shares":       shares,
                "amount":       actual_amt,
                "confidence":   confidence,
                "target_pct":   target_pct,
                "sl_pct":       sl_pct,
            })
            print(f"  OPEN {ticker} ({strategy}): ₹{ltp:,.2f} × {shares} = ₹{actual_amt:,.0f} "
                  f"| Target +{target_pct}% | SL -{sl_pct}% | Conf {confidence}%")

    return new_trades


# ── Telegram notification ──────────────────────────────────────────────────────

def _notify_kill_switch(pnl_pct: float) -> None:
    msg = (
        f"🚨 *ONE PIECE QUANT — KILL SWITCH TRIGGERED*\n"
        f"Daily P\\&L: `{pnl_pct:.1f}%` exceeded threshold `\\-{KILL_DRAWDOWN}%`\n"
        f"_All new paper trades halted for today\\._"
    )
    _tg(msg)


def _tg(msg: str) -> bool:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return False
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       msg,
        "parse_mode": "MarkdownV2",
    }).encode()
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        return bool(result.get("ok"))
    except Exception as e:
        print(f"  Telegram send failed: {e}")
        return False


def notify_new_trades(trades: list[dict]) -> None:
    if not trades:
        _tg(
            f"🏴‍☠️ *ONE PIECE QUANT — Paper Trader*\n"
            f"_{date.today()} \\| No new trades today \\(no ≥{MIN_CONFIDENCE}% picks\\)_"
        )
        return

    lines = [
        f"🏴‍☠️ *ONE PIECE QUANT — Paper Trader*",
        f"_{date.today()} \\| {len(trades)} new paper trades @ ₹{TRADE_AMOUNT:,.0f}/trade_",
        "",
        "```",
        f"{'TICKER':<10} {'STRATEGY':<14} {'PRICE':>8} {'CONF':>5} {'TP':>5} {'SL':>5}",
        "─" * 55,
    ]
    for t in trades[:20]:
        lines.append(
            f"{t['ticker']:<10} {t['strategy']:<14} "
            f"₹{t['ltp']:>7,.0f} {t['confidence']:>4}% "
            f"+{t['target_pct']}% -{t['sl_pct']}%"
        )
    lines.append("```")
    lines.append(f"\n_Not financial advice\\._")

    _tg("\n".join(lines))


def notify_exits(closed: list[dict]) -> None:
    if not closed:
        return

    wins  = [t for t in closed if t["pnl"] >= 0]
    loss  = [t for t in closed if t["pnl"] < 0]
    total_pnl = sum(t["pnl"] for t in closed)

    lines = [
        f"📊 *ONE PIECE QUANT — Trade Exits*",
        f"_{date.today()} \\| {len(closed)} exits \\| Net PNL: ₹{total_pnl:+,.0f}_",
        "",
        "```",
        f"{'TICKER':<10} {'STATUS':<12} {'PNL':>10} {'%':>7}",
        "─" * 45,
    ]
    for t in sorted(closed, key=lambda x: -x["pnl"]):
        lines.append(
            f"{t['ticker']:<10} {t['status']:<12} "
            f"₹{t['pnl']:>+9,.0f} {t['pnl_pct']:>+6.1f}%"
        )
    lines.append("```")
    lines.append(
        f"\n✅ {len(wins)} wins \\| ❌ {len(loss)} losses \\| "
        f"Win rate: {len(wins)/len(closed)*100:.0f}%"
    )
    _tg("\n".join(lines))


# ── Entry point ────────────────────────────────────────────────────────────────

def main(mode: str = "both") -> None:
    now = datetime.now(IST)
    print("=" * 60)
    print(f"  One Piece Quant — Paper Trader  [{now.strftime('%Y-%m-%d %H:%M')} IST]")
    print(f"  Mode: {mode} | Trade amount: ₹{TRADE_AMOUNT:,.0f} | Min conf: {MIN_CONFIDENCE}%")
    print("=" * 60)

    new_trades: list[dict] = []
    closed_trades: list[dict] = []

    if mode in ("open", "both"):
        print("\n[OPEN] Scanning screener cache for new trades...")
        new_trades = open_new_trades()
        if new_trades:
            notify_new_trades(new_trades)
        print(f"\n  Opened {len(new_trades)} new paper trades")

    if mode in ("check", "both"):
        print("\n[CHECK] Checking open trades for exits...")
        open_trades = get_open_trades()
        print(f"  {len(open_trades)} open trades to check")

        if open_trades:
            tickers = [t.get("ticker", "") for t in open_trades]
            ltps = get_ltps_bulk(tickers)
            closed_trades = check_exits(open_trades, ltps)
            if closed_trades:
                notify_exits(closed_trades)

    # Summary
    daily_pnl_pct = get_daily_pnl_pct()
    print(f"\n  Summary: {len(new_trades)} opened | {len(closed_trades)} closed | "
          f"Today's realised PNL: {daily_pnl_pct:+.2f}%")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One Piece Quant — Paper Trader")
    parser.add_argument("--open",  action="store_true", help="Open new paper trades only")
    parser.add_argument("--check", action="store_true", help="Check exits on open positions only")
    parser.add_argument("--both",  action="store_true", help="Open + check (default)")
    args = parser.parse_args()

    if args.open:
        main("open")
    elif args.check:
        main("check")
    else:
        main("both")
