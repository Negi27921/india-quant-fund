"""Seed Supabase with realistic paper trades and daily P&L data.

IMPORTANT: Supabase RLS blocks anon key writes.
Before running this script, you MUST either:
  A) Run scripts/fix_rls_and_seed.sql in Supabase Dashboard → SQL Editor, OR
  B) Add SUPABASE_SERVICE_KEY to your .env file (Project Settings → API → service_role key)

Usage:
  python3 scripts/seed_paper_trades.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
# Use service key if available, fall back to anon key
def _decode_role(key: str) -> str:
    """Decode JWT payload to get role."""
    try:
        import base64, json
        payload = key.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.b64decode(payload)).get("role", "")
    except Exception:
        return ""


SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_KEY"]
_role = _decode_role(SUPABASE_KEY)
if _role not in ("service_role",):
    print(f"WARNING: Key role is '{_role}' (not service_role). RLS may block inserts.")
    print("  → Get service_role key from: Supabase Dashboard → Project Settings → API")
    print("  → Add to .env: SUPABASE_SERVICE_KEY=eyJhbGci...\n")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def rest(method: str, table: str, payload=None, params: str = ""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    r = requests.request(method, url, headers=HEADERS, json=payload, timeout=30)
    if not r.ok:
        print(f"ERROR {method} {table}: {r.status_code} {r.text[:400]}")
        if "row-level security" in r.text:
            print("\n  *** RLS BLOCKED ***")
            print("  Fix: Run scripts/fix_rls_and_seed.sql in Supabase SQL Editor")
            print("  OR: Add SUPABASE_SERVICE_KEY to .env and re-run this script\n")
        sys.exit(1)
    return r.json() if r.text else []


def insert(table: str, rows: list[dict]):
    return rest("POST", table, rows)


def query(table: str, select: str = "*"):
    return rest("GET", table, params=f"?select={select}")


def delete_existing(table: str, date_col: str):
    """Delete rows from 2026 onwards."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?{date_col}=gte.2026-01-01"
    r = requests.delete(url, headers={**HEADERS, "Prefer": "return=minimal"}, timeout=30)
    if r.ok:
        print(f"  Cleared existing {table} rows from 2026+")
    else:
        print(f"  Could not clear {table}: {r.status_code} (continuing)")


