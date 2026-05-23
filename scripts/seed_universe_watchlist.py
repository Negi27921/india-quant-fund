"""
Seed Universe Watchlist
───────────────────────
Fast seed of the Universe watchlist from api/full_universe.py (2137 NSE tickers).
No market-cap filtering — populates immediately so the dashboard isn't empty
while universe_agent.py does the full yfinance market-cap pass.

Prerequisite: run migration 011_grant_anon_permissions.sql in Supabase first
if SUPABASE_KEY is the anon key (not service_role key).

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
SUPABASE_URL   = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "").strip()
BATCH          = 100   # smaller batches — safer for anon key rate limits


def _headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
    }


def _ensure_watchlist() -> bool:
    """Verify Universe watchlist exists (seeded by migration 009). Returns True if OK."""
    url  = f"{SUPABASE_URL}/rest/v1/watchlists?id=eq.{UNIVERSE_WL_ID}&select=id,name"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if not resp.ok:
        print(f"  [WL] GET watchlists failed: HTTP {resp.status_code} — {resp.text[:300]}")
        return False
    rows = resp.json()
    if rows:
        print(f"  Universe watchlist exists: {rows[0].get('name')}")
        return True
    # Try to create it (fallback if migration 009 wasn't run)
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
    if r.ok:
        print(f"  Created Universe watchlist: HTTP {r.status_code}")
        return True
    print(f"  [WL] POST watchlists failed: HTTP {r.status_code} — {r.text[:300]}")
    return False


def _upsert_batch(rows: list[dict]) -> tuple[bool, str]:
    """
    Upsert a batch of watchlist_items.
    Uses ?on_conflict=watchlist_id,symbol so Supabase uses the UNIQUE constraint
    for conflict resolution (not the PK which we don't send).
    Returns (ok, error_message).
    """
    url  = f"{SUPABASE_URL}/rest/v1/watchlist_items?on_conflict=watchlist_id,symbol"
    hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    r    = requests.post(url, json=rows, headers=hdrs, timeout=45)
    if r.ok:
        return True, ""
    return False, f"HTTP {r.status_code}: {r.text[:300]}"


def main() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set")
        sys.exit(1)

    print("=" * 64)
    print(f"Seed Universe Watchlist  {datetime.now(timezone.utc).isoformat()}")
    print(f"Tickers to seed: {len(FULL_NSE_TICKERS)}")
    print("=" * 64)

    if not _ensure_watchlist():
        print("FATAL: Universe watchlist missing and could not be created.")
        print("       Run migration 009_universe_watchlist.sql in Supabase first.")
        sys.exit(1)

    total_ok  = 0
    total_err = 0
    first_error: str = ""

    for i in range(0, len(FULL_NSE_TICKERS), BATCH):
        chunk = FULL_NSE_TICKERS[i : i + BATCH]
        rows  = []
        for ticker in chunk:
            symbol = ticker.replace(".NS", "").replace(".BO", "")
            rows.append({
                "watchlist_id": UNIVERSE_WL_ID,
                "symbol":       symbol,
                "ticker":       ticker,
                "company":      symbol,
                "sector":       "",
                "industry":     "",
                "added_reason": "universe_seed",
            })

        ok, err = _upsert_batch(rows)
        batch_n = i // BATCH + 1
        if ok:
            total_ok += len(rows)
            print(f"  Batch {batch_n}: {len(rows)} rows — OK")
        else:
            total_err += len(rows)
            print(f"  Batch {batch_n}: {len(rows)} rows — FAILED  {err}")
            if not first_error:
                first_error = err

        time.sleep(0.3)

    print(f"\n{'='*64}")
    print(f"Seed done — {total_ok} inserted/updated, {total_err} errors")

    if total_err > 0 and total_ok == 0:
        print("\n  *** ALL BATCHES FAILED ***")
        print(f"  First error: {first_error}")
        print("  Likely cause: anon key lacks INSERT permission.")
        print("  Fix: run migration 011_grant_anon_permissions.sql in Supabase SQL Editor.")
        sys.exit(1)


if __name__ == "__main__":
    main()
    sys.exit(0)
