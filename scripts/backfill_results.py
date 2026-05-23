"""
Backfill Results Pipeline
─────────────────────────
Fetches ALL BSE quarterly result filings from FROM_DATE to today using
BSE's date-range API (strSearch=D) — the only mode that reaches historical
filings beyond the last 2-3 days.

Processes: PDF → NIM DeepSeek R1 → deterministic rating → Supabase
→ Results Radar + quarterly watchlists for Good/Great/Excellent.

Run via GitHub Actions → Backfill Results workflow (workflow_dispatch).

Environment:
  FROM_DATE          start date YYYY-MM-DD  (default: 2026-05-01)
  TO_DATE            end date   YYYY-MM-DD  (default: today)
  MAX_PROCESS        max filings to process this run (default: 100)
  WEEK_CHUNK_DAYS    days per BSE API chunk  (default: 7)
  SUPABASE_URL       required
  SUPABASE_KEY       required
  NVIDIA_API_KEY     primary LLM
  OPENROUTER_API_KEY fallback LLM
  TELEGRAM_BOT_TOKEN optional
  TELEGRAM_CHAT_ID   optional
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.results_pipeline as rp

# ── Config ────────────────────────────────────────────────────────────────────
FROM_DATE        = os.getenv("FROM_DATE", "2026-05-01")
TO_DATE          = os.getenv("TO_DATE",   date.today().isoformat())
MAX_PROCESS      = int(os.getenv("MAX_PROCESS",      "100"))
WEEK_CHUNK_DAYS  = int(os.getenv("WEEK_CHUNK_DAYS",  "7"))


# ── Chunked date-range BSE fetch ──────────────────────────────────────────────

def _fetch_all_results_in_range(from_date: str, to_date: str) -> list[dict]:
    """
    Chunk the date range into WEEK_CHUNK_DAYS windows and call BSE's
    date-range API for each window.  This guarantees full coverage because
    BSE page-based search only returns the last ~2 days regardless of page#.
    """
    f = date.fromisoformat(from_date)
    t = date.fromisoformat(to_date)
    all_items: list[dict] = []
    seen: set[str] = set()

    chunk_start = f
    chunk_num   = 0
    while chunk_start <= t:
        chunk_end = min(chunk_start + timedelta(days=WEEK_CHUNK_DAYS - 1), t)
        chunk_num += 1
        print(f"\n  Chunk {chunk_num}: {chunk_start}  →  {chunk_end}")

        raw = rp._fetch_bse_filings_daterange(
            chunk_start.isoformat(),
            chunk_end.isoformat(),
            max_pages=40,   # 40 pages × ~20 items = 800 per week; enough for any week
        )
        print(f"  Chunk {chunk_num}: {len(raw)} raw announcements")

        # Filter to results filings and deduplicate globally
        for item in raw:
            if not rp._is_results_filing(item):
                continue
            key = (item.get("ATTACHMENTNAME", "").strip() or
                   f"{item.get('SCRIP_CD','')}_{item.get('DT_TM','')}")
            if key and key not in seen:
                seen.add(key)
                all_items.append(item)

        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(1.5)   # respectful pause between chunks

    return all_items


def main() -> None:
    print("=" * 68)
    print(f"Backfill Results Pipeline  {datetime.now(timezone.utc).isoformat()}")
    print(f"Date range  : {FROM_DATE}  →  {TO_DATE}")
    print(f"Max process : {MAX_PROCESS}  |  Chunk days: {WEEK_CHUNK_DAYS}")
    print("=" * 68)

    # 1. Fetch all results filings in range (chunked, date-range BSE API)
    print("\n[1] Fetching BSE results filings in date range…")
    results_items = _fetch_all_results_in_range(FROM_DATE, TO_DATE)
    print(f"\n    Total results filings found: {len(results_items)}")

    if not results_items:
        print("    Nothing to backfill — BSE returned no results filings.")
        return

    # 2. Load already-processed filing IDs
    print("\n[2] Loading processed filing IDs from Supabase…")
    processed = rp._get_processed_filing_ids()
    print(f"    {len(processed)} already saved")

    # 3. Filter to new ones
    new_items = []
    for it in results_items:
        attachment = it.get("ATTACHMENTNAME", "").strip()
        filing_id  = attachment or f"{it.get('SCRIP_CD','')}_{it.get('DT_TM','')}"
        if filing_id and filing_id not in processed:
            new_items.append((it, filing_id))

    print(f"    {len(new_items)} new filings to process")
    if not new_items:
        print("    All up-to-date — nothing new to backfill.")
        return

    # 4. Process (oldest-first so quarterly watchlists are created in order)
    new_items.sort(key=lambda x: x[0].get("DT_TM", ""))

    processed_count = 0
    skip_count      = 0

    for it, filing_id in new_items[:MAX_PROCESS]:
        company    = it.get("SHORT_NAME", "Unknown").title()
        scrip_code = str(it.get("SCRIP_CD", ""))
        headline   = it.get("NEWSSUB", "")
        category   = it.get("CATEGORYNAME", "Financial Results")
        dt         = it.get("DT_TM", "")
        attachment = it.get("ATTACHMENTNAME", "")
        pdf_url    = (
            f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}"
            if attachment else ""
        )

        symbol = rp._scrip_to_symbol(scrip_code, company)
        idx    = processed_count + skip_count + 1
        total  = min(len(new_items), MAX_PROCESS)
        print(f"\n  [{idx}/{total}] {company} ({symbol}) | {dt[:10]}")
        print(f"    {headline[:90]}")

        # PDF extraction
        pdf_text = rp._extract_pdf_text(pdf_url) if pdf_url else ""
        if pdf_text:
            print(f"    PDF: {len(pdf_text)} chars extracted")

        # AI extraction (NIM DeepSeek R1 → OpenRouter fallback)
        ai = rp._call_nim_deepseek(company, scrip_code, dt, category, headline, pdf_text)
        if not ai:
            print("    AI extraction failed — skipping")
            skip_count += 1
            continue

        # Rating
        rating, rating_note, score = rp._compute_rating(ai)
        ai["rating"]      = rating
        ai["rating_note"] = rating_note
        ai["score"]       = score

        quarter = ai.get("quarter", "")

        # Normalise report_date from BSE DT_TM format ("20260523120000" or "2026-05-23 ...")
        raw_dt      = dt[:10] if len(dt) >= 10 else date.today().isoformat()
        report_date = raw_dt.replace(" ", "-")
        if len(report_date) == 8 and report_date.isdigit():
            report_date = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"

        print(f"    {quarter} | {rating} (score {score:.0f}) | sector: {ai.get('sector','?')}")

        # Live price
        price_data = rp._fetch_price(symbol)
        metrics    = rp._build_metrics(ai)
        rev = metrics["sales"]
        pat = metrics["pat"]
        eps = metrics["eps"]
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

        if not rp._upsert_result(row):
            print("    ✗ Supabase save failed — skipping")
            skip_count += 1
            continue

        processed_count += 1
        print(f"    ✓ Saved")

        # Auto-watchlist for Good/Great/Excellent
        if rating in ("Good", "Great", "Excellent"):
            used_ticker = price_data.get("ticker") or f"{symbol}.NS"
            qwl_id      = rp._ensure_quarterly_watchlist(quarter)
            rp._auto_watchlist_add(
                symbol=symbol,
                ticker=used_ticker,
                company=company,
                rating=rating,
                result_date=report_date,
                result_high=rp._fetch_result_day_high(used_ticker, report_date),
                result_volume=rp._fetch_avg_volume(used_ticker),
                sector=ai.get("sector", ""),
                industry=ai.get("industry", ""),
                extra_watchlist_ids=[qwl_id] if qwl_id else [],
            )

        # Telegram only for standout results (not every filing)
        if rating in ("Excellent", "Great"):
            rp._send_telegram(row)

        time.sleep(1.5)  # NIM API rate limit

    print(f"\n{'='*68}")
    print(f"Backfill complete — {processed_count} saved, {skip_count} skipped")
    remaining = max(0, len(new_items) - MAX_PROCESS)
    if remaining:
        print(f"  {remaining} filings still pending — trigger workflow again to continue")


if __name__ == "__main__":
    main()
    sys.exit(0)
