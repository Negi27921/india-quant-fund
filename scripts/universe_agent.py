"""
Universe Agent — BSE/NSE Stock Universe Manager

Mission: Maintain a live list of investable Indian stocks (market cap > 1000 Cr)
         across both NSE and BSE, stored in the Supabase stock_universe table.

Sources:
  1. BSE EQ-segment API  — all BSE-listed EQ stocks (excludes SME/BE/BM segments)
  2. NSE EQUITY_L.csv    — all NSE-listed EQ stocks
  3. yfinance fast_info  — market cap filter (<1000 Cr excluded)

Runs daily via GitHub Actions. Safe to run multiple times (upserts by symbol).

Filtering:
  ✓ BSE EQ segment only (excludes SME = BE/BM/Z/XT segments)
  ✓ Market cap ≥ 1000 Cr (configurable via MCAP_MIN_CR env var)
  ✓ Has valid price data (not suspended/zero volume)
  ✗ Excludes SME Exchange (NSE Emerge / BSE SME)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

# ── Config ───────────────────────────────────────────────────────────────────
SUPABASE_URL    = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY", "").strip()
MCAP_MIN_CR     = float(os.getenv("MCAP_MIN_CR", "1000"))   # default 1000 Cr
BATCH_SIZE      = int(os.getenv("BATCH_SIZE", "50"))        # yfinance batch size
MAX_STOCKS      = int(os.getenv("MAX_STOCKS", "0"))         # 0 = no limit (testing)

_BSE_EQ_URL = (
    "https://api.bseindia.com/BseIndiaAPI/api/listofscripdata/w"
    "?Group=EQ&Scripcode=&flag=0&strsearch="
)
_NSE_CSV_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

_BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer":    "https://www.bseindia.com/",
    "Accept":     "application/json",
}

# BSE segments to exclude (SME and odd lots)
_EXCLUDE_GROUPS = {"BE", "BM", "Z", "XT", "ZT", "ZP", "Y", "R", "IL"}

# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates,return=minimal",
    }


def _sb_upsert_batch(rows: list[dict]) -> int:
    if not (SUPABASE_URL and SUPABASE_KEY) or not rows:
        return 0
    data = json.dumps(rows, default=str).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/stock_universe",
        data=data, headers=_sb_headers(), method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        return len(rows)
    except urllib.error.HTTPError as e:
        body = e.read()[:300]
        print(f"  [SB] upsert error {e.code}: {body}")
        return 0
    except Exception as e:
        print(f"  [SB] upsert failed: {e}")
        return 0


def _sb_get_existing_symbols() -> dict[str, dict]:
    """Return {symbol: {market_cap_cr, last_updated}} for all existing records."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {}
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/stock_universe?select=symbol,market_cap_cr,last_updated&limit=10000",
            headers=_sb_headers()
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read())
        return {r["symbol"]: r for r in rows}
    except Exception as e:
        print(f"  [SB] get_existing failed: {e}")
        return {}


# ── BSE stock list ────────────────────────────────────────────────────────────

