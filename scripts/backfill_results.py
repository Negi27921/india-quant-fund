"""
Backfill Results Pipeline
─────────────────────────
Three-strategy fetch for BSE quarterly results in [FROM_DATE, TO_DATE]:

  Strategy A — BSE date-range API (strSearch=D, session cookies)
               Best when GitHub Actions IPs are not blocked.

  Strategy B — BSE page-based API (strSearch=P, many pages)
               Works during IST market hours when the feed is active.
               Workflow scheduled at 10:30 AM + 2:00 PM IST Mon-Fri.

  Strategy C — yfinance quarterly financials (fallback, no BSE needed)
               Iterates NSE universe, compares reported quarters,
               fills the table with real numbers even when BSE API is
               fully unreachable (nights, weekends, IP blocks).

Run via GitHub Actions → Backfill Results workflow.
  • Scheduled: Mon-Fri 10:30 AM + 2:00 PM IST automatically
  • Manual: workflow_dispatch with from_date / max_process inputs

Environment:
  FROM_DATE          start date YYYY-MM-DD  (default: 2026-05-01)
  TO_DATE            end date   YYYY-MM-DD  (default: today)
  MAX_PROCESS        max filings to process this run (default: 100)
  WEEK_CHUNK_DAYS    days per BSE API chunk  (default: 7)
  USE_YFINANCE       set to "true" to force Strategy C even if A/B succeed
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
FROM_DATE        = os.getenv("FROM_DATE",     "").strip() or "2026-05-01"
TO_DATE          = os.getenv("TO_DATE",       "").strip() or date.today().isoformat()
MAX_PROCESS      = int(os.getenv("MAX_PROCESS",      "100"))
WEEK_CHUNK_DAYS  = int(os.getenv("WEEK_CHUNK_DAYS",  "7"))
USE_YFINANCE     = os.getenv("USE_YFINANCE",  "").strip().lower() == "true"


# ── BSE results fetch with automatic fallback ────────────────────────────────

def _date_in_range(dt_str: str, from_date: str, to_date: str) -> bool:
    """Return True if a BSE DT_TM string falls within [from_date, to_date]."""
    if not dt_str:
        return True   # can't parse → include
    try:
        clean = dt_str.replace("-", "").replace(" ", "").replace(":", "")[:8]
        filing_dt = datetime.strptime(clean, "%Y%m%d").date()
        return date.fromisoformat(from_date) <= filing_dt <= date.fromisoformat(to_date)
    except Exception:
        return True


def _dedup_items(raw: list[dict], seen: set[str], require_results: bool = True) -> list[dict]:
    """Deduplicate filing items using ATTACHMENTNAME or SCRIP_CD+DT_TM as key."""
    out = []
    for item in raw:
        if require_results and not rp._is_results_filing(item):
            continue
        key = (item.get("ATTACHMENTNAME", "").strip() or
               f"{item.get('SCRIP_CD','')}_{item.get('DT_TM','')}")
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _fetch_all_results_in_range(from_date: str, to_date: str) -> list[dict]:
    """
    Fetch every results filing in [from_date, to_date].

    Strategy A — NSE corporate-announcements API (primary)
                 No bot-protection, direct PDFs, always works.
    Strategy B — BSE date-range API with session cookies
                 Good when GitHub Actions IPs not blocked by Cloudflare.
    Strategy C — BSE page-based feed
                 Works during IST market hours only.

    Returns from whichever strategy first yields results.
    Multiple strategies are tried and their results merged.
    """
    from_d = date.fromisoformat(from_date)
    to_d   = date.fromisoformat(to_date)
    days   = (to_d - from_d).days + 1
    seen: set[str] = set()
    all_items: list[dict] = []

    # ── Strategy A: NSE API ─────────────────────────────────────────────────
    print("\n  [A] NSE corporate-announcements API…")
    nse_items = rp._fetch_nse_results(from_date, to_date)
    nse_deduped = _dedup_items(nse_items, seen, require_results=False)
    if nse_deduped:
        print(f"  [A] NSE: {len(nse_deduped)} results filings")
        all_items.extend(nse_deduped)

    # ── Strategy B: BSE date-range API (with session cookies) ──────────────
    print("\n  [B] BSE date-range API (strSearch=D, session cookies)…")
    bse_dr_items: list[dict] = []
    chunk_start = from_d
    chunk_num   = 0
    while chunk_start <= to_d:
        chunk_end  = min(chunk_start + timedelta(days=WEEK_CHUNK_DAYS - 1), to_d)
        chunk_num += 1
        print(f"    Chunk {chunk_num}: {chunk_start} → {chunk_end}")
        raw = rp._fetch_bse_filings_daterange(
            chunk_start.isoformat(), chunk_end.isoformat(), max_pages=30
        )
        bse_dr_items.extend(_dedup_items(raw, seen))
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(1.0)
    if bse_dr_items:
        print(f"  [B] BSE date-range: +{len(bse_dr_items)} additional filings")
        all_items.extend(bse_dr_items)

    # ── Strategy C: BSE page-based (market hours only) ─────────────────────
    if not all_items:
        pages_needed = max(50, int(days * 150 / 20 * 1.2))
        pages_needed = min(pages_needed, 600)
        print(f"\n  [C] BSE page-based ({pages_needed} pages)…")
        raw_all = rp._fetch_bse_filings(pages=pages_needed)
        pb_items = []
        for item in _dedup_items(raw_all, seen):
            if _date_in_range(item.get("DT_TM", ""), from_date, to_date):
                pb_items.append(item)
        if pb_items:
            print(f"  [C] Page-based: +{len(pb_items)} filings (from {len(raw_all)} total)")
            all_items.extend(pb_items)
        else:
            print(f"  [C] Page-based: 0 in range (BSE feed has {len(raw_all)} items, likely off-hours)")

    print(f"\n  Total results filings found: {len(all_items)}")
    return all_items


# ── Strategy C: yfinance quarterly financials ─────────────────────────────────

def _quarter_label(period_end: "date") -> str:
    """Convert a period-end date (yfinance) to 'Q1 FY2027' notation."""
    y = period_end.year
    m = period_end.month
    # Indian FY: Apr-Jun = Q1, Jul-Sep = Q2, Oct-Dec = Q3, Jan-Mar = Q4
    if m <= 3:
        return f"Q4 FY{y}"
    elif m <= 6:
        return f"Q1 FY{y + 1}"
    elif m <= 9:
        return f"Q2 FY{y + 1}"
    else:
        return f"Q3 FY{y + 1}"


def _period_in_range(period_end: "date", from_date: str, to_date: str) -> bool:
    from_d = date.fromisoformat(from_date)
    to_d   = date.fromisoformat(to_date)
    # Allow a 90-day window before from_date for result-day detection
    return (from_d - timedelta(days=90)) <= period_end <= to_d


def _fetch_yfinance_results(from_date: str, to_date: str,
                              max_tickers: int = 500) -> list[dict]:
    """
    Strategy C: Pull quarterly financials from yfinance for the NSE universe.
    Returns BSE-style filing dicts (synthetic) with real revenue/PAT/EPS data.
    Only includes companies whose most-recent quarterly period ends within range.
    """
    try:
        import yfinance as yf
        from api.full_universe import FULL_NSE_TICKERS
    except ImportError as e:
        print(f"  [C] Import failed: {e}")
        return []

    print(f"\n  [C] yfinance strategy — scanning up to {max_tickers} NSE tickers")
    results: list[dict] = []
    errors  = 0
    from_d  = date.fromisoformat(from_date)
    to_d    = date.fromisoformat(to_date)

    # Work through the universe; limit to max_tickers per run so we don't time out
    tickers = FULL_NSE_TICKERS[:max_tickers]
    for i, ticker in enumerate(tickers, 1):
        if i % 50 == 0:
            print(f"    [C] {i}/{len(tickers)} scanned, {len(results)} found so far")
        try:
            tkr = yf.Ticker(ticker)
            qf  = tkr.quarterly_financials  # DataFrame: cols=periods, rows=line items
            if qf is None or qf.empty:
                continue

            # Most recent quarter
            period_end = qf.columns[0]
            if hasattr(period_end, "date"):
                period_end = period_end.date()
            elif not isinstance(period_end, date):
                period_end = date.fromisoformat(str(period_end)[:10])

            # Only keep if this quarter was recently reported (likely filed in range)
            # We use a wide window: period ends within 120 days before to_date
            earliest = to_d - timedelta(days=120)
            if not (earliest <= period_end <= to_d):
                continue

            # Extract financials
            def _val(label: str) -> float | None:
                for row_label in qf.index:
                    if label.lower() in str(row_label).lower():
                        v = qf.loc[row_label, qf.columns[0]]
                        if v is not None and str(v) not in ("nan", "None", ""):
                            return float(v) / 1e7  # convert ₹ to Crores (1 Cr = 1e7)
                return None

            def _val_prev(label: str) -> float | None:
                if len(qf.columns) < 2:
                    return None
                for row_label in qf.index:
                    if label.lower() in str(row_label).lower():
                        v = qf.loc[row_label, qf.columns[1]]
                        if v is not None and str(v) not in ("nan", "None", ""):
                            return float(v) / 1e7
                return None

            rev_cr      = _val("total revenue") or _val("revenue")
            pat_cr      = _val("net income") or _val("net profit")
            rev_prev_q  = _val_prev("total revenue") or _val_prev("revenue")
            pat_prev_q  = _val_prev("net income") or _val_prev("net profit")

            if pat_cr is None and rev_cr is None:
                continue

            # YoY: look 4 quarters back
            rev_prev_y = pat_prev_y = None
            if len(qf.columns) >= 5:
                def _val_yoy(label: str) -> float | None:
                    for row_label in qf.index:
                        if label.lower() in str(row_label).lower():
                            v = qf.loc[row_label, qf.columns[4]]
                            if v is not None and str(v) not in ("nan", "None", ""):
                                return float(v) / 1e7
                    return None
                rev_prev_y = _val_yoy("total revenue") or _val_yoy("revenue")
                pat_prev_y = _val_yoy("net income") or _val_yoy("net profit")

            def _pct(curr: float | None, prev: float | None) -> float | None:
                if curr is None or prev is None or prev == 0:
                    return None
                return round((curr - prev) / abs(prev) * 100, 1)

            symbol     = ticker.replace(".NS", "").replace(".BO", "")
            quarter    = _quarter_label(period_end)
            report_dt  = period_end.isoformat()  # approximate (actual filing may differ)
            scrip_code = ""  # not available from yfinance

            # Build a synthetic BSE-like item dict
            synthetic = {
                "_source":        "yfinance",
                "SCRIP_CD":       scrip_code,
                "SHORT_NAME":     symbol,
                "NEWSSUB":        f"{quarter} Financial Results — yfinance",
                "CATEGORYNAME":   "Financial Results",
                "DT_TM":          report_dt,
                "ATTACHMENTNAME": f"yf_{symbol}_{quarter.replace(' ','_')}",
                "_symbol":        symbol,
                "_ticker":        ticker,
                "_quarter":       quarter,
                "_report_date":   report_dt,
                "_rev_cr":        rev_cr,
                "_pat_cr":        pat_cr,
                "_rev_prev_q":    rev_prev_q,
                "_rev_prev_y":    rev_prev_y,
                "_pat_prev_q":    pat_prev_q,
                "_pat_prev_y":    pat_prev_y,
                "_rev_yoy":       _pct(rev_cr, rev_prev_y),
                "_rev_qoq":       _pct(rev_cr, rev_prev_q),
                "_pat_yoy":       _pct(pat_cr, pat_prev_y),
                "_pat_qoq":       _pct(pat_cr, pat_prev_q),
            }
            results.append(synthetic)

        except Exception as exc:
            errors += 1
            if errors <= 5:
                print(f"    [C] {ticker}: {exc}")
        time.sleep(0.1)

    print(f"  [C] yfinance: {len(results)} quarters found, {errors} errors")
    return results


def _process_yfinance_item(it: dict, filing_id: str) -> dict | None:
    """
    Build a quarterly_results row from a synthetic yfinance item.
    Skips the PDF + LLM step — uses numbers directly.
    """
    symbol     = it["_symbol"]
    ticker     = it["_ticker"]
    quarter    = it["_quarter"]
    report_dt  = it["_report_date"]
    company    = symbol.title()

    rev_cr      = it.get("_rev_cr") or 0
    pat_cr      = it.get("_pat_cr") or 0
    rev_prev_q  = it.get("_rev_prev_q")
    rev_prev_y  = it.get("_rev_prev_y")
    pat_prev_q  = it.get("_pat_prev_q")
    pat_prev_y  = it.get("_pat_prev_y")
    rev_yoy     = it.get("_rev_yoy")
    rev_qoq     = it.get("_rev_qoq")
    pat_yoy     = it.get("_pat_yoy")
    pat_qoq     = it.get("_pat_qoq")

    # EPS from yfinance
    eps_cr = None
    try:
        import yfinance as yf
        tkr   = yf.Ticker(ticker)
        qi    = tkr.quarterly_earnings
        if qi is not None and not qi.empty:
            eps_cr = float(qi.iloc[0].get("EPS", 0) or 0)
    except Exception:
        pass

    ai = {
        "quarter":       quarter,
        "revenue_cr":    rev_cr,
        "pat_cr":        pat_cr,
        "eps":           eps_cr,
        "revenue_yoy":   rev_yoy,
        "revenue_qoq":   rev_qoq,
        "pat_yoy":       pat_yoy,
        "pat_qoq":       pat_qoq,
        "revenue_prev_q": rev_prev_q,
        "revenue_prev_y": rev_prev_y,
        "pat_prev_q":    pat_prev_q,
        "pat_prev_y":    pat_prev_y,
        "sector":        "",
        "industry":      "",
        "insight":       f"Data sourced from yfinance quarterly financials. AI analysis not available.",
        "report_time":   "After Market Hours",
        "currency_unit": "Cr",
    }

    rating, rating_note, score = rp._compute_rating(ai)
    ai["rating"]      = rating
    ai["rating_note"] = rating_note
    ai["score"]       = score

    price_data = rp._fetch_price(symbol)
    metrics    = rp._build_metrics(ai)
    rev = metrics["sales"]
    pat = metrics["pat"]
    eps = metrics["eps"]

    row_id = f"yf_{symbol}_{quarter.replace(' ','_')}"
    return {
        "id":             row_id,
        "symbol":         symbol,
        "ticker":         price_data.get("ticker") or ticker,
        "company":        company,
        "exchange":       "NSE",
        "sector":         "",
        "industry":       "",
        "quarter":        quarter,
        "report_date":    report_dt,
        "report_time":    "After Market Hours",
        "rating":         rating,
        "rating_note":    rating_note,
        "score":          score,
        "insight":        ai["insight"],
        "metrics":        metrics,
        "revenue_trend":  [rev["q1"], rev["q2"], rev["q3"]],
        "pat_trend":      [pat["q1"], pat["q2"], pat["q3"]],
        "eps_trend":      [eps["q1"], eps["q2"], eps["q3"]],
        "quarter_labels": ["Q-2", "Q-1", quarter],
        "cmp":            price_data.get("cmp"),
        "market_cap":     price_data.get("market_cap") or 0,
        "pe":             price_data.get("pe"),
        "currency_unit":  "Cr",
        "pdf_url":        "",
        "filing_id":      filing_id,
    }


def _process_and_save_bse_items(new_items: list[tuple[dict, str]]) -> tuple[int, int]:
    """Process BSE filing items through PDF → AI → rating → Supabase. Returns (saved, skipped)."""
    processed_count = 0
    skip_count      = 0
    total           = min(len(new_items), MAX_PROCESS)

    for it, filing_id in new_items[:MAX_PROCESS]:
        company    = it.get("SHORT_NAME", "Unknown").title()
        scrip_code = str(it.get("SCRIP_CD", ""))
        headline   = it.get("NEWSSUB", "")
        category   = it.get("CATEGORYNAME", "Financial Results")
        dt         = it.get("DT_TM", "")
        attachment = it.get("ATTACHMENTNAME", "")
        source     = it.get("_source", "bse")

        # NSE items carry a direct PDF URL; BSE items construct it from ATTACHMENTNAME
        if source == "nse":
            pdf_url = it.get("_pdf_url", "")
        else:
            pdf_url = (
                f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}"
                if attachment and not attachment.startswith("nse_") else ""
            )

        # NSE items have the symbol directly; BSE items need scrip → symbol lookup
        if source == "nse" and it.get("_symbol"):
            symbol = it["_symbol"]
        else:
            symbol = rp._scrip_to_symbol(scrip_code, company)
        idx    = processed_count + skip_count + 1
        print(f"\n  [{idx}/{total}] {company} ({symbol}) | {dt[:10]}")
        print(f"    {headline[:90]}")

        pdf_text = rp._extract_pdf_text(pdf_url) if pdf_url else ""
        if pdf_text:
            print(f"    PDF: {len(pdf_text)} chars extracted")

        ai = rp._call_nim_deepseek(company, scrip_code, dt, category, headline, pdf_text)
        if not ai:
            print("    AI extraction failed — skipping")
            skip_count += 1
            continue

        rating, rating_note, score = rp._compute_rating(ai)
        ai["rating"]      = rating
        ai["rating_note"] = rating_note
        ai["score"]       = score

        quarter = ai.get("quarter", "")
        raw_dt  = dt[:10] if len(dt) >= 10 else date.today().isoformat()
        report_date = raw_dt.replace(" ", "-")
        if len(report_date) == 8 and report_date.isdigit():
            report_date = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"

        print(f"    {quarter} | {rating} (score {score:.0f}) | sector: {ai.get('sector','?')}")

        price_data = rp._fetch_price(symbol)
        metrics    = rp._build_metrics(ai)
        rev = metrics["sales"]
        pat = metrics["pat"]
        eps = metrics["eps"]
        row_id = f"{scrip_code}_{filing_id[:40].replace('/', '_')}"

        # Industry hint from NSE item (may be null; AI extraction overrides if available)
        nse_industry = it.get("_industry") or ""
        exchange = "NSE" if source == "nse" else "BSE"

        row = {
            "id":             row_id,
            "symbol":         symbol,
            "ticker":         price_data.get("ticker") or f"{symbol}.NS",
            "company":        company,
            "exchange":       exchange,
            "sector":         ai.get("sector") or "",
            "industry":       ai.get("industry") or nse_industry,
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

        if rating in ("Excellent", "Great"):
            rp._send_telegram(row)

        time.sleep(1.5)

    return processed_count, skip_count


def _process_and_save_yfinance_items(yf_items: list[dict], processed: set[str]) -> tuple[int, int]:
    """Process yfinance synthetic items → rating → Supabase (no AI, no PDF)."""
    saved = 0
    skip  = 0
    total = min(len(yf_items), MAX_PROCESS)

    for it in yf_items[:MAX_PROCESS]:
        filing_id = it.get("ATTACHMENTNAME", "")
        if filing_id in processed:
            continue

        symbol  = it["_symbol"]
        quarter = it["_quarter"]
        idx     = saved + skip + 1
        print(f"\n  [yf {idx}/{total}] {symbol} | {quarter}")

        row = _process_yfinance_item(it, filing_id)
        if not row:
            skip += 1
            continue

        if not rp._upsert_result(row):
            print("    ✗ Supabase save failed")
            skip += 1
            continue

        saved += 1
        print(f"    ✓ Saved  rating={row['rating']} (score {row.get('score', '?')})")

        rating = row["rating"]
        if rating in ("Good", "Great", "Excellent"):
            used_ticker = row.get("ticker") or f"{symbol}.NS"
            qwl_id      = rp._ensure_quarterly_watchlist(quarter)
            rp._auto_watchlist_add(
                symbol=symbol,
                ticker=used_ticker,
                company=row.get("company", symbol),
                rating=rating,
                result_date=row.get("report_date", ""),
                result_high=rp._fetch_result_day_high(used_ticker, row.get("report_date", "")),
                result_volume=rp._fetch_avg_volume(used_ticker),
                sector=row.get("sector", ""),
                industry=row.get("industry", ""),
                extra_watchlist_ids=[qwl_id] if qwl_id else [],
            )

        if rating in ("Excellent", "Great"):
            rp._send_telegram(row)

        time.sleep(0.5)

    return saved, skip


def main() -> None:
    print("=" * 68)
    print(f"Backfill Results Pipeline  {datetime.now(timezone.utc).isoformat()}")
    print(f"Date range  : {FROM_DATE}  →  {TO_DATE}")
    print(f"Max process : {MAX_PROCESS}  |  Chunk days: {WEEK_CHUNK_DAYS}")
    print(f"yfinance forced: {USE_YFINANCE}")
    print("=" * 68)

    # Pre-flight checks
    if not rp.SUPABASE_URL or not rp.SUPABASE_KEY:
        print("FATAL: SUPABASE_URL / SUPABASE_KEY not set")
        sys.exit(1)

    # Load processed IDs upfront (shared by all strategies)
    print("\n[0] Loading processed filing IDs from Supabase…")
    processed = rp._get_processed_filing_ids()
    print(f"    {len(processed)} already saved")

    total_saved   = 0
    total_skipped = 0

    # ── Strategies A + B: BSE API ─────────────────────────────────────────────
    if not USE_YFINANCE:
        if not rp.NVIDIA_API_KEY and not rp.OPENROUTER_KEY:
            print("\nWARNING: No LLM key set — BSE strategies require AI for extraction.")
            print("         Skipping A+B and going straight to Strategy C (yfinance).")
        else:
            print("\n[1] Fetching BSE results filings in date range…")
            results_items = _fetch_all_results_in_range(FROM_DATE, TO_DATE)
            print(f"\n    Total results filings found: {len(results_items)}")

            if results_items:
                new_items = []
                for it in results_items:
                    attachment = it.get("ATTACHMENTNAME", "").strip()
                    filing_id  = attachment or f"{it.get('SCRIP_CD','')}_{it.get('DT_TM','')}"
                    if filing_id and filing_id not in processed:
                        new_items.append((it, filing_id))

                new_items.sort(key=lambda x: x[0].get("DT_TM", ""))
                print(f"    {len(new_items)} new filings to process")

                if new_items:
                    saved, skipped = _process_and_save_bse_items(new_items)
                    total_saved   += saved
                    total_skipped += skipped
                    remaining = max(0, len(new_items) - MAX_PROCESS)
                    if remaining:
                        print(f"\n  {remaining} filings still pending — re-trigger workflow to continue")
            else:
                print("\n  BSE A+B returned 0 results — falling through to Strategy C (yfinance).")

    # ── Strategy C: yfinance (runs when BSE fails OR USE_YFINANCE=true) ────────
    if USE_YFINANCE or total_saved == 0:
        print("\n[C] Strategy C: yfinance quarterly financials…")
        yf_items = _fetch_yfinance_results(FROM_DATE, TO_DATE,
                                            max_tickers=min(MAX_PROCESS * 5, 500))
        if yf_items:
            saved, skipped = _process_and_save_yfinance_items(yf_items, processed)
            total_saved   += saved
            total_skipped += skipped
        else:
            print("  [C] yfinance returned no matching quarters.")

    print(f"\n{'='*68}")
    print(f"Backfill complete — {total_saved} saved, {total_skipped} skipped")


if __name__ == "__main__":
    main()
    sys.exit(0)
