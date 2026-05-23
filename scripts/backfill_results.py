"""
Backfill Results Pipeline
─────────────────────────
Fetches ALL BSE quarterly result filings from FROM_DATE to today,
processes them through the full pipeline (PDF → DeepSeek → rating → Supabase → watchlists).

Designed to run once via GitHub Actions workflow_dispatch to populate
historical results from May 1st 2026 onwards.

Environment:
  FROM_DATE          start date, YYYY-MM-DD (default: 2026-05-01)
  TO_DATE            end date,   YYYY-MM-DD (default: today)
  MAX_PROCESS        max filings to process per run (default: 60)
  SUPABASE_URL       required
  SUPABASE_KEY       required
  NVIDIA_API_KEY     primary LLM
  OPENROUTER_API_KEY fallback LLM
  TELEGRAM_BOT_TOKEN optional, for alerts
  TELEGRAM_CHAT_ID   optional
"""
from __future__ import annotations

import importlib
import os
import sys
import time
from datetime import datetime, timezone, date, timedelta

# Reuse all logic from results_pipeline (same module, no duplication)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.results_pipeline as rp

# ── Config ────────────────────────────────────────────────────────────────────
FROM_DATE    = os.getenv("FROM_DATE", "2026-05-01")
TO_DATE      = os.getenv("TO_DATE", date.today().isoformat())
MAX_PROCESS  = int(os.getenv("MAX_PROCESS", "60"))
PAGES        = int(os.getenv("BSE_PAGES", "20"))   # 20 pages ≈ 400-500 announcements

# ── Date filtering helper ─────────────────────────────────────────────────────

def _is_in_range(dt_str: str, from_date: str, to_date: str) -> bool:
    """BSE DT_TM format: '20260523120000' or '2026-05-23 12:00:00'"""
    if not dt_str:
        return False
    try:
        # Normalise: strip non-digits and take first 8 chars as YYYYMMDD
        clean = dt_str.replace("-", "").replace(" ", "").replace(":", "")[:8]
        filing_dt = datetime.strptime(clean, "%Y%m%d").date()
        from_d = date.fromisoformat(from_date)
        to_d   = date.fromisoformat(to_date)
        return from_d <= filing_dt <= to_d
    except Exception:
        return True  # if we can't parse, include it