# ── Paper trades (status values match updated schema: OPEN/CLOSED) ─────────
PAPER_TRADES = [
    # CLOSED WINNERS
    {
        "strategy": "vcp", "ticker": "RELIANCE", "entry_date": "2026-04-01",
        "entry_price": 1285.50, "target_price": 1420.0, "sl_price": 1245.0,
        "shares": 50, "confidence": 82, "hold_days": 18,
        "exit_date": "2026-04-19", "exit_price": 1412.80,
        "pnl": round(50 * (1412.80 - 1285.50), 2),
        "pnl_pct": round((1412.80 - 1285.50) / 1285.50 * 100, 2),
        "status": "CLOSED", "notes": "VCP breakout on volume. Nailed the move."
    },
    {
        "strategy": "breakout", "ticker": "HDFCBANK", "entry_date": "2026-04-03",
        "entry_price": 1745.00, "target_price": 1900.0, "sl_price": 1700.0,
        "shares": 40, "confidence": 75, "hold_days": 14,
        "exit_date": "2026-04-17", "exit_price": 1889.50,
        "pnl": round(40 * (1889.50 - 1745.00), 2),
        "pnl_pct": round((1889.50 - 1745.00) / 1745.00 * 100, 2),
        "status": "CLOSED", "notes": "52-week high breakout, clean close above resistance."
    },
    {
        "strategy": "golden_cross", "ticker": "INFY", "entry_date": "2026-04-07",
        "entry_price": 1582.00, "target_price": 1720.0, "sl_price": 1540.0,
        "shares": 35, "confidence": 70, "hold_days": 12,
        "exit_date": "2026-04-19", "exit_price": 1695.00,
        "pnl": round(35 * (1695.00 - 1582.00), 2),
        "pnl_pct": round((1695.00 - 1582.00) / 1582.00 * 100, 2),
        "status": "CLOSED", "notes": "50 DMA crossed above 200 DMA. IT rally."
    },
    {
        "strategy": "multibagger", "ticker": "TITAN", "entry_date": "2026-04-10",
        "entry_price": 3415.00, "target_price": 3900.0, "sl_price": 3300.0,
        "shares": 15, "confidence": 88, "hold_days": 20,
        "exit_date": "2026-04-30", "exit_price": 3892.00,
        "pnl": round(15 * (3892.00 - 3415.00), 2),
        "pnl_pct": round((3892.00 - 3415.00) / 3415.00 * 100, 2),
        "status": "CLOSED", "notes": "Strong fundamentals + Q4 earnings beat."
    },
    {
        "strategy": "rsi_reversal", "ticker": "SUNPHARMA", "entry_date": "2026-04-14",
        "entry_price": 1685.00, "target_price": 1780.0, "sl_price": 1640.0,
        "shares": 30, "confidence": 68, "hold_days": 10,
        "exit_date": "2026-04-24", "exit_price": 1762.50,
        "pnl": round(30 * (1762.50 - 1685.00), 2),
        "pnl_pct": round((1762.50 - 1685.00) / 1685.00 * 100, 2),
        "status": "CLOSED", "notes": "RSI bounced from 32. Pharma sector rotation."
    },
    {
        "strategy": "breakout", "ticker": "LTIM", "entry_date": "2026-04-16",
        "entry_price": 5280.00, "target_price": 5800.0, "sl_price": 5100.0,
        "shares": 10, "confidence": 72, "hold_days": 9,
        "exit_date": "2026-04-25", "exit_price": 5694.00,
        "pnl": round(10 * (5694.00 - 5280.00), 2),
        "pnl_pct": round((5694.00 - 5280.00) / 5280.00 * 100, 2),
        "status": "CLOSED", "notes": "LTIM breakout post Q4. Strong deal wins."
    },
    # CLOSED LOSERS
    {
        "strategy": "vcp", "ticker": "ADANIENT", "entry_date": "2026-04-08",
        "entry_price": 2385.00, "target_price": 2620.0, "sl_price": 2300.0,
        "shares": 20, "confidence": 60, "hold_days": 6,
        "exit_date": "2026-04-14", "exit_price": 2298.00,
        "pnl": round(20 * (2298.00 - 2385.00), 2),
        "pnl_pct": round((2298.00 - 2385.00) / 2385.00 * 100, 2),
        "status": "CLOSED", "notes": "Stop triggered. Adani news overhang."
    },
    {
        "strategy": "golden_cross", "ticker": "WIPRO", "entry_date": "2026-04-21",
        "entry_price": 568.50, "target_price": 620.0, "sl_price": 548.0,
        "shares": 80, "confidence": 65, "hold_days": 7,
        "exit_date": "2026-04-28", "exit_price": 545.00,
        "pnl": round(80 * (545.00 - 568.50), 2),
        "pnl_pct": round((545.00 - 568.50) / 568.50 * 100, 2),
        "status": "CLOSED", "notes": "Weak IT guidance, cut losses early."
    },
    {
        "strategy": "ipo_base", "ticker": "ONGC", "entry_date": "2026-04-22",
        "entry_price": 268.00, "target_price": 300.0, "sl_price": 255.0,
        "shares": 150, "confidence": 58, "hold_days": 5,
        "exit_date": "2026-04-27", "exit_price": 257.50,
        "pnl": round(150 * (257.50 - 268.00), 2),
        "pnl_pct": round((257.50 - 268.00) / 268.00 * 100, 2),
        "status": "CLOSED", "notes": "Oil prices dropped. Stop out."
    },
    # OPEN POSITIONS
    {
        "strategy": "vcp", "ticker": "TCS", "entry_date": "2026-05-02",
        "entry_price": 3845.00, "target_price": 4200.0, "sl_price": 3720.0,
        "shares": 15, "confidence": 85, "hold_days": None,
        "exit_date": None, "exit_price": None,
        "pnl": None, "pnl_pct": None,
        "status": "OPEN", "notes": "VCP setup, tight coil. Strong volume on base."
    },
    {
        "strategy": "breakout", "ticker": "BAJFINANCE", "entry_date": "2026-05-05",
        "entry_price": 7215.00, "target_price": 7900.0, "sl_price": 6980.0,
        "shares": 8, "confidence": 78, "hold_days": None,
        "exit_date": None, "exit_price": None,
        "pnl": None, "pnl_pct": None,
        "status": "OPEN", "notes": "Multi-month consolidation breakout on high volume."
    },
    {
        "strategy": "multibagger", "ticker": "AXISBANK", "entry_date": "2026-05-07",
        "entry_price": 1185.00, "target_price": 1340.0, "sl_price": 1140.0,
        "shares": 45, "confidence": 80, "hold_days": None,
        "exit_date": None, "exit_price": None,
        "pnl": None, "pnl_pct": None,
        "status": "OPEN", "notes": "Strong Q4 results. Banking sector tailwinds."
    },
    {
        "strategy": "rsi_reversal", "ticker": "ICICIBANK", "entry_date": "2026-05-08",
        "entry_price": 1248.00, "target_price": 1380.0, "sl_price": 1200.0,
        "shares": 40, "confidence": 76, "hold_days": None,
        "exit_date": None, "exit_price": None,
        "pnl": None, "pnl_pct": None,
        "status": "OPEN", "notes": "RSI recovery from oversold. Accumulation pattern."
    },
    {
        "strategy": "golden_cross", "ticker": "TATAMOTORS", "entry_date": "2026-05-09",
        "entry_price": 718.50, "target_price": 820.0, "sl_price": 685.0,
        "shares": 70, "confidence": 74, "hold_days": None,
        "exit_date": None, "exit_price": None,
        "pnl": None, "pnl_pct": None,
        "status": "OPEN", "notes": "50 DMA cross. EV + JLR recovery thesis."
    },
    {
        "strategy": "vcp", "ticker": "KOTAKBANK", "entry_date": "2026-05-12",
        "entry_price": 2045.00, "target_price": 2280.0, "sl_price": 1980.0,
        "shares": 25, "confidence": 82, "hold_days": None,
        "exit_date": None, "exit_price": None,
        "pnl": None, "pnl_pct": None,
        "status": "OPEN", "notes": "VCP on weekly chart. Clean base, low volatility coil."
    },
]


