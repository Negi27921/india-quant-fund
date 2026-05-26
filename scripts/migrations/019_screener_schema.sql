-- Migration 019: Screener.in fundamentals cache
-- One row per company, overwritten on every scrape run.
-- Run in Supabase SQL Editor after 018_neo_technicals_schema.sql

CREATE TABLE IF NOT EXISTS fact_screener_fundamentals (
    ticker              TEXT PRIMARY KEY,
    company_id          TEXT REFERENCES dim_company(company_id) ON DELETE SET NULL,
    -- Price / size
    market_cap_cr       NUMERIC,
    current_price       NUMERIC,
    high_52w            NUMERIC,
    low_52w             NUMERIC,
    -- Valuation
    pe_ratio            NUMERIC,
    book_value          NUMERIC,
    face_value          NUMERIC,
    eps_ttm             NUMERIC,
    dividend_yield_pct  NUMERIC,
    -- Quality
    roce_pct            NUMERIC,
    roe_pct             NUMERIC,
    debt_to_equity      NUMERIC,
    current_ratio       NUMERIC,
    -- P&L TTM (Cr)
    sales_ttm_cr        NUMERIC,
    profit_ttm_cr       NUMERIC,
    -- Shareholding latest quarter (%)
    promoter_pct        NUMERIC,
    promoter_pledge_pct NUMERIC,
    fii_pct             NUMERIC,
    dii_pct             NUMERIC,
    public_pct          NUMERIC,
    -- Meta
    screener_url        TEXT,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fsf_company_id_idx  ON fact_screener_fundamentals (company_id);
CREATE INDEX IF NOT EXISTS fsf_scraped_at_idx  ON fact_screener_fundamentals (scraped_at DESC);
CREATE INDEX IF NOT EXISTS fsf_market_cap_idx  ON fact_screener_fundamentals (market_cap_cr DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS fsf_pe_idx          ON fact_screener_fundamentals (pe_ratio);
CREATE INDEX IF NOT EXISTS fsf_roe_idx         ON fact_screener_fundamentals (roe_pct DESC NULLS LAST);

-- RLS: anon read
ALTER TABLE fact_screener_fundamentals ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_read_screener_fundamentals" ON fact_screener_fundamentals;
CREATE POLICY "anon_read_screener_fundamentals"
    ON fact_screener_fundamentals FOR SELECT TO anon USING (true);
