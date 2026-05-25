#!/usr/bin/env python3
"""Workflow 4.3 — Real-time filings + announcements poller (streaming).

Polls SI.ai every 60 seconds:
  - GET /documents  (document_type=earnings-transcript)
  - GET /documents  (document_type=annual-report)
  - GET /documents/announcement

New items (by id) are:
  1. Upserted to fact_filings / fact_announcements_tagged
  2. Fan-out: Telegram notification for new earnings transcripts
  3. Async: LLM thesis refresh queued (written to job_run for pickup)

Also runs results-calendar sync every 3600s (Workflow 4.4).

Usage:
    cd india-quant-fund
    python3 scripts/si_realtime_poller.py

Run as a long-lived process on Railway/Fly.io or via nohup locally.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Union

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
from core.config import settings
from core.providers.stockinsights import get_si_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("si_poller")

POLL_INTERVAL_S   = 60
CALENDAR_INTERVAL = 3600  # results-calendar refresh


def _iso(dt: Union[datetime, str, None]) -> Union[str, None]:
    """Return ISO string regardless of whether the value is already a string or a datetime."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _quarter_int(q) -> Union[int, None]:
    """Parse SI.ai quarter field to int. Handles 'Q4' → 4, 4 → 4, None → None."""
    if q is None:
        return None
    if isinstance(q, int):
        return q
    s = str(q).strip().upper().lstrip("Q")
    try:
        return int(s)
    except ValueError:
        return None