# ── Daily P&L (Apr 1 – May 14 2026) ──────────────────────────────────────────
DAILY_PNL = [
    {"date": "2026-04-01", "portfolio_value": 1001450.00, "day_pnl":  1450.00, "day_pnl_pct":  0.1450, "drawdown_pct":  0.0000},
    {"date": "2026-04-02", "portfolio_value": 1003820.00, "day_pnl":  2370.00, "day_pnl_pct":  0.2366, "drawdown_pct":  0.0000},
    {"date": "2026-04-03", "portfolio_value": 1002190.00, "day_pnl": -1630.00, "day_pnl_pct": -0.1625, "drawdown_pct":  0.0000},
    {"date": "2026-04-04", "portfolio_value": 1005680.00, "day_pnl":  3490.00, "day_pnl_pct":  0.3482, "drawdown_pct":  0.0000},
    {"date": "2026-04-07", "portfolio_value": 1008340.00, "day_pnl":  2660.00, "day_pnl_pct":  0.2643, "drawdown_pct":  0.0000},
    {"date": "2026-04-08", "portfolio_value": 1010920.00, "day_pnl":  2580.00, "day_pnl_pct":  0.2558, "drawdown_pct":  0.0000},
    {"date": "2026-04-09", "portfolio_value": 1009150.00, "day_pnl": -1770.00, "day_pnl_pct": -0.1750, "drawdown_pct":  0.0000},
    {"date": "2026-04-10", "portfolio_value": 1013250.00, "day_pnl":  4100.00, "day_pnl_pct":  0.4062, "drawdown_pct":  0.0000},
    {"date": "2026-04-11", "portfolio_value": 1015870.00, "day_pnl":  2620.00, "day_pnl_pct":  0.2586, "drawdown_pct":  0.0000},
    {"date": "2026-04-14", "portfolio_value": 1014120.00, "day_pnl": -1750.00, "day_pnl_pct": -0.1722, "drawdown_pct":  0.0000},
    {"date": "2026-04-15", "portfolio_value": 1017680.00, "day_pnl":  3560.00, "day_pnl_pct":  0.3511, "drawdown_pct":  0.0000},
    {"date": "2026-04-16", "portfolio_value": 1020430.00, "day_pnl":  2750.00, "day_pnl_pct":  0.2702, "drawdown_pct":  0.0000},
    {"date": "2026-04-17", "portfolio_value": 1023190.00, "day_pnl":  2760.00, "day_pnl_pct":  0.2705, "drawdown_pct":  0.0000},
    {"date": "2026-04-22", "portfolio_value": 1021450.00, "day_pnl": -1740.00, "day_pnl_pct": -0.1700, "drawdown_pct":  0.0000},
    {"date": "2026-04-23", "portfolio_value": 1025230.00, "day_pnl":  3780.00, "day_pnl_pct":  0.3700, "drawdown_pct":  0.0000},
    {"date": "2026-04-24", "portfolio_value": 1028760.00, "day_pnl":  3530.00, "day_pnl_pct":  0.3443, "drawdown_pct":  0.0000},
    {"date": "2026-04-25", "portfolio_value": 1032420.00, "day_pnl":  3660.00, "day_pnl_pct":  0.3558, "drawdown_pct":  0.0000},
    {"date": "2026-04-28", "portfolio_value": 1030680.00, "day_pnl": -1740.00, "day_pnl_pct": -0.1685, "drawdown_pct":  0.0000},
    {"date": "2026-04-29", "portfolio_value": 1034520.00, "day_pnl":  3840.00, "day_pnl_pct":  0.3726, "drawdown_pct":  0.0000},
    {"date": "2026-04-30", "portfolio_value": 1037890.00, "day_pnl":  3370.00, "day_pnl_pct":  0.3258, "drawdown_pct":  0.0000},
    {"date": "2026-05-01", "portfolio_value": 1036340.00, "day_pnl": -1550.00, "day_pnl_pct": -0.1493, "drawdown_pct":  0.0000},
    {"date": "2026-05-02", "portfolio_value": 1040120.00, "day_pnl":  3780.00, "day_pnl_pct":  0.3648, "drawdown_pct":  0.0000},
    {"date": "2026-05-05", "portfolio_value": 1038570.00, "day_pnl": -1550.00, "day_pnl_pct": -0.1490, "drawdown_pct": -0.0015},
    {"date": "2026-05-06", "portfolio_value": 1042680.00, "day_pnl":  4110.00, "day_pnl_pct":  0.3957, "drawdown_pct":  0.0000},
    {"date": "2026-05-07", "portfolio_value": 1045930.00, "day_pnl":  3250.00, "day_pnl_pct":  0.3118, "drawdown_pct":  0.0000},
    {"date": "2026-05-08", "portfolio_value": 1044280.00, "day_pnl": -1650.00, "day_pnl_pct": -0.1578, "drawdown_pct": -0.0016},
    {"date": "2026-05-09", "portfolio_value": 1048550.00, "day_pnl":  4270.00, "day_pnl_pct":  0.4089, "drawdown_pct":  0.0000},
    {"date": "2026-05-12", "portfolio_value": 1051820.00, "day_pnl":  3270.00, "day_pnl_pct":  0.3119, "drawdown_pct":  0.0000},
    {"date": "2026-05-13", "portfolio_value": 1054390.00, "day_pnl":  2570.00, "day_pnl_pct":  0.2443, "drawdown_pct":  0.0000},
    {"date": "2026-05-14", "portfolio_value": 1057630.00, "day_pnl":  3240.00, "day_pnl_pct":  0.3073, "drawdown_pct":  0.0000},
]


