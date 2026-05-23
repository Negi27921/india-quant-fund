"""
Morning screener — runs all 7 strategies for nifty500 universe and writes results
to Supabase screener_cache so the dashboard has fresh data on first load.

Schedule (GitHub Actions): 10:00 AM IST = 04:30 UTC  Mon–Fri  (after market open)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Make api/ importable
sys.path.insert(0, str(Path(__file__).parent.parent))

IST = ZoneInfo("Asia/Kolkata")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

STRATEGIES = ["vcp", "ipo_base", "rocket_base", "breakout", "rsi_reversal", "golden_cross", "multibagger"]
UNIVERSE   = "nifty500"


def _sb_write(strategy: str, universe: str, results: list[dict]) -> None:
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  Supabase not configured — skipping write")
        return
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    sb.table("screener_cache").upsert(
        {
            "strategy":    strategy,
            "universe":    universe,
            "scanned_at":  datetime.now(timezone.utc).isoformat(),
            "results":     json.dumps(results),
            "is_scanning": False,
        },
        on_conflict="strategy,universe",
    ).execute()


def main() -> None:
    print(f"[run_screener] {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")

    # Import the scan function from the API router
    from api.routers.screener import _run_scan

    total_t0 = time.time()
    for strategy in STRATEGIES:
        t0 = time.time()
        print(f"  Scanning {strategy}/{UNIVERSE}...")
        try:
            results = _run_scan(strategy, UNIVERSE)
            elapsed = time.time() - t0
            print(f"    → {len(results)} results in {elapsed:.1f}s")
            _sb_write(strategy, UNIVERSE, results)
            print(f"    → Saved to Supabase")
        except Exception as e:
            print(f"    ✗ {strategy} failed: {e}")

    total_elapsed = time.time() - total_t0
    print(f"[run_screener] Done in {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