def _fetch_bse_eq_list() -> list[dict]:
    """Fetch all BSE EQ-segment stocks. Returns list of dicts with symbol, company, sector etc."""
    print("[BSE] Fetching EQ stock list…")
    try:
        req = urllib.request.Request(_BSE_EQ_URL, headers=_BSE_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        # BSE returns {"Table": [...]} or just a list
        items = data.get("Table", data) if isinstance(data, dict) else data
        stocks = []
        for item in items:
            group = str(item.get("Group", "")).strip().upper()
            if group in _EXCLUDE_GROUPS:
                continue
            scrip  = str(item.get("SCRIP_CD", "")).strip()
            name   = str(item.get("Scrip_Name", "") or item.get("SCRIP_NAME", "")).strip()
            nse_sym = str(item.get("NSE_SYMBOL", "") or "").strip()
            sector  = str(item.get("Sector_name", "") or item.get("SECTOR", "") or "").strip()
            industry = str(item.get("Industry", "") or "").strip()
            if scrip:
                stocks.append({
                    "bse_scrip_code": scrip,
                    "company": name,
                    "nse_symbol": nse_sym,
                    "sector": sector,
                    "industry": industry,
                })
        print(f"  Got {len(stocks)} BSE EQ stocks (excluded SME/odd lot segments)")
        return stocks
    except Exception as e:
        print(f"  [BSE] fetch failed: {e}")
        return []


def _fetch_nse_eq_list() -> list[dict]:
    """Fetch NSE EQUITY_L.csv and parse symbol + company + sector."""
    print("[NSE] Fetching EQUITY_L.csv…")
    try:
        req = urllib.request.Request(
            _NSE_CSV_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="ignore")
        lines = raw.strip().split("\n")
        if not lines:
            return []
        header = [h.strip().strip('"') for h in lines[0].split(",")]
        stocks = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 2:
                continue
            row = dict(zip(header, [p.strip().strip('"') for p in parts]))
            symbol = row.get("SYMBOL", "").strip()
            series = row.get("SERIES", "").strip()
            # Only EQ series (not BE = BSE SME equivalent on NSE, not SM = NSE Emerge)
            if series not in ("EQ",):
                continue
            if not symbol:
                continue
            stocks.append({
                "symbol": symbol,
                "company": row.get("NAME OF COMPANY", "").strip(),
                "isin": row.get("ISIN NUMBER", "").strip(),
            })
        print(f"  Got {len(stocks)} NSE EQ stocks")
        return stocks
    except Exception as e:
        print(f"  [NSE] fetch failed: {e}")
        return []


# ── Market cap check via yfinance ─────────────────────────────────────────────

def _fetch_market_caps_batch(tickers: list[str]) -> dict[str, dict]:
    """Batch fetch market cap, price, prev_close, 52W high/low for a list of tickers."""
    try:
        import yfinance as yf
        result = {}
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                fi = t.fast_info
                price      = getattr(fi, "last_price", None) or getattr(fi, "regular_market_price", None)
                prev_close = getattr(fi, "previous_close", None)
                week_high  = getattr(fi, "year_high", None)
                week_low   = getattr(fi, "year_low", None)
                mcap       = getattr(fi, "market_cap", None) or 0
                if price and price > 0:
                    result[ticker] = {
                        "last_price":    round(float(price), 2),
                        "market_cap_cr": round(float(mcap) / 1e7, 2) if mcap else 0,
                        "pe":            None,
                        "prev_close":    round(float(prev_close), 2) if prev_close else None,
                        "week_high_52":  round(float(week_high), 2) if week_high else None,
                        "week_low_52":   round(float(week_low), 2) if week_low else None,
                    }
            except Exception:
                pass
        return result
    except ImportError:
        print("  [yfinance] not installed")
        return {}


# ── Merge BSE + NSE lists ─────────────────────────────────────────────────────

def _build_candidate_list(bse_stocks: list[dict], nse_stocks: list[dict]) -> list[dict]:
    """
    Merge BSE and NSE lists into a deduplicated candidate list.
    Priority for symbol: NSE symbol > BSE scrip code.
    """
    candidates: dict[str, dict] = {}

    # Seed from NSE list (EQ series only)
    for s in nse_stocks:
        sym = s["symbol"]
        candidates[sym] = {
            "symbol":        sym,
            "ticker":        f"{sym}.NS",
            "company":       s["company"],
            "bse_scrip_code": "",
            "exchange":      "NSE",
            "sector":        "",
            "industry":      "",
        }

    # Add BSE stocks — augment if NSE symbol known, add new if BSE-only
    for b in bse_stocks:
        nse_sym = b.get("nse_symbol", "").strip()
        bse_code = b["bse_scrip_code"]

        if nse_sym and nse_sym in candidates:
            # Already in NSE list — just add BSE scrip code + sector
            candidates[nse_sym]["bse_scrip_code"] = bse_code
            candidates[nse_sym]["exchange"] = "BOTH"
            if b.get("sector") and not candidates[nse_sym]["sector"]:
                candidates[nse_sym]["sector"] = b["sector"]
            if b.get("industry") and not candidates[nse_sym]["industry"]:
                candidates[nse_sym]["industry"] = b["industry"]
        elif nse_sym:
            # NSE symbol from BSE data but not in NSE list
            candidates[nse_sym] = {
                "symbol":        nse_sym,
                "ticker":        f"{nse_sym}.NS",
                "company":       b["company"],
                "bse_scrip_code": bse_code,
                "exchange":      "BOTH",
                "sector":        b.get("sector", ""),
                "industry":      b.get("industry", ""),
            }
        else:
            # BSE-only stock (no NSE listing) — use BSE ticker
            if bse_code not in candidates:
                candidates[bse_code] = {
                    "symbol":        bse_code,
                    "ticker":        f"{bse_code}.BO",
                    "company":       b["company"],
                    "bse_scrip_code": bse_code,
                    "exchange":      "BSE",
                    "sector":        b.get("sector", ""),
                    "industry":      b.get("industry", ""),
                }

    return list(candidates.values())


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    print("=" * 64)
    print(f"Universe Agent  {now}")
    print(f"Filter: market cap ≥ ₹{MCAP_MIN_CR:,.0f} Cr | batch size: {BATCH_SIZE}")
    print("=" * 64)

    # 1. Fetch stock lists
    bse_stocks = _fetch_bse_eq_list()
    nse_stocks = _fetch_nse_eq_list()

    # 2. Build merged candidate list
    print("\n[MERGE] Building candidate list…")
    candidates = _build_candidate_list(bse_stocks, nse_stocks)
    print(f"  {len(candidates)} unique stocks across BSE + NSE")

    if MAX_STOCKS > 0:
        candidates = candidates[:MAX_STOCKS]
        print(f"  Capped at {MAX_STOCKS} for testing")

    # 3. Load existing market caps to avoid re-fetching recently updated stocks
    print("\n[SB] Loading existing universe…")
    existing = _sb_get_existing_symbols()
    print(f"  {len(existing)} stocks already in universe")

    # 4. Batch market cap check
    print(f"\n[MCAP] Fetching market caps in batches of {BATCH_SIZE}…")
    tickers_to_check = [c["ticker"] for c in candidates]
    all_mcaps: dict[str, dict] = {}

    for i in range(0, len(tickers_to_check), BATCH_SIZE):
        batch = tickers_to_check[i:i + BATCH_SIZE]
        batch_result = _fetch_market_caps_batch(batch)
        all_mcaps.update(batch_result)
        done = min(i + BATCH_SIZE, len(tickers_to_check))
        eligible = sum(1 for v in batch_result.values() if v["market_cap_cr"] >= MCAP_MIN_CR)
        print(f"  [{done:>4}/{len(tickers_to_check)}] batch: {len(batch_result)} prices, {eligible} pass filter")
        time.sleep(0.3)  # rate limiting

    # 5. Filter and build upsert rows
    rows_to_upsert: list[dict] = []
    excluded_mcap = 0
    excluded_no_data = 0

    for c in candidates:
        ticker = c["ticker"]
        mcap_data = all_mcaps.get(ticker)
        if not mcap_data:
            excluded_no_data += 1
            continue
        mcap_cr = mcap_data["market_cap_cr"]
        if mcap_cr < MCAP_MIN_CR and mcap_cr > 0:
            excluded_mcap += 1
            continue

        row = {
            "symbol":         c["symbol"],
            "ticker":         ticker,
            "company":        c["company"],
            "bse_scrip_code": c.get("bse_scrip_code") or None,
            "exchange":       c.get("exchange", "NSE"),
            "sector":         c.get("sector", ""),
            "industry":       c.get("industry", ""),
            "market_cap_cr":  mcap_cr,
            "last_price":     mcap_data["last_price"],
            "pe":             mcap_data.get("pe"),
            "is_active":      True,
            "last_updated":   now,
        }
        if mcap_data.get("prev_close"):
            row["prev_close"] = mcap_data["prev_close"]
        if mcap_data.get("week_high_52"):
            row["week_high_52"] = mcap_data["week_high_52"]
        if mcap_data.get("week_low_52"):
            row["week_low_52"] = mcap_data["week_low_52"]
        rows_to_upsert.append(row)

    print(f"\n[FILTER] Results:")
    print(f"  Pass filter : {len(rows_to_upsert)}")
    print(f"  No data     : {excluded_no_data}")
    print(f"  Below {MCAP_MIN_CR:.0f}Cr : {excluded_mcap}")

    # 6. Upsert in batches
    print(f"\n[SB] Upserting {len(rows_to_upsert)} stocks to Supabase…")
    total_saved = 0
    for i in range(0, len(rows_to_upsert), 100):
        batch = rows_to_upsert[i:i + 100]
        saved = _sb_upsert_batch(batch)
        total_saved += saved
        print(f"  [{i+len(batch):>4}/{len(rows_to_upsert)}] saved {saved}")

    # 7. Deactivate stocks no longer in the eligible list
    active_symbols = {r["symbol"] for r in rows_to_upsert}
    now_str = now
    deactivated = 0
    for sym, rec in existing.items():
        if sym not in active_symbols:
            # Mark inactive (may have fallen below market cap threshold)
            try:
                hdr = _sb_headers()
                hdr["Prefer"] = "return=minimal"
                data = json.dumps({"is_active": False, "last_updated": now_str}).encode()
                req = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/stock_universe?symbol=eq.{sym}",
                    data=data, headers=hdr, method="PATCH"
                )
                with urllib.request.urlopen(req, timeout=8):
                    pass
                deactivated += 1
            except Exception:
                pass

    # 8. Sync UNIVERSE watchlist — upsert all active stocks as watchlist items
    _sync_universe_watchlist(rows_to_upsert, now)

    print(f"\n{'='*64}")
    print(f"Done — {total_saved} upserted, {deactivated} deactivated")
    print(f"Active universe size: {len(rows_to_upsert)}")


