"""
Seed Universe Watchlist
───────────────────────
Fast seed of the Universe watchlist from api/full_universe.py (2137 NSE tickers).
No market-cap filtering — just populates the watchlist immediately so the
dashboard isn't empty while universe_agent.py does the full yfinance pass.

Run once via GitHub Actions or locally:
  python scripts/seed_universe_watchlist.py

Environment:
  SUPABASE_URL  required
  SUPABASE_KEY  required
"""
from __future__ import annotations

import os
import sys
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.full_universe import FULL_NSE_TICKERS

UNIVERSE_WL_ID = "bbbbbbbb-0000-0000-0000-000000000001"
SUPABASE_URL   = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "").strip()
BATCH          = 200  # upsert in batches to stay under Supabase payload limits

def _headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }

def _ensure_watchlist() -> None:
    """Create Universe watchlist if it doesn't exist yet."""
    url  = f"{SUPABASE_URL}/rest/v1/watchlists?id=eq.{UNIVERSE_WL_ID}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if resp.ok and resp.json():
        print("  Universe watchlist already exists")
        return
    payload = {
        "id":          UNIVERSE_WL_ID,
        "name":        "Universe",
        "description": "All investable BSE/NSE stocks — auto-updated daily by Universe Agent",
        "type":        "universe",
        "color":       "#60a5fa",
    }
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/watchlists",
        json=payload,
        headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
        timeout=15,
    )
    print(f"  Created Universe watchlist: {r.status_code}")

def _upsert_batch(rows: list[dict]) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/watchlist_items"
    hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    r = requests.post(url, json=rows, headers=hdrs, timeout=30)
    return r.ok

def main() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set")
        sys.exit(1)

    print("=" * 64)
    print(f"Seed Universe Watchlist  {datetime.now(timezone.utc).isoformat()}")
    print(f"Tickers to seed: {len(FULL_NSE_TICKERS)}")
    print("=" * 64)

    _ensure_watchlist()

    now       = datetime.now(timezone.utc).isoformat()
    total_ok  = 0
    total_err = 0

    for i in range(0, len(FULL_NSE_TICKERS), BATCH):
        chunk   = FULL_NSE_TICKERS[i : i + BATCH]
        rows    = []
        for ticker in chunk:
            symbol  = ticker.replace(".NS", "").replace(".BO", "")
            company = symbol  # no company name available at seed time
            rows.append({
                "watchlist_id": UNIVERSE_WL_ID,
                "symbol":       symbol,
                "ticker":       ticker,
                "company":      company,
                "sector":       "",
                "industry":     "",
                "added_at":     now,
            })

        ok = _upsert_batch(rows)
        if ok:
            total_ok += len(rows)
            print(f"  Batch {i//BATCH + 1}: {len(rows)} rows — OK")
        else:
            total_err += len(rows)
            print(f"  Batch {i//BATCH + 1}: {len(rows)} rows — FAILED")

        time.sleep(0.3)  # gentle rate limit

    print(f"\n{'='*64}")
    print(f"Seed done — {total_ok} inserted/updated, {total_err} errors")


if __name__ == "__main__":
    main()
    sys.exit(0)
