"""
FII/DII daily data updater — runs from GitHub Actions (10 PM IST, Mon–Fri).

Fetches 60-day FII/DII cash-segment data from NSE India and persists it to
Supabase screener_cache (strategy="fii_dii", universe="cash") so the Vercel
API can serve real data even when NSE blocks direct serverless requests.

Also overwrites api/fii_dii_data/latest.json with today's row.
"""
from __future__ import annotations

import http.cookiejar as _cj
import json
import os
import sys
import time
import urllib.request as _ur
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

_REPO_ROOT = Path(__file__).parent.parent
_LATEST_JSON = _REPO_ROOT / "api" / "fii_dii_data" / "latest.json"
_LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def _sf(v, default: float = 0.0) -> float:
    try:
        import math
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return default


def fetch_nse_fii_dii() -> list[dict]:
    """Fetch 30-day FII/DII data from NSE India with session cookie."""
    jar = _cj.CookieJar()
    opener = _ur.build_opener(_ur.HTTPCookieProcessor(jar))

    # Step 1: land on the page to get cookies
    req = _ur.Request(
        "https://www.nseindia.com/reports/fii-dii",
        headers={**HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"},
    )
    try:
        opener.open(req, timeout=10)
    except Exception as e:
        print(f"  Cookie fetch failed: {e}")
        raise

    time.sleep(1.0)

    # Step 2: fetch the API
    api_req = _ur.Request(
        "https://www.nseindia.com/api/fiidiiTradeReact",
        headers={
            **HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/reports/fii-dii",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with opener.open(api_req, timeout=10) as r:
        import gzip as _gz, io as _io
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = _gz.decompress(raw)
        data = json.loads(raw)

    rows = []
    for row in (data if isinstance(data, list) else []):
        fii_net = _sf(row.get("buySell_FII_net", row.get("fii_net", 0)))
        dii_net = _sf(row.get("buySell_DII_net", row.get("dii_net", 0)))
        if abs(fii_net) < 0.01 and abs(dii_net) < 0.01:
            continue
        rows.append({
            "date":             row.get("date", ""),
            "fii_buy":          _sf(row.get("buySell_FII_buy",  row.get("fii_buy",  0))),
            "fii_sell":         _sf(row.get("buySell_FII_sell", row.get("fii_sell", 0))),
            "fii_net":          fii_net,
            "dii_buy":          _sf(row.get("buySell_DII_buy",  row.get("dii_buy",  0))),
            "dii_sell":         _sf(row.get("buySell_DII_sell", row.get("dii_sell", 0))),
            "dii_net":          dii_net,
            "fii_idx_fut_net":  0.0,
            "fii_stk_fut_net":  0.0,
            "fii_idx_call_net": 0.0,
            "fii_idx_put_net":  0.0,
            "pcr":              0.0,
            "sentiment_score":  50.0,
            "sentiment":        "Neutral",
            "updated_at":       datetime.now(IST).isoformat(),
        })
    return rows


def save_to_supabase(rows: list[dict]) -> None:
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("  Supabase not configured — skipping")
        return
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    sb.table("screener_cache").upsert(
        {
            "strategy":    "fii_dii",
            "universe":    "cash",
            "scanned_at":  datetime.now(timezone.utc).isoformat(),
            "results":     json.dumps(rows),
            "is_scanning": False,
        },
        on_conflict="strategy,universe",
    ).execute()
    print(f"  Saved {len(rows)} rows to Supabase screener_cache")


def save_latest_json(rows: list[dict]) -> None:
    if not rows:
        return
    latest = rows[-1]
    with open(_LATEST_JSON, "w") as f:
        json.dump({**latest, "_updated_at": datetime.now(IST).isoformat()}, f, indent=2)
    print(f"  Updated {_LATEST_JSON} → {latest.get('date','')}")


def main() -> None:
    print(f"[FII/DII updater] {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")

    try:
        rows = fetch_nse_fii_dii()
        print(f"  Fetched {len(rows)} rows from NSE")
    except Exception as e:
        print(f"  NSE fetch failed: {e}")
        sys.exit(1)

    if not rows:
        print("  No valid rows returned — nothing to save")
        sys.exit(1)

    save_to_supabase(rows)
    save_latest_json(rows)
    print("  Done.")


if __name__ == "__main__":
    main()