# ── Universe Watchlist Sync ───────────────────────────────────────────────────

UNIVERSE_WL_ID = "bbbbbbbb-0000-0000-0000-000000000001"  # matches migration 009 seed


def _sync_universe_watchlist(stocks: list[dict], now: str) -> None:
    """
    Keep the 'Universe' watchlist in sync with the active stock_universe.
    Upserts all active stocks as watchlist items (batch of 100).
    Removes items no longer in the active universe.
    """
    if not (SUPABASE_URL and SUPABASE_KEY):
        return

    print(f"\n[WL] Syncing Universe watchlist ({len(stocks)} stocks)…")

    headers = _sb_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    synced = 0

    for i in range(0, len(stocks), 100):
        batch = stocks[i:i + 100]
        wl_items = [
            {
                "watchlist_id":  UNIVERSE_WL_ID,
                "symbol":        s["symbol"],
                "ticker":        s["ticker"],
                "company":       s["company"],
                "sector":        s.get("sector", ""),
                "industry":      s.get("industry", ""),
                "added_reason":  "universe",
                "notes":         f"Market cap ₹{s['market_cap_cr']:,.0f} Cr | {s.get('exchange','NSE')}",
            }
            for s in batch
        ]
        data = json.dumps(wl_items, default=str).encode()
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/watchlist_items",
            data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
            synced += len(batch)
        except Exception as e:
            print(f"  [WL] batch {i} failed: {e}")

    print(f"  ✓ Synced {synced} stocks to Universe watchlist")

    # Remove items whose symbols are no longer in active universe
    active_symbols = {s["symbol"] for s in stocks}
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/watchlist_items"
            f"?watchlist_id=eq.{UNIVERSE_WL_ID}&select=symbol&limit=10000",
            headers=_sb_headers()
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            existing_items = json.loads(r.read())
        stale = [row["symbol"] for row in existing_items if row["symbol"] not in active_symbols]
        removed = 0
        for sym in stale:
            try:
                del_headers = _sb_headers()
                del_headers["Prefer"] = "return=minimal"
                req2 = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/watchlist_items"
                    f"?watchlist_id=eq.{UNIVERSE_WL_ID}&symbol=eq.{sym}",
                    headers=del_headers, method="DELETE"
                )
                with urllib.request.urlopen(req2, timeout=8):
                    pass
                removed += 1
            except Exception:
                pass
        if removed:
            print(f"  ✓ Removed {removed} stale stocks from Universe watchlist")
    except Exception as e:
        print(f"  [WL] cleanup failed: {e}")


if __name__ == "__main__":
    main()
    sys.exit(0)
