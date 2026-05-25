#!/usr/bin/env python3
"""Workflow 4.1 — Universe Seed (one-shot).

Pages through SI.ai GET /companies until exhausted.
Upserts all rows into dim_company via Supabase service role.
Records a job_run row for observability.

Usage:
    cd india-quant-fund
    python3 scripts/si_universe_seed.py

Expected runtime: ~3-6 minutes for 5,443 companies at 10 req/s with 100/page.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

# Resolve project root
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
logger = logging.getLogger("universe_seed")


def _company_to_row(c) -> dict:
    row = {
        "company_id":        c.id,
        "isin":              c.isin,
        "ticker":            c.ticker,
        "company_name":      c.company_name,
        "company_website":   c.company_website,
        "marketcap_category": c.marketcap_category,
        "bse_scrip_code":    c.bse_code(),
        "nse_symbol":        c.nse_symbol(),
        "source":            "stockinsights",
        "fetched_at":        datetime.now(timezone.utc).isoformat(),
        "updated_at":        datetime.now(timezone.utc).isoformat(),
    }
    if c.industry_info:
        row["macro_sector"]  = c.industry_info.macro
        row["sector"]        = c.industry_info.sector
        row["industry"]      = c.industry_info.industry
        row["basic_industry"] = c.industry_info.basic_industry
    if c.market_snapshot:
        if c.market_snapshot.market_cap:
            row["market_cap_inr_cr"] = c.market_snapshot.market_cap.value
        if c.market_snapshot.prices:
            p = c.market_snapshot.prices
            row["current_price_inr"] = p.current
            row["high_52w_inr"]      = p.high_52w
            row["low_52w_inr"]       = p.low_52w
        if c.market_snapshot.as_of:
            row["prices_as_of"] = c.market_snapshot.as_of.isoformat()
    return row


async def main() -> None:
    # Service key required — anon key is blocked by RLS for writes
    write_key = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
    if not settings.SUPABASE_SERVICE_KEY:
        logger.warning("SUPABASE_SERVICE_KEY not set — falling back to anon key. RLS will block writes.")
    sb = create_client(settings.SUPABASE_URL, write_key)
    si = get_si_client()

    # Open job_run
    job_start = datetime.now(timezone.utc)
    try:
        jr = sb.table("job_run").insert({
            "job_name": "si_universe_seed",
            "start_ts": job_start.isoformat(),
            "status":   "running",
        }).execute()
        job_id = jr.data[0]["id"] if jr.data else None
    except Exception as e:
        logger.warning("Could not create job_run: %s", e)
        job_id = None

    total_upserted = 0
    total_errors   = 0
    page = 1
    BATCH = 100  # Supabase upsert batch size

    try:
        while True:
            companies, total_count = await si.get_companies(page=page, limit=100)
            if not companies:
                break

            rows = []
            for c in companies:
                try:
                    rows.append(_company_to_row(c))
                except Exception as exc:
                    logger.warning("Row build error %s: %s", c.ticker, exc)
                    total_errors += 1

            # Supabase upsert in sub-batches of BATCH
            for i in range(0, len(rows), BATCH):
                chunk = rows[i:i + BATCH]
                try:
                    sb.table("dim_company").upsert(
                        chunk,
                        on_conflict="company_id",
                    ).execute()
                    total_upserted += len(chunk)
                except Exception as exc:
                    err_str = str(exc)
                    logger.error("Upsert error page %d batch %d: %s", page, i, exc)
                    total_errors += len(chunk)
                    if "row-level security" in err_str or "42501" in err_str:
                        logger.critical(
                            "RLS violation — ensure SUPABASE_SERVICE_KEY is set in .env. Aborting."
                        )
                        await si.close()
                        raise SystemExit(1)

            logger.info(
                "Page %d: +%d companies | total %d/%d | errors %d",
                page, len(companies), total_upserted, total_count, total_errors,
            )

            if total_upserted + total_errors >= total_count:
                break
            page += 1

    except Exception as exc:
        logger.exception("Universe seed failed: %s", exc)
        if job_id:
            sb.table("job_run").update({
                "end_ts":   datetime.now(timezone.utc).isoformat(),
                "status":   "failed",
                "rows_out": total_upserted,
                "error":    str(exc)[:500],
            }).eq("id", job_id).execute()
        raise

    # Close job_run
    duration = (datetime.now(timezone.utc) - job_start).total_seconds()
    if job_id:
        sb.table("job_run").update({
            "end_ts":   datetime.now(timezone.utc).isoformat(),
            "status":   "success",
            "rows_in":  total_upserted + total_errors,
            "rows_out": total_upserted,
            "metadata": json.dumps({"duration_s": round(duration, 1), "errors": total_errors}),
        }).eq("id", job_id).execute()

    await si.close()
    logger.info(
        "Universe seed complete: %d upserted, %d errors, %.1fs",
        total_upserted, total_errors, duration,
    )


if __name__ == "__main__":
    asyncio.run(main())
