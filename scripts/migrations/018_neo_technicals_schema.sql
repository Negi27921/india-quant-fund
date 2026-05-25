-- Migration 018: Technicals, Bulk/Block Deals, Shareholding
-- Run in Supabase SQL Editor after 017_neo_schema.sql

-- ============================================================
-- fact_technicals  (daily OHLCV + computed indicators snapshot)
-- One row per company per date — refreshed daily post-market
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_technicals (
    id              BIGSERIAL PRIMARY KEY,
    company_id      TEXT REFERENCES dim_company(company_id) ON DELETE SET NULL,
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    -- OHLCV
    open            NUMERIC,
    high            NUMERIC,
    low             NUMERIC,
    close           NUMERIC,
    volume          BIGINT,
    -- Moving averages
    sma_20          NUMERIC,
    sma_50          NUMERIC,
    sma_200         NUMERIC,
    ema_20          NUMERIC,
    -- Momentum
    rsi_14          NUMERIC,
    macd            NUMERIC,
    macd_signal     NUMERIC,
    macd_hist       NUMERIC,
    -- Volatility
    atr_14          NUMERIC,
    bb_upper        NUMERIC,
    bb_mid          NUMERIC,
    bb_lower        NUMERIC,
    -- Price context
    pct_change_1d   NUMERIC,
    pct_change_5d   NUMERIC,
    pct_change_20d  NUMERIC,
    high_52w        NUMERIC,
    low_52w         NUMERIC,
    pct_from_52w_high NUMERIC,
    -- Volume context
    vol_sma_20      NUMERIC,
    rel_volume      NUMERIC,        -- volume / vol_sma_20
    source          TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, date)
);

CREATE INDEX IF NOT EXISTS fact_tech_ticker_date_idx ON fact_technicals (ticker, date DESC);
CREATE INDEX IF NOT EXISTS fact_tech_date_idx        ON fact_technicals (date DESC);
CREATE INDEX IF NOT EXISTS fact_tech_rsi_idx         ON fact_technicals (rsi_14);

-- ============================================================
-- fact_bulk_block_deals  (NSE bulk & block deal disclosures)
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_bulk_block_deals (
    deal_id         TEXT PRIMARY KEY,   -- hash(ticker+date+client+qty)
    ticker          TEXT NOT NULL,
    company_name    TEXT,
    exchange        TEXT NOT NULL DEFAULT 'NSE',
    deal_type       TEXT NOT NULL,      -- bulk | block
    deal_date       DATE NOT NULL,
    client_name     TEXT,
    buy_sell        TEXT,               -- BUY | SELL
    quantity        BIGINT,
    price           NUMERIC,
    value_cr        NUMERIC,            -- quantity * price / 1e7
    is_institutional BOOLEAN DEFAULT FALSE,
    source          TEXT NOT NULL DEFAULT 'nse',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fact_bbd_ticker_idx  ON fact_bulk_block_deals (ticker);
CREATE INDEX IF NOT EXISTS fact_bbd_date_idx    ON fact_bulk_block_deals (deal_date DESC);
CREATE INDEX IF NOT EXISTS fact_bbd_client_idx  ON fact_bulk_block_deals (client_name);

-- ============================================================
-- fact_shareholding  (quarterly promoter/FII/DII/public pattern)
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_shareholding (
    id              BIGSERIAL PRIMARY KEY,
    company_id      TEXT REFERENCES dim_company(company_id) ON DELETE SET NULL,
    ticker          TEXT NOT NULL,
    period_end_date DATE NOT NULL,
    promoter_pct    NUMERIC,
    promoter_pledged_pct NUMERIC,
    fii_pct         NUMERIC,
    dii_pct         NUMERIC,
    public_pct      NUMERIC,
    mutual_fund_pct NUMERIC,
    total_shares    BIGINT,
    source          TEXT NOT NULL DEFAULT 'nse',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, period_end_date)
);

CREATE INDEX IF NOT EXISTS fact_sh_ticker_idx  ON fact_shareholding (ticker);
CREATE INDEX IF NOT EXISTS fact_sh_period_idx  ON fact_shareholding (period_end_date DESC);

-- RLS: anon read
ALTER TABLE fact_technicals       ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_bulk_block_deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_shareholding     ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_technicals"   ON fact_technicals       FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_bulk_block"   ON fact_bulk_block_deals FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_shareholding" ON fact_shareholding      FOR SELECT TO anon USING (true);