def main() -> None:
    print("=" * 64)
    print(f"Backfill Results Pipeline  {datetime.now(timezone.utc).isoformat()}")
    print(f"Date range  : {FROM_DATE}  →  {TO_DATE}")
    print(f"Max process : {MAX_PROCESS}  |  BSE pages: {PAGES}")
    print("=" * 64)

    # 1. Fetch more BSE pages to cover the full date range
    print(f"\n[1] Fetching {PAGES} pages of BSE announcements…")
    raw_items = rp._fetch_bse_filings(pages=PAGES)
    print(f"    Got {len(raw_items)} announcements")

    # 2. Filter to results filings in date range
    results_items = [
        it for it in raw_items
        if rp._is_results_filing(it) and _is_in_range(
            it.get("DT_TM", ""), FROM_DATE, TO_DATE
        )
    ]
    print(f"    {len(results_items)} match results categories in date range")

    if not results_items:
        print("    Nothing to backfill.")
        return

    # 3. Load already-processed filing IDs
    print("\n[2] Loading processed filing IDs from Supabase…")
    processed = rp._get_processed_filing_ids()
    print(f"    {len(processed)} already processed")

    # 4. Filter to new ones
    new_items = []
    for it in results_items:
        attachment = it.get("ATTACHMENTNAME", "").strip()
        filing_id  = attachment or f"{it.get('SCRIP_CD','')}_{it.get('DT_TM','')}"
        if filing_id and filing_id not in processed:
            new_items.append((it, filing_id))

    print(f"    {len(new_items)} new filings to process")
    if not new_items:
        print("    All up-to-date.")
        return

    # 5. Process (up to MAX_PROCESS — no 8-item limit during backfill)
    processed_count = 0
    for it, filing_id in new_items[:MAX_PROCESS]:
        company    = it.get("SHORT_NAME", "Unknown").title()
        scrip_code = str(it.get("SCRIP_CD", ""))
        headline   = it.get("NEWSSUB", "")
        category   = it.get("CATEGORYNAME", "Financial Results")
        dt         = it.get("DT_TM", "")
        attachment = it.get("ATTACHMENTNAME", "")
        pdf_url    = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}" if attachment else ""

        symbol = rp._scrip_to_symbol(scrip_code, company)
        print(f"\n  [{processed_count+1}/{min(len(new_items), MAX_PROCESS)}] {company} ({symbol}) | {dt[:16]}")
        print(f"    {headline[:80]}")

        # PDF extraction
        pdf_text = rp._extract_pdf_text(pdf_url) if pdf_url else ""
        if pdf_text:
            print(f"    PDF: {len(pdf_text)} chars")

        # AI extraction
        ai = rp._call_nim_deepseek(company, scrip_code, dt, category, headline, pdf_text)
        if not ai:
            print("    AI failed — skipping")
            continue

        # Rating
        rating, rating_note, score = rp._compute_rating(ai)
        ai["rating"]      = rating
        ai["rating_note"] = rating_note
        ai["score"]       = score

        quarter     = ai.get("quarter", "")
        report_date = dt[:10] if len(dt) >= 10 else date.today().isoformat()
        # Normalise report_date format (BSE DT_TM can be "20260523120000")
        if len(report_date) == 8 and report_date.isdigit():
            report_date = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"

        print(f"    {quarter} | {rating} (score {score:.0f}) | sector: {ai.get('sector','?')}")

        # Live price
        price_data = rp._fetch_price(symbol)
        metrics    = rp._build_metrics(ai)
        rev = metrics["sales"]; pat = metrics["pat"]; eps = metrics["eps"]
        row_id = f"{scrip_code}_{filing_id[:40].replace('/', '_')}"

        row = {
            "id":             row_id,
            "symbol":         symbol,
            "ticker":         price_data.get("ticker") or f"{symbol}.NS",
            "company":        company,
            "exchange":       "BSE",
            "sector":         ai.get("sector", ""),
            "industry":       ai.get("industry", ""),
            "quarter":        quarter,
            "report_date":    report_date,
            "report_time":    ai.get("report_time", "After Market Hours"),
            "rating":         rating,
            "rating_note":    rating_note,
            "insight":        ai.get("insight", ""),
            "metrics":        metrics,
            "revenue_trend":  [rev["q1"], rev["q2"], rev["q3"]],
            "pat_trend":      [pat["q1"], pat["q2"], pat["q3"]],
            "eps_trend":      [eps["q1"], eps["q2"], eps["q3"]],
            "quarter_labels": ["Q-2", "Q-1", quarter],
            "cmp":            price_data.get("cmp"),
            "market_cap":     price_data.get("market_cap") or 0,
            "pe":             price_data.get("pe"),
            "currency_unit":  ai.get("currency_unit", "Cr"),
            "pdf_url":        pdf_url,
            "filing_id":      filing_id,
        }

        if rp._upsert_result(row):
            print(f"    ✓ Saved")
            processed_count += 1
        else:
            print(f"    ✗ Save failed")
            continue

        # Auto watchlist (Good/Great/Excellent → Results Radar + quarterly)
        if rating in ("Good", "Great", "Excellent"):
            used_ticker = price_data.get("ticker") or f"{symbol}.NS"
            qwl_id = rp._ensure_quarterly_watchlist(quarter)
            rp._auto_watchlist_add(
                symbol=symbol, ticker=used_ticker, company=company,
                rating=rating, result_date=report_date,
                result_high=rp._fetch_result_day_high(used_ticker, report_date),
                result_volume=rp._fetch_avg_volume(used_ticker),
                sector=ai.get("sector", ""),
                industry=ai.get("industry", ""),
                extra_watchlist_ids=[qwl_id] if qwl_id else [],
            )

        # Telegram only for Excellent/Great during backfill (avoid spam)
        if rating in ("Excellent", "Great"):
            rp._send_telegram(row)

        time.sleep(1.2)  # rate limit NIM API

    print(f"\n{'='*64}")
    print(f"Backfill done — {processed_count} results saved")
    print(f"Remaining unprocessed: {max(0, len(new_items) - MAX_PROCESS)}")
    if len(new_items) > MAX_PROCESS:
        print(f"  → Trigger workflow again to process next batch of {MAX_PROCESS}")


if __name__ == "__main__":
    main()
    sys.exit(0)
