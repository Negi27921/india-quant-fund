-- Migration 008: Stock Universe — BSE/NSE filtered list (market cap > 1000 Cr)
-- Maintained by universe_agent.py (runs daily via GitHub Actions)
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS stock_universe (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol           TEXT        NOT NULL,           -- canonical NSE symbol
    ticker           TEXT        NOT NULL,           -- e.g. RELIANCE.NS or 500325.BO
    company          TEXT        NOT NULL DEFAULT '',
    bse_scrip_code   TEXT,                           -- BSE 6-digit code
    exchange         TEXT        DEFAULT 'NSE',      -- 'NSE' | 'BSE' | 'BOTH'
    sector           TEXT        DEFAULT '',
    industry         TEXT        DEFAULT '',
    market_cap_cr    NUMERIC(14,2) DEFAULT 0,
    last_price       NUMERIC(12,2),
    pe               NUMERIC(8,2),
    is_active        BOOLEAN     DEFAULT TRUE,
    last_updated     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol)
);

-- Indexes for screener / pipeline lookups
CREATE INDEX IF NOT EXISTS su_symbol_idx     ON stock_universe (symbol);
CREATE INDEX IF NOT EXISTS su_sector_idx     ON stock_universe (sector);
CREATE INDEX IF NOT EXISTS su_mcap_idx       ON stock_universe (market_cap_cr);
CREATE INDEX IF NOT EXISTS su_active_idx     ON stock_universe (is_active);
CREATE INDEX IF NOT EXISTS su_bse_scrip_idx  ON stock_universe (bse_scrip_code);