def main():
    print("=" * 60)
    print("Seeding Supabase with paper trades and daily P&L...")
    print(f"Key role: {_role or 'unknown'}")
    print("=" * 60)

    # Delete existing 2026 data
    print("\n[1/4] Clearing existing paper_trades (2026)...")
    delete_existing("paper_trades", "entry_date")

    print("[2/4] Clearing existing daily_pnl (2026)...")
    delete_existing("daily_pnl", "date")

    # Insert paper trades
    print(f"\n[3/4] Inserting {len(PAPER_TRADES)} paper trades...")
    result = insert("paper_trades", PAPER_TRADES)
    if isinstance(result, list):
        print(f"  Inserted {len(result)} paper trades")

    # Insert daily P&L
    print(f"\n[4/4] Inserting {len(DAILY_PNL)} daily P&L rows...")
    result2 = insert("daily_pnl", DAILY_PNL)
    if isinstance(result2, list):
        print(f"  Inserted {len(result2)} daily_pnl rows")

    # Verify
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    trades = query("paper_trades", "id,ticker,status,pnl")
    print(f"\npaper_trades count: {len(trades)}")
    open_t  = [t for t in trades if str(t.get("status", "")).upper() == "OPEN"]
    closed_t = [t for t in trades if str(t.get("status", "")).upper() == "CLOSED"]
    print(f"  OPEN:   {len(open_t)}")
    print(f"  CLOSED: {len(closed_t)}")
    total_pnl = sum(float(t["pnl"]) for t in closed_t if t.get("pnl"))
    print(f"  Total closed P&L: ₹{total_pnl:,.2f}")

    pnl_rows = query("daily_pnl", "date,portfolio_value")
    print(f"\ndaily_pnl count: {len(pnl_rows)}")
    if pnl_rows:
        sorted_rows = sorted(pnl_rows, key=lambda x: x["date"])
        print(f"  First: {sorted_rows[0]['date']}  Value: ₹{float(sorted_rows[0]['portfolio_value']):,.2f}")
        print(f"  Last:  {sorted_rows[-1]['date']}  Value: ₹{float(sorted_rows[-1]['portfolio_value']):,.2f}")
        print(f"  Total return: {(float(sorted_rows[-1]['portfolio_value']) / 1_000_000 - 1) * 100:.2f}%")

    print("\nSeeding complete!")


if __name__ == "__main__":
    main()
