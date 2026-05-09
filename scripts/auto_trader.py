"""
Auto-trader agent — reads screener results from Supabase and places
paper/live trades via Dhan API based on risk config.

Run modes:
  python scripts/auto_trader.py --paper       # dry-run (no real orders)
  python scripts/auto_trader.py --live        # real orders (PAPER_TRADING=false)
  python scripts/auto_trader.py --dry-run     # just show what would be traded

Config via env vars or .env file:
  PAPER_TRADING        true | false
  RISK_PCT_PER_TRADE   max % of portfolio per trade (default 2.0)
  MAX_OPEN_POSITIONS   max simultaneous positions (default 5)
  MIN_CONFIDENCE       only trade ≥ this confidence (default 95)
  STRATEGIES           comma-separated list (default multibagger)
  DHAN_CLIENT_ID       Dhan client ID
  DHAN_ACCESS_TOKEN    Dhan access token
  SUPABASE_URL         Supabase project URL
  SUPABASE_KEY         Supabase service key
  TELEGRAM_BOT_TOKEN   Telegram bot token
  TELEGRAM_CHAT_ID     Telegram chat ID
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

IST = ZoneInfo("Asia/Kolkata")

# ── Config ────────────────────────────────────────────────────────────────────
PAPER_TRADING      = os.getenv("PAPER_TRADING", "true").lower() == "true"
RISK_PCT_PER_TRADE = float(os.getenv("RISK_PCT_PER_TRADE", "2.0"))   # 2% of portfolio per trade
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
MIN_CONFIDENCE     = int(os.getenv("MIN_CONFIDENCE", "95"))
STRATEGIES         = os.getenv("STRATEGIES", "multibagger").split(",")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# NSE holidays 2025 (add more as needed)
NSE_HOLIDAYS_2025 = {
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31",
    "2025-04-10", "2025-04-14", "2025-04-18", "2025-05-01",
    "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-02",
    "2025-10-23", "2025-10-24", "2025-11-05", "2025-12-25",
}


# ── Market open check ─────────────────────────────────────────────────────────

def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    if str(now.date()) in NSE_HOLIDAYS_2025:
        return False
    market_open  = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


# ── Portfolio helpers ─────────────────────────────────────────────────────────

def get_portfolio_value() -> float:
    """Fetch current fund limit from Dhan."""
    try:
        from dhanhq import dhanhq
        client_id    = os.getenv("DHAN_CLIENT_ID", "")
        access_token = os.getenv("DHAN_ACCESS_TOKEN", "")
        if not (client_id and access_token):
            return 0.0
        dhan = dhanhq(client_id, access_token)
        limits = dhan.get_fund_limits()
        if isinstance(limits, dict) and "data" in limits:
            return float(limits["data"].get("availabelBalance", 0))
    except Exception as e:
        print(f"  Portfolio fetch failed: {e}")
    return 0.0


def get_open_positions() -> list[dict]:
    """Fetch current open positions from Dhan."""
    try:
        from dhanhq import dhanhq
        client_id    = os.getenv("DHAN_CLIENT_ID", "")
        access_token = os.getenv("DHAN_ACCESS_TOKEN", "")
        if not (client_id and access_token):
            return []
        dhan = dhanhq(client_id, access_token)
        result = dhan.get_positions()
        if isinstance(result, dict):
            return result.get("data", []) or []
    except Exception as e:
        print(f"  Positions fetch failed: {e}")
    return []


# ── Screener results from Supabase ────────────────────────────────────────────

def fetch_screener_candidates(strategy: str) -> list[dict]:
    """Read latest screener results from Supabase cache."""
    try:
        from data.storage import supabase_db as sdb
        rows = sdb.select(
            "screener_cache",
            cols="results,scanned_at",
            filters={"strategy": strategy, "universe": "full"},
            limit=1,
        )
        if not rows:
            rows = sdb.select(
                "screener_cache",
                cols="results,scanned_at",
                filters={"strategy": strategy, "universe": "nifty500"},
                limit=1,
            )
        if not rows:
            return []
        raw = rows[0].get("results")
        results = json.loads(raw) if isinstance(raw, str) else (raw or [])
        scanned_at = rows[0].get("scanned_at", "unknown")
        print(f"  {strategy}: {len(results)} cached results (scanned: {scanned_at})")
        return results
    except Exception as e:
        print(f"  Supabase read failed: {e}")
        return []


# ── Order sizing ──────────────────────────────────────────────────────────────

def compute_quantity(ltp: float, sl_pct: float, portfolio_value: float) -> int:
    """
    Risk-based position sizing:
      risk_amount = portfolio_value × RISK_PCT_PER_TRADE / 100
      risk_per_share = ltp × sl_pct / 100
      quantity = risk_amount / risk_per_share
    """
    if ltp <= 0 or sl_pct <= 0 or portfolio_value <= 0:
        return 0
    risk_amount    = portfolio_value * RISK_PCT_PER_TRADE / 100
    risk_per_share = ltp * sl_pct / 100
    qty = int(risk_amount / risk_per_share)
    return max(qty, 1)


# ── Order placement ───────────────────────────────────────────────────────────

def place_order(ticker: str, qty: int, ltp: float, sl: float, tp1: float, dry_run: bool = False) -> dict:
    """Place a limit buy order via Dhan (or simulate in paper/dry-run mode)."""
    limit_price = round(ltp * 1.001, 2)   # 0.1% above LTP for immediate fill

    if dry_run or PAPER_TRADING:
        mode = "DRY-RUN" if dry_run else "PAPER"
        print(f"  [{mode}] BUY {ticker}: qty={qty} @ ₹{limit_price} | SL=₹{sl} | TP=₹{tp1}")
        return {
            "ticker": ticker, "side": "BUY", "qty": qty, "price": limit_price,
            "sl": sl, "tp1": tp1, "mode": mode, "status": "SIMULATED",
        }

    try:
        from dhanhq import dhanhq, constants
        client_id    = os.getenv("DHAN_CLIENT_ID", "")
        access_token = os.getenv("DHAN_ACCESS_TOKEN", "")
        dhan = dhanhq(client_id, access_token)

        # Look up Dhan security ID for NSE ticker
        ticker_ns = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        import yfinance as yf
        info    = yf.Ticker(ticker_ns).info
        isin    = info.get("isin", "")
        # Dhan requires security_id — use a best-effort lookup
        result = dhan.place_order(
            security_id  = ticker,        # falls back if no ID mapping
            exchange_segment = constants.NSE,
            transaction_type = constants.BUY,
            quantity     = qty,
            order_type   = constants.LIMIT,
            product_type = constants.INTRA,  # use CNC for delivery; INTRA for intraday
            price        = limit_price,
        )
        status = result.get("status", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"
        order_id = result.get("data", {}).get("orderId", "") if isinstance(result, dict) else ""
        print(f"  LIVE BUY {ticker}: qty={qty} @ ₹{limit_price} | orderId={order_id} | {status}")
        return {"ticker": ticker, "side": "BUY", "qty": qty, "price": limit_price,
                "sl": sl, "tp1": tp1, "mode": "LIVE", "status": status, "order_id": order_id}
    except Exception as e:
        print(f"  Order failed for {ticker}: {e}")
        return {"ticker": ticker, "status": "FAILED", "error": str(e)}


# ── Supabase trade log ────────────────────────────────────────────────────────

def log_trade(trade: dict, strategy: str) -> None:
    try:
        from data.storage import supabase_db as sdb
        sdb.insert("trades", {
            "ticker":     trade["ticker"],
            "side":       trade.get("side", "BUY"),
            "quantity":   trade.get("qty", 0),
            "price":      trade.get("price", 0),
            "trade_date": date.today().isoformat(),
            "strategy":   strategy,
            "pnl":        None,
            "order_id":   trade.get("order_id", ""),
            "mode":       trade.get("mode", "PAPER"),
        })
    except Exception as e:
        print(f"  Trade log failed: {e}")


# ── Telegram notification ─────────────────────────────────────────────────────

def notify_telegram(trades: list[dict], skipped: list[str]) -> None:
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return
    mode = "🟡 PAPER" if PAPER_TRADING else "🟢 LIVE"
    lines = [
        f"🤖 *Auto-Trader Agent* [{mode}]",
        f"📅 {date.today()} | {datetime.now(IST).strftime('%H:%M')} IST",
        f"📊 {len(trades)} orders placed | {len(skipped)} skipped",
        "",
    ]
    for t in trades:
        icon = "✅" if t.get("status") not in ("FAILED",) else "❌"
        lines.append(
            f"{icon} *{t['ticker']}* BUY {t.get('qty',0)} @ ₹{t.get('price',0):,.2f}"
            f" | SL ₹{t.get('sl',0):,.2f}"
        )
    if skipped:
        lines.append(f"\n⏭ Skipped (already held / max positions): {', '.join(skipped)}")
    lines.append("\n_Not financial advice._")

    import json as _json
    msg  = "\n".join(lines)
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = _json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception as e:
        print(f"  Telegram notification failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False):
    print("=" * 60)
    print(f"  IQF Auto-Trader Agent  —  {date.today()}  {datetime.now(IST).strftime('%H:%M')} IST")
    mode_str = "DRY-RUN" if dry_run else ("PAPER" if PAPER_TRADING else "LIVE ⚠️")
    print(f"  Mode: {mode_str}")
    print("=" * 60)

    # Safety: require explicit flag to go live
    if not PAPER_TRADING and not dry_run:
        confirm = os.getenv("CONFIRM_LIVE_TRADING", "")
        if confirm != "YES_I_AM_SURE":
            print("  ❌ Live trading requires CONFIRM_LIVE_TRADING=YES_I_AM_SURE env var.")
            print("     Set it explicitly to confirm you want real orders placed.")
            sys.exit(1)

    if not dry_run and not is_market_open():
        print("  ⏰ Market is closed — no orders placed.")
        now = datetime.now(IST)
        if now.weekday() < 5 and str(now.date()) not in NSE_HOLIDAYS_2025:
            print("     Market hours: 9:15 AM – 3:30 PM IST, Mon–Fri")
        return

    # Portfolio state
    portfolio_value = get_portfolio_value() if not dry_run else float(os.getenv("DEMO_PORTFOLIO", "1000000"))
    open_positions  = get_open_positions() if not dry_run else []
    held_tickers    = {p.get("tradingSymbol", "").replace("-EQ", "") for p in open_positions}
    available_slots = MAX_OPEN_POSITIONS - len(held_tickers)

    print(f"\n  Portfolio: ₹{portfolio_value:,.0f}")
    print(f"  Open positions: {len(held_tickers)} / {MAX_OPEN_POSITIONS}")
    print(f"  Available slots: {available_slots}")

    if available_slots <= 0:
        print("  Max positions reached — no new orders.")
        return

    # Gather candidates from all configured strategies
    all_candidates: list[tuple[str, dict]] = []  # (strategy, result)
    for strategy in STRATEGIES:
        strategy = strategy.strip()
        candidates = fetch_screener_candidates(strategy)
        for c in candidates:
            if c.get("confidence", 0) >= MIN_CONFIDENCE:
                all_candidates.append((strategy, c))

    # Sort by confidence desc, deduplicate by ticker
    all_candidates.sort(key=lambda x: -x[1]["confidence"])
    seen: set[str] = set()
    unique: list[tuple[str, dict]] = []
    for strat, cand in all_candidates:
        if cand["ticker"] not in seen:
            seen.add(cand["ticker"])
            unique.append((strat, cand))

    print(f"\n  {len(unique)} unique candidates ≥ {MIN_CONFIDENCE}% confidence")

    placed_trades: list[dict] = []
    skipped: list[str] = []

    for strategy, cand in unique:
        if len(placed_trades) >= available_slots:
            break

        ticker = cand["ticker"]
        ltp    = cand["ltp"]
        sl     = cand["sl"]
        sl_pct = cand["sl_pct"]
        tp1    = cand["tp1"]

        if ticker in held_tickers:
            skipped.append(ticker)
            print(f"  Skip {ticker} — already holding")
            continue

        qty = compute_quantity(ltp, sl_pct, portfolio_value)
        if qty <= 0:
            skipped.append(ticker)
            print(f"  Skip {ticker} — qty computed as 0 (portfolio: ₹{portfolio_value:,.0f})")
            continue

        trade_value = qty * ltp
        print(f"\n  → {ticker} | Conf {cand['confidence']}% | ₹{ltp:,.2f} × {qty} = ₹{trade_value:,.0f}"
              f" | SL ₹{sl:,.2f} ({sl_pct}%) | TP ₹{tp1:,.2f}")

        trade = place_order(ticker, qty, ltp, sl, tp1, dry_run=dry_run)
        placed_trades.append(trade)

        if not dry_run:
            log_trade(trade, strategy)

    print(f"\n  Summary: {len(placed_trades)} orders | {len(skipped)} skipped")
    notify_telegram(placed_trades, skipped)
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IQF Auto-Trader Agent")
    parser.add_argument("--paper",   action="store_true", help="Paper trading mode (no real orders)")
    parser.add_argument("--live",    action="store_true", help="Live trading (real orders — be careful!)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be traded, nothing placed")
    args = parser.parse_args()

    if args.live:
        os.environ["PAPER_TRADING"] = "false"
    if args.paper:
        os.environ["PAPER_TRADING"] = "true"

    main(dry_run=args.dry_run or (not args.paper and not args.live))
