"""
Seed Supabase with demo portfolio data for testing the dashboard.

Usage:
  python scripts/seed_demo_data.py

Requires SUPABASE_URL and SUPABASE_KEY env vars (from .env file).
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()


def _sb(method: str, path: str, body=None):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body else b""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
        "User-Agent": "curl/8.4.0",
    }
    req = urllib.request.Request(url, data=data or None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  Supabase {method} {path}: {e}")
        return {}


PAPER_TRADES = [
    # (strategy, ticker, entry_date_offset, entry_price, target_pct, sl_pct, hold_days, status, pnl_pct)
    ("multibagger",  "RVNL",     -25, 285.40, 20, 7,  30, "open",       None),
    ("multibagger",  "IRFC",     -20, 175.20, 20, 7,  30, "open",       None),
    ("vcp",          "ASTRAL",   -18, 1820.0, 8,  4,  15, "open",       None),
    ("breakout",     "TITAGARH", -15, 1105.0, 7,  3,  10, "open",       None),
    ("golden_cross", "HDFCBANK", -12, 1680.0, 10, 4,  20, "open",       None),
    ("multibagger",  "BSE",      -10,  1380.0, 20, 7, 30, "open",       None),
    ("vcp",          "ZOMATO",    -8,  232.0,  8,  4, 15, "open",       None),
    ("breakout",     "BPCL",      -6,  342.0,  7,  3, 10, "open",       None),
    ("multibagger",  "CDSL",     -30, 1050.0, 20, 7,  30, "target_hit", 18.4),
    ("vcp",          "DIXON",    -28, 13200.0, 8, 4,  15, "target_hit",  7.8),
    ("golden_cross", "BAJFINANCE",-22, 6800.0,10, 4,  20, "target_hit", 9.2),
    ("ipo_base",     "JYOTILAB", -19, 1650.0, 12, 5,  20, "target_hit", 11.5),
    ("breakout",     "TIINDIA",  -16, 3450.0, 7,  3,  10, "sl_hit",    -3.2),
    ("rsi_reversal", "TATACHEM", -14, 1020.0, 6,  3,   7, "sl_hit",    -3.0),
    ("golden_cross", "ICICIBANK",-11, 1130.0, 10, 4,  20, "target_hit", 8.7),
    ("breakout",     "APOLLOHOSP",-9, 6850.0, 7,  3,  10, "expired",    4.1),
    ("vcp",          "POLYCAB",   -7, 5400.0,  8, 4,  15, "target_hit", 7.5),
    ("multibagger",  "POWERGRID", -5,  325.0, 20, 7,  30, "open",       None),
    ("rsi_reversal", "SUNPHARMA", -4, 1680.0,  6, 3,   7, "target_hit", 5.8),
    ("ipo_base",     "FIRSTCRY", -3,   380.0, 12, 5,  20, "open",       None),
]

DAILY_PNL = [
    (-30,  985_000, 30_000,  0.15, 0.0),
    (-29,  988_500, 27_500,  0.36, 0.0),
    (-28,  994_200, 21_800,  0.57, 0.0),
    (-27,  991_800, 24_200, -0.24, 0.0),
    (-26,  997_300, 18_700,  0.56, 0.0),
    (-25, 1003_500, 12_500,  0.62, 0.2),
    (-24, 1008_900,  7_100,  0.54, 0.7),
    (-23, 1006_200,  9_800, -0.27, 0.5),
    (-22, 1011_400,  4_600,  0.52, 0.9),
    (-21, 1017_800,      0,  0.63, 1.2),
    (-20, 1023_100,      0,  0.52, 1.8),
    (-19, 1019_400,      0, -0.37, 1.5),
    (-18, 1025_600,      0,  0.61, 2.1),
    (-17, 1031_200,      0,  0.55, 2.7),
    (-16, 1028_700,      0, -0.24, 2.4),
    (-15, 1034_100,      0,  0.52, 3.0),
    (-14, 1039_800,      0,  0.55, 3.5),
    (-13, 1036_900,      0, -0.28, 3.2),
    (-12, 1043_200,      0,  0.61, 3.8),
    (-11, 1049_600,      0,  0.61, 4.4),
    (-10, 1046_100,      0, -0.33, 4.1),
    ( -9, 1052_800,      0,  0.64, 4.7),
    ( -8, 1059_300,      0,  0.63, 5.4),
    ( -7, 1056_400,      0, -0.27, 5.0),
    ( -6, 1063_100,      0,  0.63, 5.7),
    ( -5, 1070_000,      0,  0.64, 6.3),
    ( -4, 1067_200,      0, -0.26, 6.0),
    ( -3, 1074_100,      0,  0.65, 6.7),
    ( -2, 1081_200,      0,  0.66, 7.3),
    ( -1, 1078_500,      0, -0.25, 7.0),
    (  0, 1082_000,      0,  0.32, 7.4),
]


def main():
    today = date.today()
    print("=" * 55)
    print("  One Piece Demo Data Seeder")
    print("=" * 55)

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("  ❌ SUPABASE_URL / SUPABASE_KEY not set")
        sys.exit(1)

    # 1. Paper trades
    print("\n[1] Seeding paper_trades...")
    ok = 0
    for row in PAPER_TRADES:
        strat, ticker, offset, entry, tp_pct, sl_pct, hold, status, pnl_pct = row
        entry_date = (today + timedelta(days=offset)).isoformat()
        target = round(entry * (1 + tp_pct / 100), 2)
        sl     = round(entry * (1 - sl_pct / 100), 2)
        shares = max(int(25000 / entry), 1)
        amount = round(shares * entry, 2)

        exit_date  = None
        exit_price = None
        pnl        = None
        if status != "open" and pnl_pct is not None:
            exit_date  = (today + timedelta(days=offset + hold)).isoformat()
            exit_price = round(entry * (1 + pnl_pct / 100), 2)
            pnl        = round((exit_price - entry) * shares, 2)

        body = {
            "strategy": strat, "ticker": ticker, "entry_date": entry_date,
            "entry_price": entry, "target_price": target, "sl_price": sl,
            "exit_date": exit_date, "exit_price": exit_price,
            "trade_amount": amount, "shares": shares,
            "pnl": pnl, "pnl_pct": pnl_pct, "confidence": 97,
            "hold_days": hold, "status": status,
            "notes": f"target={tp_pct}% sl={sl_pct}%",
        }
        result = _sb("POST", "paper_trades", body)
        if result:
            ok += 1
            print(f"  ✓ {ticker} ({strat}) {status}")
        else:
            print(f"  ✗ {ticker} failed")
    print(f"  {ok}/{len(PAPER_TRADES)} paper trades seeded")

    # 2. Daily P&L
    print("\n[2] Seeding daily_pnl...")
    ok = 0
    peak = 1_000_000.0
    for offset, nav, cash, day_pct, dd_pct in DAILY_PNL:
        d = (today + timedelta(days=offset)).isoformat()
        day_pnl = round(nav * day_pct / 100, 2)
        peak = max(peak, nav)
        drawdown = round((nav - peak) / peak * 100, 4) if nav < peak else 0.0
        body = {
            "date": d, "portfolio_value": nav, "cash": cash,
            "invested": nav - cash, "day_pnl": day_pnl, "day_pnl_pct": day_pct,
            "realized_pnl": 0, "unrealized_pnl": nav - 1_000_000,
            "drawdown_pct": drawdown, "num_positions": 8,
        }
        result = _sb("POST", "daily_pnl", body)
        if isinstance(result, list) and result:
            ok += 1
        elif isinstance(result, dict) and result:
            ok += 1
    print(f"  {ok}/{len(DAILY_PNL)} daily_pnl rows seeded")

    # 3. Trade log
    print("\n[3] Seeding trades (filled orders)...")
    fills = [
        ("RVNL",     "BUY",   3, -25, 285.40, 42, "multibagger"),
        ("IRFC",     "BUY",   3, -20, 175.20, 71, "multibagger"),
        ("ASTRAL",   "BUY",   3, -18, 1820.0,  8, "vcp"),
        ("CDSL",     "BUY",   3, -32, 1050.0,  7, "multibagger"),
        ("CDSL",     "SELL",  3, -18, 1243.0,  7, "multibagger"),
        ("DIXON",    "BUY",   3, -30, 13200.0, 1, "vcp"),
        ("DIXON",    "SELL",  3, -22, 14229.0, 1, "vcp"),
        ("BAJFINANCE","BUY",  3, -24, 6800.0,  2, "golden_cross"),
        ("BAJFINANCE","SELL", 3, -18, 7425.0,  2, "golden_cross"),
        ("TIINDIA",  "BUY",   3, -18, 3450.0,  4, "breakout"),
        ("TIINDIA",  "SELL",  3, -15, 3340.0,  4, "breakout"),
    ]
    ok = 0
    for ticker, side, qty, offset, price, qty_, strat in fills:
        d = (today + timedelta(days=offset)).isoformat()
        total = round(qty_ * price, 2)
        body = {
            "trade_date": d, "ticker": ticker, "side": side,
            "quantity": qty_, "price": price, "total_value": total,
            "strategy": strat,
        }
        result = _sb("POST", "trades", body)
        if result:
            ok += 1
            print(f"  ✓ {side} {ticker} @ ₹{price}")
    print(f"  {ok}/{len(fills)} trade log entries seeded")

    print("\n  ✅ Done. Refresh the dashboard.")
    print("=" * 55)


if __name__ == "__main__":
    main()
