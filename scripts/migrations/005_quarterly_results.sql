-- Migration 005: quarterly_results table
-- Real-time BSE filing results parsed by DeepSeek AI.
-- Each row = one quarterly result announcement from BSE.
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS quarterly_results (
    id              TEXT PRIMARY KEY,           -- scrip_code + '_' + attachment_name stem
    symbol          TEXT NOT NULL,              -- NSE/BSE symbol  e.g. RELIANCE
    ticker          TEXT,                       -- yfinance ticker e.g. RELIANCE.NS
    company         TEXT NOT NULL,
    exchange        TEXT DEFAULT 'BSE',
    sector          TEXT DEFAULT '',
    industry        TEXT DEFAULT '',
    quarter         TEXT,                       -- e.g. Q4 FY2026
    report_date     TEXT,                       -- ISO date of filing
    report_time     TEXT DEFAULT 'After Market Hours',
    rating          TEXT CHECK (rating IN ('Excellent','Great','Good','Ok','Weak')),
    rating_note     TEXT DEFAULT '',
    insight         TEXT DEFAULT '',
    metrics         JSONB,                      -- {sales, pat, eps, opm, ...} with qoq/yoy
    revenue_trend   JSONB DEFAULT '[]',         -- last 3 quarters revenue
    pat_trend       JSONB DEFAULT '[]',
    eps_trend       JSONB DEFAULT '[]',
    quarter_labels  JSONB DEFAULT '[]',
    cmp             NUMERIC(12,2),
    market_cap      NUMERIC(20,2) DEFAULT 0,
    pe              NUMERIC(10,2),
    currency_unit   TEXT DEFAULT 'Cr',
    pdf_url         TEXT,
    filing_id       TEXT UNIQUE NOT NULL,       -- BSE attachment filename (dedup key)
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS qr_report_date_idx  ON quarterly_results (report_date DESC);
CREATE INDEX IF NOT EXISTS qr_symbol_idx        ON quarterly_results (symbol);
CREATE INDEX IF NOT EXISTS qr_created_at_idx    ON quarterly_results (created_at DESC);

-- auto-update updated_at
CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS qr_updated_at ON quarterly_results;
CREATE TRIGGER qr_updated_at
    BEFORE UPDATE ON quarterly_results
    FOR EACH ROW EXECUTE FUNCTION _set_updated_at();
