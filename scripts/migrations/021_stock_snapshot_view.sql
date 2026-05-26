-- Migration 021: vw_stock_snapshot — unified read model
-- This is the ONE source of truth for:
--   • AI agents (chat, analysis, watchlist)
--   • Frontend fundamentals tab
--   • Screener / scanner UI
--   • Alert engine
--
-- Sources joined:
--   dim_company           → identity, sector, industry, marketcap_category
--   fact_market_realtime  → live price, volume, pct_change (fast-changing)
--   fact_screener_fundamentals → PE, ROE, ROCE, shareholding (slow-changing)
--
-- CRITICAL: AI models and scanners should query ONLY this view, never the
-- underlying tables directly, so source-of-truth is always consistent.
--
-- Run after 020_market_realtime_schema.sql

CREATE OR REPLACE VIEW vw_stock_snapshot AS
SELECT
    -- ── Identity ────────────────────────────────────────────────────────────
    dc.ticker                                       AS symbol,
    dc.company_name,
    COALESCE(mr.exchange, 'NSE')                    AS exchange,
    dc.sector,
    dc.industry,
    dc.basic_industry,
    dc.macro_sector,
    dc.marketcap_category,
    dc.nse_symbol,
    dc.bse_scrip_code,
    dc.isin,

    -- ── Live market state (fast-changing — from fact_market_realtime) ───────
    mr.ltp,
    mr.prev_close,
    mr.day_open,
    mr.day_high,
    mr.day_low,
    mr.volume,
    mr.volume_cr,
    mr.value_traded_cr,
    mr.delivery_pct,
    mr.pct_change,
    mr.abs_change,
    mr.vwap,
    mr.market_cap_live_cr,
    mr.week_high_52,
    mr.week_low_52,
    mr.pct_from_52w_high,
    mr.upper_circuit,
    mr.lower_circuit,
    mr.market_status,
    mr.last_trade_time,
    mr.updated_at                                   AS market_updated_at,

    -- ── Fundamentals snapshot (slow-changing — from fact_screener_fundamentals) ──
    sf.market_cap_cr                                AS screener_market_cap_cr,
    sf.current_price                                AS screener_price_at_scrape,
    sf.pe_ratio,
    sf.book_value,
    sf.face_value,
    sf.eps_ttm,
    sf.dividend_yield_pct,
    sf.roce_pct,
    sf.roe_pct,
    sf.debt_to_equity,
    sf.current_ratio,
    sf.sales_ttm_cr,
    sf.profit_ttm_cr,
    sf.promoter_pct,
    sf.promoter_pledge_pct,
    sf.fii_pct,
    sf.dii_pct,
    sf.public_pct,
    sf.high_52w                                     AS screener_52w_high,
    sf.low_52w                                      AS screener_52w_low,
    sf.screener_url,
    sf.scraped_at                                   AS fundamentals_scraped_at,

    -- ── Computed / blended fields ────────────────────────────────────────────
    -- Live PE: use live LTP with screener EPS (more accurate than static PE)
    CASE
        WHEN sf.eps_ttm > 0 AND mr.ltp IS NOT NULL
        THEN ROUND(mr.ltp / sf.eps_ttm, 1)
        ELSE sf.pe_ratio
    END                                             AS live_pe,

    -- Best available 52W high (live > screener)
    COALESCE(mr.week_high_52, sf.high_52w, dc.high_52w_inr)   AS best_52w_high,
    COALESCE(mr.week_low_52,  sf.low_52w,  dc.low_52w_inr)    AS best_52w_low,

    -- Best available price (live > dim_company baseline)
    COALESCE(mr.ltp, dc.current_price_inr)          AS cmp,

    -- Best available market cap (live > screener snapshot > dim_company)
    COALESCE(mr.market_cap_live_cr, sf.market_cap_cr, dc.market_cap_inr_cr) AS market_cap_cr,

    -- Staleness flags for AI context
    CASE
        WHEN mr.updated_at > NOW() - INTERVAL '30 minutes' THEN 'fresh'
        WHEN mr.updated_at > NOW() - INTERVAL '6 hours'    THEN 'stale'
        ELSE 'very_stale'
    END                                             AS price_freshness,

    CASE
        WHEN sf.scraped_at > NOW() - INTERVAL '7 days'  THEN 'fresh'
        WHEN sf.scraped_at > NOW() - INTERVAL '30 days' THEN 'stale'
        ELSE 'very_stale'
    END                                             AS fundamentals_freshness

FROM dim_company dc
LEFT JOIN fact_market_realtime        mr ON mr.symbol = dc.ticker
LEFT JOIN fact_screener_fundamentals  sf ON sf.ticker = dc.ticker
WHERE dc.ticker IS NOT NULL;

-- Grant read to anon role (inherits dim_company's RLS implicitly in views)
GRANT SELECT ON vw_stock_snapshot TO anon;
