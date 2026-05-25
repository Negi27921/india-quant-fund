#!/usr/bin/env python3
"""
Screener.in biweekly refresh — LLM-guided incremental re-scraper.

What it does:
  1. Pulls all rows from fact_screener_fundamentals older than STALE_DAYS.
  2. Sends a representative sample (top 200 by market cap) to Claude which
     identifies stocks with material changes that warrant priority re-scraping
     (promoter pledge spike, PE/ROE anomaly, dramatic cap change, etc.).
  3. Re-scrapes priority stocks first, then all stale rows.
  4. Upserts updated rows into fact_screener_fundamentals and patches dim_company.
  5. Runs universe expansion: tickers in fact_screener_fundamentals not yet in
     dim_company are inserted so the investable universe grows automatically.

Schedule: run via GitHub Actions on a biweekly cron (see screener_biweekly.yml).

Usage:
    python3 scripts/screener_refresh.py                  # refresh stale (>14d) rows
    python3 scripts/screener_refresh.py --days 30        # custom staleness threshold
    python3 scripts/screener_refresh.py --dry-run        # no DB writes
    python3 scripts/screener_refresh.py --priority-only  # LLM-flagged stocks only
    python3 scripts/screener_refresh.py --reset          # re-scrape everything
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

# ── Config ────────────────────────────────────────────────────────────────────

STALE_DAYS      = int(os.getenv("SCREENER_STALE_DAYS", "14"))
POLL_DELAY      = 1.5
POLL_JITTER     = 0.4
BACKOFF_429     = 90
BACKOFF_5XX     = 10
MAX_RETRIES     = 3
UPSERT_BATCH    = 50
LLM_SAMPLE_SIZE = 200   # stocks sent to Claude for change analysis
LLM_MODEL       = "claude-opus-4-7"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("screener_refresh")


# ── Parse helpers (reused from screener_scraper.py) ───────────────────────────

def _num(text: str) -> Optional[float]:
    if not text:
        return None
    clean = re.sub(r"[₹,\s]", "", text)
    m = re.search(r"[-]?[\d]+(?:\.\d+)?", clean)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _find(pattern: str, body: str, flags: int = re.IGNORECASE) -> Optional[float]:
    m = re.search(pattern, body, flags)
    return _num(m.group(1)) if m else None


def _parse_page(ticker: str, html: str) -> dict[str, Any]:
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>",  " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    row: dict[str, Any] = {"ticker": ticker}
    row["market_cap_cr"]     = _find(r"Market\s*Cap\s*[₹\s]*([\d,]+(?:\.\d+)?)\s*Cr", text)
    row["current_price"]     = _find(r"Current\s*Price\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)
    hl = re.search(r"High\s*/\s*Low\s*[₹\s]*([\d,]+(?:\.\d+)?)\s*/\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if hl:
        row["high_52w"] = _num(hl.group(1))
        row["low_52w"]  = _num(hl.group(2))
    row["pe_ratio"]          = _find(r"Stock\s*P/E\s*([\d,]+(?:\.\d+)?)", text)
    row["book_value"]        = _find(r"Book\s*Value\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)
    row["face_value"]        = _find(r"Face\s*Value\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)
    row["dividend_yield_pct"]= _find(r"Dividend\s*Yield\s*([\d,]+(?:\.\d+)?)\s*%", text)
    row["roce_pct"]          = _find(r"ROCE\s*([\d,]+(?:\.\d+)?)\s*%", text)
    row["roe_pct"]           = _find(r"\bROE\b\s*([\d,]+(?:\.\d+)?)\s*%", text)
    row["debt_to_equity"]    = _find(r"Debt\s*to\s*equity\s*([\d,]+(?:\.\d+)?)", text)
    row["current_ratio"]     = _find(r"Current\s*ratio\s*([\d,]+(?:\.\d+)?)", text)
    row["eps_ttm"]           = _find(r"\bEPS\s*(?:\(TTM\))?\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)
    sm = re.search(r"(?:Sales|Revenue)\s*(?:TTM|Trailing).*?([\d,]+(?:\.\d+)?)", text, re.IGNORECASE | re.DOTALL)
    if sm:
        row["sales_ttm_cr"] = _num(sm.group(1))
    pm = re.search(r"(?:Net\s*Profit|PAT)\s*(?:TTM|Trailing).*?([\d,]+(?:\.\d+)?)", text, re.IGNORECASE | re.DOTALL)
    if pm:
        row["profit_ttm_cr"] = _num(pm.group(1))
    for pat, key in [
        (r"Promoter(?:s|&\s*Promoter\s*Group)?\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%", "promoter_pct"),
        (r"Pledged\s*%\s*([\d]+(?:\.\d+)?)\s*%", "promoter_pledge_pct"),
        (r"(?:FII\s*\+\s*FPI|FII|Foreign\s*Institutional)\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%", "fii_pct"),
        (r"\bDII\b\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%", "dii_pct"),
        (r"\bPublic\b\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%", "public_pct"),
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            row[key] = _num(m.group(1))

    row["screener_url"] = f"https://www.screener.in/company/{ticker}/"
    row["scraped_at"]   = datetime.now(timezone.utc).isoformat()
    return row


# ── HTTP fetch ─────────────────────────────────────────────────────────────────

class RateLimitError(Exception):
    pass

class NotFoundError(Exception):
    pass


def _fetch_html(ticker: str) -> str:
    url = f"https://www.screener.in/company/{ticker}/"
    ua  = random.choice(USER_AGENTS)
    req = urllib.request.Request(url, headers={
        "User-Agent":      ua,
        "Accept":          "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Connection":      "keep-alive",
    })
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFoundError(ticker)
            if e.code == 429:
                log.warning("429 rate-limit on %s — sleeping %ds", ticker, BACKOFF_429)
                time.sleep(BACKOFF_429)
                raise RateLimitError(ticker)
            if e.code >= 500:
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_5XX)
                    continue
                raise RuntimeError(f"{ticker}: HTTP {e.code}")
            raise
        except Exception as exc:
            if attempt < MAX_RETRIES:
                time.sleep(5)
                continue
            raise RuntimeError(f"{ticker}: {exc}") from exc
    raise RuntimeError(f"{ticker}: exhausted retries")


# ── Supabase helpers ───────────────────────────────────────────────────────────

def _get_sb():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY env vars not set")
    return create_client(url, key)


def _load_stale(sb, stale_cutoff: datetime, reset: bool) -> list[dict]:
    """Return rows older than stale_cutoff (or all rows if reset)."""
    if reset:
        log.info("--reset: fetching all rows from fact_screener_fundamentals")
        resp = sb.table("fact_screener_fundamentals").select(
            "ticker,market_cap_cr,pe_ratio,roe_pct,roce_pct,promoter_pct,"
            "promoter_pledge_pct,scraped_at"
        ).order("market_cap_cr", desc=True).execute()
    else:
        cutoff_iso = stale_cutoff.isoformat()
        log.info("Fetching rows scraped before %s", cutoff_iso[:10])
        resp = sb.table("fact_screener_fundamentals").select(
            "ticker,market_cap_cr,pe_ratio,roe_pct,roce_pct,promoter_pct,"
            "promoter_pledge_pct,scraped_at"
        ).lt("scraped_at", cutoff_iso).order("market_cap_cr", desc=True).execute()
    rows = resp.data or []
    log.info("Stale rows to refresh: %d", len(rows))
    return rows


# ── LLM change-detection ──────────────────────────────────────────────────────

def _llm_flag_priority(rows: list[dict]) -> list[str]:
    """
    Send top LLM_SAMPLE_SIZE rows to Claude.
    Claude returns a JSON list of tickers that need priority re-scraping.
    Falls back to empty list if Anthropic key is not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set — skipping LLM priority detection")
        return []

    sample = rows[:LLM_SAMPLE_SIZE]
    table_lines = ["ticker | market_cap_cr | pe | roe | roce | promoter% | pledge% | scraped_at"]
    table_lines.append("-" * 90)
    for r in sample:
        table_lines.append(
            f"{r['ticker']:<15} | {r.get('market_cap_cr') or ''!s:<13} | "
            f"{r.get('pe_ratio') or ''!s:<5} | {r.get('roe_pct') or ''!s:<5} | "
            f"{r.get('roce_pct') or ''!s:<5} | {r.get('promoter_pct') or ''!s:<9} | "
            f"{r.get('promoter_pledge_pct') or ''!s:<7} | "
            f"{str(r.get('scraped_at', ''))[:10]}"
        )

    prompt = f"""You are a quant analyst reviewing stale screener.in data for an Indian equity fund.

Below are the top {len(sample)} stocks (sorted by market cap) that need a data refresh.
Identify stocks that MOST URGENTLY need re-scraping due to potential material changes.
Flag stocks where you suspect:
- Promoter pledge > 20% or sudden large increase
- Very high or negative P/E (bubble or loss-making)
- ROE < 5% or ROCE < 8% for large caps (quality deterioration)
- Very large market cap swings likely
- Missing data in key fields (null values)

Return ONLY a JSON array of ticker strings, max 50, in priority order.
Example: ["ADANI", "YESBANK", "ZOMATO"]

Data:
{chr(10).join(table_lines)}

Return JSON array only, no explanation."""

    body = json.dumps({
        "model": LLM_MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        text = data["content"][0]["text"].strip()
        # Extract JSON array from response
        m = re.search(r"\[.*?\]", text, re.DOTALL)
        if m:
            tickers = json.loads(m.group())
            log.info("LLM flagged %d priority tickers: %s", len(tickers), tickers[:10])
            return [t.strip().upper() for t in tickers if isinstance(t, str)]
    except Exception as exc:
        log.warning("LLM priority detection failed: %s", exc)
    return []


# ── Universe expansion ─────────────────────────────────────────────────────────

def _expand_universe(sb, dry_run: bool) -> int:
    """Insert into dim_company any ticker in fact_screener_fundamentals that's missing."""
    log.info("Checking universe expansion…")
    scr_resp = sb.table("fact_screener_fundamentals").select(
        "ticker,market_cap_cr,current_price"
    ).execute()
    scr_tickers = {r["ticker"] for r in (scr_resp.data or [])}

    dim_resp = sb.table("dim_company").select("ticker").execute()
    dim_tickers = {r["ticker"] for r in (dim_resp.data or []) if r.get("ticker")}

    new_tickers = scr_tickers - dim_tickers
    if not new_tickers:
        log.info("Universe already complete — no new tickers to add")
        return 0

    scr_map = {r["ticker"]: r for r in (scr_resp.data or [])}
    new_rows = []
    for t in sorted(new_tickers):
        r = scr_map.get(t, {})
        new_rows.append({
            "company_id":        t,
            "ticker":            t,
            "company_name":      t,
            "exchange":          "NSE",
            "market_cap_inr_cr": r.get("market_cap_cr"),
            "current_price_inr": r.get("current_price"),
            "is_active":         True,
        })

    log.info("Expanding universe by %d new tickers", len(new_rows))
    if dry_run:
        log.info("[dry-run] Would insert: %s…", [r["ticker"] for r in new_rows[:5]])
        return len(new_rows)

    BATCH = 200
    added = 0
    for i in range(0, len(new_rows), BATCH):
        chunk = new_rows[i : i + BATCH]
        sb.table("dim_company").upsert(chunk, on_conflict="ticker", ignore_duplicates=True).execute()
        added += len(chunk)
        log.info("  inserted batch %d/%d (%d rows)", i // BATCH + 1, -(-len(new_rows) // BATCH), len(chunk))
    return added


# ── Patch dim_company with fresh price/cap ────────────────────────────────────

def _patch_dim_company(sb, rows: list[dict], dry_run: bool) -> None:
    updates = [
        {"ticker": r["ticker"], "market_cap_inr_cr": r.get("market_cap_cr"), "current_price_inr": r.get("current_price")}
        for r in rows if r.get("ticker")
    ]
    if not updates or dry_run:
        return
    BATCH = 200
    for i in range(0, len(updates), BATCH):
        sb.table("dim_company").upsert(
            updates[i : i + BATCH], on_conflict="ticker"
        ).execute()


# ── Main refresh loop ──────────────────────────────────────────────────────────

def run(days: int, dry_run: bool, priority_only: bool, reset: bool) -> None:
    sb = _get_sb()
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stale_rows = _load_stale(sb, stale_cutoff, reset)
    if not stale_rows:
        log.info("Nothing stale — all data is fresh. Checking universe expansion.")
        _expand_universe(sb, dry_run)
        return

    stale_tickers = [r["ticker"] for r in stale_rows]

    # LLM priority ordering
    priority = _llm_flag_priority(stale_rows)
    priority_set = set(priority)

    # Ordered queue: priority first, then remaining stale
    queue = priority + [t for t in stale_tickers if t not in priority_set]
    if priority_only:
        queue = priority
        log.info("--priority-only: will refresh %d LLM-flagged tickers", len(queue))

    log.info("Total to refresh: %d tickers", len(queue))

    batch: list[dict] = []
    done = 0
    skip = 0

    for i, ticker in enumerate(queue):
        time.sleep(POLL_DELAY + random.uniform(-POLL_JITTER, POLL_JITTER))
        try:
            html = _fetch_html(ticker)
            row  = _parse_page(ticker, html)
            batch.append(row)
            done += 1
            if done % 50 == 0:
                log.info("Progress: %d/%d refreshed (%d skipped)", done, len(queue), skip)
        except NotFoundError:
            skip += 1
            continue
        except RateLimitError:
            log.warning("Rate limited — pausing %ds then continuing", BACKOFF_429)
            time.sleep(BACKOFF_429)
            continue
        except Exception as exc:
            log.warning("Error scraping %s: %s", ticker, exc)
            skip += 1
            continue

        if len(batch) >= UPSERT_BATCH:
            if not dry_run:
                sb.table("fact_screener_fundamentals").upsert(batch, on_conflict="ticker").execute()
                _patch_dim_company(sb, batch, dry_run)
            else:
                log.info("[dry-run] Would upsert %d rows", len(batch))
            batch.clear()

    # Final flush
    if batch:
        if not dry_run:
            sb.table("fact_screener_fundamentals").upsert(batch, on_conflict="ticker").execute()
            _patch_dim_company(sb, batch, dry_run)
        else:
            log.info("[dry-run] Would upsert %d rows", len(batch))

    log.info("Refresh complete: %d updated, %d skipped", done, skip)

    # Universe expansion after refresh
    added = _expand_universe(sb, dry_run)
    if added:
        log.info("Universe expanded by %d new stocks", added)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screener.in biweekly refresh")
    parser.add_argument("--days",          type=int, default=STALE_DAYS,
                        help=f"Re-scrape rows older than N days (default: {STALE_DAYS})")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Scrape but skip Supabase writes")
    parser.add_argument("--priority-only", action="store_true",
                        help="Only re-scrape LLM-flagged priority stocks")
    parser.add_argument("--reset",         action="store_true",
                        help="Re-scrape all rows regardless of age")
    args = parser.parse_args()
    run(
        days          = args.days,
        dry_run       = args.dry_run,
        priority_only = args.priority_only,
        reset         = args.reset,
    )
