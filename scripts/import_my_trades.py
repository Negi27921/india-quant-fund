"""
Import My Trades.xlsx (Upstox Realized P&L) → journal_trades table.

Idempotent: uses a deterministic ID (md5 of symbol+buy_date+qty+buy_price+sell_date)
so re-running never creates duplicates.

Usage:
    python3 scripts/import_my_trades.py [--xlsx path/to/My Trades.xlsx] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Load env ──────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_env_path = _ROOT / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_SB_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
_SB_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

if not _SB_URL or not _SB_KEY:
    sys.exit("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "apikey":        _SB_KEY,
        "Authorization": f"Bearer {_SB_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _get(path: str) -> list:
    url = f"{_SB_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _upsert(path: str, rows: list[dict]) -> None:
    url = f"{_SB_URL}/rest/v1/{path}"
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    data = json.dumps(rows).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        raise RuntimeError(f"Supabase {e.code}: {body[:400]}")


# ── Parse xlsx ────────────────────────────────────────────────────────────────

def _parse_xlsx(xlsx_path: str) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        sys.exit("Run: pip install openpyxl")

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb["REALIZED_PNL_DOWNLOAD"]

    trades = []
    header_row = None

    for row in ws.iter_rows(values_only=True):
        if row[0] == "Scrip Name ":
            header_row = list(row)
            continue
        if header_row is None:
            continue
        if not row[0] or row[0] == "TOTAL":
            continue
        # Skip footer notice rows
        if isinstance(row[0], str) and "transitioned" in row[0].lower():
            continue

        r = dict(zip(header_row, row))
        symbol    = (r.get("Symbol") or "").strip()
        scrip     = (r.get("Scrip Name ") or "").strip()
        isin      = (r.get("ISIN") or "").strip()
        qty       = r.get("Qty")
        buy_rate  = r.get("Buy Rate")
        buy_amt   = r.get("Buy Amt")
        sell_rate = r.get("Sell Rate")
        sell_amt  = r.get("Sell Amt")
        buy_date  = r.get("Buy Date")
        sell_date = r.get("Sell Date")
        total_pl  = r.get("Total PL")
        days      = r.get("Days")
        spec      = r.get("Speculation")
        st        = r.get("Short Term")

        if not symbol or qty is None or buy_rate is None:
            continue

        # Normalise dates
        def _dt(v) -> str:
            if isinstance(v, datetime):
                return v.date().isoformat()
            if isinstance(v, str):
                return v[:10]
            return str(v)[:10]

        buy_date_str  = _dt(buy_date)
        sell_date_str = _dt(sell_date) if sell_date else None

        # Determine trade type: Speculation = intraday, else Swing
        trade_type = "Intraday" if (spec and float(spec or 0) != 0 and days == 0) else "Swing"

        # Unique deterministic ID
        uid_src = f"{symbol}|{buy_date_str}|{int(qty)}|{float(buy_rate):.4f}|{sell_date_str}"
        trade_id = "imp_" + hashlib.md5(uid_src.encode()).hexdigest()[:16]

        pl_val = float(total_pl or 0)
        notes = (
            f"Upstox Import · {scrip} · ISIN: {isin} · "
            f"Days held: {int(days or 0)} · "
            f"P&L: ₹{pl_val:+,.2f} · "
            f"Buy ₹{float(buy_amt or 0):,.2f} → Sell ₹{float(sell_amt or 0):,.2f}"
        )

        trades.append({
            "id":          trade_id,
            "stock_name":  symbol,
            "buy_price":   round(float(buy_rate), 4),
            "quantity":    int(qty),
            "entry_date":  buy_date_str,
            "capital_used": round(float(buy_amt or 0), 2),
            "trade_type":  trade_type,
            "status":      "Closed",
            "sell_price":  round(float(sell_rate), 4) if sell_rate else None,
            "exit_date":   sell_date_str,
            "strategy":    "FY2026-27 Upstox",
            "notes":       notes,
            "rule_followed": "Yes",
        })

    return trades


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=str(_ROOT.parent / "My Trades.xlsx"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"Reading {args.xlsx} ...")
    trades = _parse_xlsx(args.xlsx)
    print(f"  → Parsed {len(trades)} trades")

    # Fetch existing IDs to show what's new vs already imported
    print("Checking existing journal_trades ...")
    existing = {r["id"] for r in _get("journal_trades?select=id&strategy=eq.FY2026-27%20Upstox")}
    new_trades = [t for t in trades if t["id"] not in existing]
    already   = len(trades) - len(new_trades)

    print(f"  → {already} already imported, {len(new_trades)} new")

    if not new_trades:
        print("Nothing to import. Done.")
        return

    if args.dry_run:
        print("\nDRY RUN — first 3 rows:")
        for t in new_trades[:3]:
            print(" ", json.dumps(t, default=str, indent=2))
        return

    # Upsert in batches of 50
    batch = 50
    for i in range(0, len(new_trades), batch):
        chunk = new_trades[i:i + batch]
        _upsert("journal_trades", chunk)
        print(f"  Inserted rows {i+1}–{min(i+batch, len(new_trades))}")

    print(f"\nDone. {len(new_trades)} trades imported into journal_trades.")
    print("\nSummary:")
    total_pl = sum(
        (float(t["sell_price"] or 0) - float(t["buy_price"])) * t["quantity"]
        for t in trades if t["sell_price"]
    )
    print(f"  Total realized P&L: ₹{total_pl:+,.2f}")
    print(f"  Trades: {len(trades)} | Winners: {sum(1 for t in trades if t['sell_price'] and (float(t['sell_price']) - float(t['buy_price'])) > 0)}")


if __name__ == "__main__":
    main()
