#!/usr/bin/env python3
"""
Screener.in bulk scraper — fetches key fundamentals for all stocks in dim_company.

Scrapes (public, no login required):
  Market Cap, CMP, 52W High/Low, P/E, Book Value, Face Value, EPS (TTM),
  Dividend Yield, ROCE, ROE, Debt/Equity, Current Ratio,
  Sales TTM, Profit TTM, Shareholding (Promoter/FII/DII/Public%)

Rate policy (polite — will not offend screener.in):
  • 1 request per POLL_DELAY seconds  (default 1.5s + ±0.4s jitter)
  • 429/503 → sleep BACKOFF_429 seconds then resume (default 90s)
  • 404       → skip (stock not indexed on screener.in, common for BSE-only / SME)
  • 5xx       → retry up to MAX_RETRIES times with 10s back-off
  • conn err  → retry up to MAX_RETRIES times with 5s back-off

Progress / resume:
  State written to scripts/.screener_progress.json after every batch.
  Re-run the script at any time — already-scraped tickers are skipped.

Output:
  Supabase table: fact_screener_fundamentals  (upsert, conflict on ticker)
  Also patches:   dim_company (market_cap_inr_cr, current_price_inr) in bulk

Usage:
    cd india-quant-fund
    python3 scripts/screener_scraper.py            # resume / start fresh
    python3 scripts/screener_scraper.py --reset    # ignore saved progress, restart
    python3 scripts/screener_scraper.py --dry-run  # scrape but don't write to DB

ETA: ~5,443 stocks × 1.5s ≈ 2.3 hours for a full run.
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
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from core.config import settings

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POLL_DELAY      = 1.5    # seconds between requests (base)
POLL_JITTER     = 0.4    # ± jitter added to POLL_DELAY
BACKOFF_429     = 90     # seconds to sleep on 429 / rate-limit
BACKOFF_5XX     = 10     # seconds to sleep on 5xx
BACKOFF_CONN    = 5      # seconds to sleep on connection error
MAX_RETRIES     = 3      # attempts per ticker before giving up
UPSERT_BATCH    = 50     # rows to accumulate before writing to Supabase
PROGRESS_FILE   = os.path.join(os.path.dirname(__file__), ".screener_progress.json")

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
log = logging.getLogger("screener_scraper")


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _num(text: str) -> Optional[float]:
    """Extract first numeric value from a string. Returns None if not found."""
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
    """Return numeric value from first regex match."""
    m = re.search(pattern, body, flags)
    return _num(m.group(1)) if m else None


def _parse_page(ticker: str, html: str) -> dict[str, Any]:
    """
    Extract all metrics from a screener.in company HTML page.
    Strips HTML tags first, works on plain text for robustness.
    """
    # Strip script/style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>",  " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    row: dict[str, Any] = {"ticker": ticker}

    # ── Key ratios ────────────────────────────────────────────────────────────
    # These appear in the top "key ratios" bar on every company page.

    # Market Cap  e.g. "Market Cap ₹1,23,456 Cr."
    row["market_cap_cr"] = _find(
        r"Market\s*Cap\s*[₹\s]*([\d,]+(?:\.\d+)?)\s*Cr", text)

    # Current Price  e.g. "Current Price ₹1,234"
    row["current_price"] = _find(
        r"Current\s*Price\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)

    # 52W High / Low  e.g. "High / Low 1,456 / 987"
    hl_m = re.search(
        r"High\s*/\s*Low\s*[₹\s]*([\d,]+(?:\.\d+)?)\s*/\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if hl_m:
        row["high_52w"] = _num(hl_m.group(1))
        row["low_52w"]  = _num(hl_m.group(2))

    # Stock P/E
    row["pe_ratio"] = _find(r"Stock\s*P/E\s*([\d,]+(?:\.\d+)?)", text)

    # Book Value
    row["book_value"] = _find(r"Book\s*Value\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)

    # Face Value
    row["face_value"] = _find(r"Face\s*Value\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)

    # Dividend Yield  e.g. "Dividend Yield  1.23 %"
    row["dividend_yield_pct"] = _find(
        r"Dividend\s*Yield\s*([\d,]+(?:\.\d+)?)\s*%", text)

    # ROCE
    row["roce_pct"] = _find(r"ROCE\s*([\d,]+(?:\.\d+)?)\s*%", text)

    # ROE
    row["roe_pct"] = _find(r"\bROE\b\s*([\d,]+(?:\.\d+)?)\s*%", text)

    # Debt to equity
    row["debt_to_equity"] = _find(r"Debt\s*to\s*equity\s*([\d,]+(?:\.\d+)?)", text)

    # Current ratio
    row["current_ratio"] = _find(r"Current\s*ratio\s*([\d,]+(?:\.\d+)?)", text)

    # EPS (TTM)
    row["eps_ttm"] = _find(r"\bEPS\s*(?:\(TTM\))?\s*[₹\s]*([\d,]+(?:\.\d+)?)", text)

    # ── P&L TTM (Cr) ──────────────────────────────────────────────────────────
    # "Sales TTM" / "Revenue TTM" — appears in the P&L section
    sales_m = re.search(
        r"(?:Sales|Revenue)\s*(?:TTM|Trailing).*?([\d,]+(?:\.\d+)?)", text, re.IGNORECASE | re.DOTALL)
    if sales_m:
        row["sales_ttm_cr"] = _num(sales_m.group(1))

    profit_m = re.search(
        r"(?:Net\s*Profit|Profit\s*after\s*tax|PAT)\s*(?:TTM|Trailing).*?([\d,]+(?:\.\d+)?)",
        text, re.IGNORECASE | re.DOTALL)
    if profit_m:
        row["profit_ttm_cr"] = _num(profit_m.group(1))

    # ── Shareholding ──────────────────────────────────────────────────────────
    # screener.in shows the most-recent quarter shareholding in a summary box.

    promo_m = re.search(
        r"Promoter(?:s|&\s*Promoter\s*Group)?\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%",
        text, re.IGNORECASE)
    if promo_m:
        row["promoter_pct"] = _num(promo_m.group(1))

    pledge_m = re.search(
        r"Pledged\s*%\s*([\d]+(?:\.\d+)?)\s*%",
        text, re.IGNORECASE)
    if pledge_m:
        row["promoter_pledge_pct"] = _num(pledge_m.group(1))

    fii_m = re.search(
        r"(?:FII\s*\+\s*FPI|FII|Foreign\s*Institutional)\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%",
        text, re.IGNORECASE)
    if fii_m:
        row["fii_pct"] = _num(fii_m.group(1))

    dii_m = re.search(
        r"\bDII\b\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%",
        text, re.IGNORECASE)
    if dii_m:
        row["dii_pct"] = _num(dii_m.group(1))

    pub_m = re.search(
        r"\bPublic\b\s*(?:Holding)?\s*[:\-]?\s*([\d]+(?:\.\d+)?)\s*%",
        text, re.IGNORECASE)
    if pub_m:
        row["public_pct"] = _num(pub_m.group(1))

    row["screener_url"] = f"https://www.screener.in/company/{ticker}/"
    row["scraped_at"]   = datetime.now(timezone.utc).isoformat()

    return row


# ---------------------------------------------------------------------------
# HTTP fetch with retry / back-off
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    pass

class NotFoundError(Exception):
    pass


def _fetch_html(ticker: str) -> str:
    """
    Fetch the screener.in company page for ticker.
    Returns raw HTML string.
    Raises RateLimitError, NotFoundError, or RuntimeError on failure.
    """
    url = f"https://www.screener.in/company/{ticker}/"
    ua  = random.choice(USER_AGENTS)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":      ua,
            "Accept":          "text/html,application/xhtml+xml,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",  # avoid gzip decompression hassle
            "Connection":      "keep-alive",
        },
    )
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                if r.status == 200:
                    return r.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"HTTP {r.status}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFoundError(f"{ticker} not found on screener.in")
            if e.code in (429, 503):
                log.warning("[rate-limit] HTTP %d — sleeping %ds", e.code, BACKOFF_429)
                time.sleep(BACKOFF_429)
                raise RateLimitError(f"HTTP {e.code}")
            if e.code >= 500:
                log.debug("[5xx] %s attempt %d: HTTP %d", ticker, attempt, e.code)
                time.sleep(BACKOFF_5XX)
            else:
                raise RuntimeError(f"HTTP {e.code}: {e.reason}")
        except (urllib.error.URLError, OSError) as e:
            log.debug("[conn] %s attempt %d: %s", ticker, attempt, e)
            time.sleep(BACKOFF_CONN)

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {ticker}")


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def _load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        try:
            return json.load(open(PROGRESS_FILE))
        except Exception:
            pass
    return {"done": [], "skipped": [], "failed": [], "started_at": datetime.now(timezone.utc).isoformat()}


def _save_progress(state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(PROGRESS_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _get_all_tickers(sb) -> list[dict]:
    """Return all {ticker, company_id} rows from dim_company, paged."""
    rows: list[dict] = []
    page_size = 1000
    start = 0
    while True:
        res = (
            sb.table("dim_company")
            .select("ticker,company_id")
            .range(start, start + page_size - 1)
            .order("ticker")
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def _upsert_batch(sb, rows: list[dict], dry_run: bool) -> int:
    """Upsert a batch of scraped rows to fact_screener_fundamentals."""
    if not rows:
        return 0
    if dry_run:
        log.info("[dry-run] would upsert %d rows", len(rows))
        return len(rows)
    try:
        sb.table("fact_screener_fundamentals").upsert(
            rows, on_conflict="ticker"
        ).execute()
        return len(rows)
    except Exception as e:
        log.error("[upsert] batch failed: %s", e)
        return 0


def _patch_dim_company(sb, rows: list[dict], dry_run: bool) -> None:
    """Update market_cap_inr_cr + current_price_inr in dim_company for rows that have values."""
    for r in rows:
        updates: dict = {}
        if r.get("market_cap_cr") is not None:
            updates["market_cap_inr_cr"] = r["market_cap_cr"]
        if r.get("current_price") is not None:
            updates["current_price_inr"] = r["current_price"]
        if not updates:
            continue
        if dry_run:
            continue
        try:
            sb.table("dim_company").update(updates).eq("ticker", r["ticker"]).execute()
        except Exception:
            pass  # non-critical; fact_screener_fundamentals is the source of truth


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, reset: bool = False) -> None:
    sb = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY,
    )

    # Load / reset progress
    state   = {"done": [], "skipped": [], "failed": [], "started_at": datetime.now(timezone.utc).isoformat()} if reset else _load_progress()
    done    = set(state["done"])
    skipped = set(state["skipped"])
    failed  = set(state["failed"])

    # Fetch universe
    log.info("Fetching universe from dim_company…")
    universe = _get_all_tickers(sb)
    cid_map  = {r["ticker"]: r["company_id"] for r in universe}
    all_tickers = [r["ticker"] for r in universe]
    pending  = [t for t in all_tickers if t not in done and t not in skipped]

    log.info(
        "Universe: %d total | %d done | %d skipped | %d failed | %d pending",
        len(all_tickers), len(done), len(skipped), len(failed), len(pending),
    )

    if not pending:
        log.info("All tickers already scraped. Use --reset to re-scrape.")
        return

    batch:  list[dict] = []
    stored: int = 0
    errors: int = 0

    for idx, ticker in enumerate(pending, 1):
        # ── Throttle ─────────────────────────────────────────────────────────
        sleep_for = POLL_DELAY + random.uniform(-POLL_JITTER, POLL_JITTER)
        time.sleep(max(0.5, sleep_for))

        # ── Fetch with back-off loop (handles transient rate limits) ─────────
        html: Optional[str] = None
        for _retry in range(MAX_RETRIES):
            try:
                html = _fetch_html(ticker)
                break
            except NotFoundError:
                log.debug("[skip] %s: not on screener.in", ticker)
                skipped.add(ticker)
                html = None
                break
            except RateLimitError:
                # Back-off already applied inside _fetch_html; retry outer loop
                log.info("[backoff] retrying %s after rate-limit sleep", ticker)
                continue
            except RuntimeError as e:
                log.warning("[error] %s: %s", ticker, e)
                errors += 1
                failed.add(ticker)
                html = None
                break

        if html is None:
            # Progress checkpoint every batch
            if idx % UPSERT_BATCH == 0:
                _save_progress({"done": list(done), "skipped": list(skipped), "failed": list(failed),
                                "started_at": state["started_at"]})
            continue

        # ── Parse ────────────────────────────────────────────────────────────
        row = _parse_page(ticker, html)
        row["company_id"] = cid_map.get(ticker)

        # Sanity check: skip if we extracted nothing meaningful
        has_data = any(
            row.get(k) is not None
            for k in ("market_cap_cr", "pe_ratio", "roe_pct", "roce_pct", "current_price")
        )
        if not has_data:
            log.debug("[empty] %s: no ratios extracted, skipping", ticker)
            skipped.add(ticker)
        else:
            batch.append(row)
            done.add(ticker)

        # ── Batch upsert ─────────────────────────────────────────────────────
        if len(batch) >= UPSERT_BATCH:
            n = _upsert_batch(sb, batch, dry_run)
            _patch_dim_company(sb, batch, dry_run)
            stored += n
            log.info(
                "[progress] %d/%d | stored=%d | skipped=%d | errors=%d | ETA ~%.0fm",
                idx, len(pending), stored,
                len(skipped), errors,
                (len(pending) - idx) * POLL_DELAY / 60,
            )
            batch.clear()
            _save_progress({"done": list(done), "skipped": list(skipped), "failed": list(failed),
                            "started_at": state["started_at"]})

    # ── Final flush ───────────────────────────────────────────────────────────
    if batch:
        n = _upsert_batch(sb, batch, dry_run)
        _patch_dim_company(sb, batch, dry_run)
        stored += n
        batch.clear()

    _save_progress({"done": list(done), "skipped": list(skipped), "failed": list(failed),
                    "started_at": state["started_at"],
                    "completed_at": datetime.now(timezone.utc).isoformat()})

    log.info(
        "Done. stored=%d | skipped=%d | failed=%d | total=%d",
        stored, len(skipped), len(failed), len(all_tickers),
    )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screener.in bulk scraper")
    parser.add_argument("--reset",   action="store_true", help="Ignore saved progress and restart from scratch")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but do not write to Supabase")
    args = parser.parse_args()
    run(dry_run=args.dry_run, reset=args.reset)