def _year_int(y) -> Union[int, None]:
    """Parse SI.ai year field safely. Handles int, str, 'null', None."""
    if y is None:
        return None
    if isinstance(y, int):
        return y
    s = str(y).strip()
    if not s or s.lower() in ("null", "none", ""):
        return None
    try:
        return int(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _sb():
    # Service key required — RLS blocks anon key for writes
    write_key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
    return create_client(settings.SUPABASE_URL, write_key)


def _log_job(sb, name: str, rows_in: int, rows_out: int, status: str, error: str = "") -> None:
    try:
        sb.table("job_run").insert({
            "job_name": name,
            "end_ts":   datetime.now(timezone.utc).isoformat(),
            "rows_in":  rows_in,
            "rows_out": rows_out,
            "status":   status,
            "error":    error[:500] if error else None,
        }).execute()
    except Exception as e:
        logger.warning("job_run insert failed: %s", e)


# ---------------------------------------------------------------------------
# Telegram fan-out
# ---------------------------------------------------------------------------

async def _notify_new_transcript(doc) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    import httpx
    text = (
        f"*New Earnings Transcript*\n"
        f"Company: {doc.company_name} ({doc.ticker})\n"
        f"Q{doc.quarter or '-'} FY{doc.year or '-'}\n"
        f"Published: {doc.published_date}\n"
        f"[PDF]({doc.pdf_link})" if doc.pdf_link else ""
    ).strip()
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(url, json={
                "chat_id":    settings.TELEGRAM_CHAT_ID,
                "text":       text,
                "parse_mode": "Markdown",
            })
    except Exception as e:
        logger.warning("Telegram notify failed: %s", e)


async def _notify_new_announcement(ann) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return
    import httpx
    sentiment_emoji = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(
        (ann.ai_insights.sentiment if ann.ai_insights else "") or "", "⚪"
    )
    header = ann.ai_insights.summary_header if ann.ai_insights else ""
    summary = ann.ai_insights.summary_text if ann.ai_insights else ""
    ann_type = ann.ai_insights.announcement_type if ann.ai_insights else ""
    text = (
        f"{sentiment_emoji} *{ann.company_name}* ({ann.ticker})\n"
        f"_{ann_type}_\n"
        f"*{header}*\n"
        f"{summary[:300] if summary else ''}"
    ).strip()
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(url, json={
                "chat_id":    settings.TELEGRAM_CHAT_ID,
                "text":       text,
                "parse_mode": "Markdown",
            })
    except Exception as e:
        logger.warning("Telegram announce failed: %s", e)


# ---------------------------------------------------------------------------
# Poller tasks
# ---------------------------------------------------------------------------

async def _poll_filings(si, sb, seen_ids: set[str]) -> int:
    new_count = 0
    for doc_type in ("earnings-transcript", "annual-report", "quarterly-result", "investor-presentation"):
        try:
            docs, _ = await si.get_filings_feed(document_type=doc_type, limit=50)
        except Exception as exc:
            logger.error("filings-feed %s error: %s", doc_type, exc)
            continue

        new_docs = [d for d in docs if d.id not in seen_ids]
        if not new_docs:
            continue

        rows = []
        for d in new_docs:
            rows.append({
                "filing_id":      d.id,
                "company_id":     d.company_id,
                "ticker":         d.ticker,
                "company_name":   d.company_name,
                "document_type":  d.type or doc_type,
                "fiscal_year":    _year_int(d.year),
                "fiscal_quarter": _quarter_int(d.quarter),
                "published_date": _iso(d.published_date),
                "pdf_link":       d.pdf_link,
                "html_link":      d.html_link,
                "exchange_tickers": json.dumps([e.model_dump() if hasattr(e, 'model_dump') else e for e in (d.exchange_tickers or [])]),
                "source":         "stockinsights",
                "fetched_at":     datetime.now(timezone.utc).isoformat(),
            })

        try:
            sb.table("fact_filings").upsert(rows, on_conflict="filing_id").execute()
            for d in new_docs:
                seen_ids.add(d.id)
                if doc_type == "earnings-transcript":
                    asyncio.create_task(_notify_new_transcript(d))
            new_count += len(new_docs)
            logger.info("Filings [%s]: +%d new", doc_type, len(new_docs))
        except Exception as exc:
            logger.error("filings upsert error: %s", exc)

    return new_count


async def _poll_announcements(si, sb, seen_ids: set[str]) -> int:
    new_count = 0
    try:
        items, _ = await si.get_announcements(limit=100)
    except Exception as exc:
        logger.error("announcements-feed error: %s", exc)
        return 0

    new_items = [a for a in items if a.id not in seen_ids]
    if not new_items:
        return 0

    rows = []
    for a in new_items:
        ai = a.ai_insights
        rows.append({
            "announcement_id":      a.id,
            "company_id":           None,  # resolved via ticker join at query time
            "ticker":               a.ticker,
            "company_name":         a.company_name,
            "announcement_type_id": ai.announcement_type_id if ai else None,
            "announcement_type":    ai.announcement_type   if ai else None,
            "sentiment":            ai.sentiment            if ai else None,
            "summary_header":       ai.summary_header       if ai else None,
            "summary_text":         ai.summary_text         if ai else None,
            "source_link":          a.source_link,
            "published_date":       _iso(a.published_date),
            "exchange_tickers":     json.dumps([e.model_dump() if hasattr(e, 'model_dump') else e for e in (a.exchange_tickers or [])]),
            "source":               "stockinsights",
            "fetched_at":           datetime.now(timezone.utc).isoformat(),
        })

    try:
        sb.table("fact_announcements_tagged").upsert(
            rows, on_conflict="announcement_id"
        ).execute()
        for a in new_items:
            seen_ids.add(a.id)
            asyncio.create_task(_notify_new_announcement(a))
        new_count = len(new_items)
        logger.info("Announcements: +%d new", new_count)
    except Exception as exc:
        logger.error("announcements upsert error: %s", exc)

    return new_count


async def _sync_results_calendar(si, sb) -> None:
    logger.info("Syncing results calendar...")
    upserted = 0
    page = 1
    while True:
        try:
            results, total = await si.get_results_calendar(page=page, limit=100)
        except Exception as exc:
            logger.error("results-calendar page %d error: %s", page, exc)
            break

        if not results:
            break

        rows = []
        for r in results:
            rows.append({
                "ticker":          r.ticker,
                "company_name":    r.company_name,
                "result_date":     _iso(r.result_date),
                "fiscal_year":     r.fiscal_year,
                "fiscal_quarter":  _quarter_int(r.fiscal_quarter),
                "result_type":     r.result_type,
                "raw_data":        json.dumps(r.model_dump(mode="json")),
                "source":          "stockinsights",
                "fetched_at":      datetime.now(timezone.utc).isoformat(),
            })

        try:
            sb.table("fact_results_calendar").upsert(
                rows, on_conflict="ticker,fiscal_year,fiscal_quarter"
            ).execute()
            upserted += len(rows)
        except Exception as exc:
            logger.error("calendar upsert error: %s", exc)

        if upserted >= total or not results:
            break
        page += 1

    logger.info("Results calendar synced: %d rows", upserted)
    _log_job(sb, "si_calendar_sync", upserted, upserted, "success")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run() -> None:
    si = get_si_client()
    sb = _sb()

    seen_filing_ids:      set[str] = set()
    seen_announcement_ids: set[str] = set()
    last_calendar_sync = 0.0

    # Pre-load known IDs to avoid re-alerting on existing data
    try:
        existing = sb.table("fact_filings").select("filing_id").execute()
        seen_filing_ids = {r["filing_id"] for r in (existing.data or [])}
        logger.info("Pre-loaded %d known filing IDs", len(seen_filing_ids))
    except Exception as e:
        logger.warning("Could not pre-load filing IDs: %s", e)

    try:
        existing = sb.table("fact_announcements_tagged").select("announcement_id").execute()
        seen_announcement_ids = {r["announcement_id"] for r in (existing.data or [])}
        logger.info("Pre-loaded %d known announcement IDs", len(seen_announcement_ids))
    except Exception as e:
        logger.warning("Could not pre-load announcement IDs: %s", e)

    logger.info("Poller started. Interval=%ds", POLL_INTERVAL_S)

    import time
    while True:
        tick_start = time.monotonic()

        try:
            f_new = await _poll_filings(si, sb, seen_filing_ids)
            a_new = await _poll_announcements(si, sb, seen_announcement_ids)
            if f_new + a_new:
                _log_job(sb, "si_realtime_poll", f_new + a_new, f_new + a_new, "success")
        except Exception as exc:
            logger.exception("Poll cycle error: %s", exc)
            _log_job(sb, "si_realtime_poll", 0, 0, "failed", str(exc))

        # Calendar sync every hour
        if time.monotonic() - last_calendar_sync >= CALENDAR_INTERVAL:
            try:
                await _sync_results_calendar(si, sb)
                last_calendar_sync = time.monotonic()
            except Exception as exc:
                logger.error("Calendar sync error: %s", exc)

        elapsed = time.monotonic() - tick_start
        sleep_for = max(0, POLL_INTERVAL_S - elapsed)
        logger.debug("Poll cycle %.1fs, sleeping %.1fs", elapsed, sleep_for)
        await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    asyncio.run(run())
