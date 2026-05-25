-- Migration 017: NEO Schema
-- Creates all tables for the Stock Profile pipeline:
--   dim_company, fact_income_statement, fact_balance_sheet, fact_cash_flow,
--   fact_results_calendar, fact_filings, fact_announcements_tagged,
--   job_run, data_quality_log, si_dlq
-- Run once in Supabase SQL Editor.
-- Source primacy: DATA_PRIMARY_SOURCE env var controls which source wins at app level;
-- every row carries a `source` column so provenance is always queryable.

-- ============================================================
-- dim_company  (universe, 5,443 companies from SI.ai)
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_company (
    company_id          TEXT PRIMARY KEY,           -- SI.ai id
    isin                TEXT UNIQUE,
    ticker              TEXT NOT NULL,
    company_name        TEXT NOT NULL,
    company_website     TEXT,
    marketcap_category  TEXT,                       -- large | mid | small | micro
    bse_scrip_code      TEXT,
    nse_symbol          TEXT,
    macro_sector        TEXT,
    sector              TEXT,
    industry            TEXT,
    basic_industry      TEXT,
    market_cap_inr_cr   NUMERIC,
    current_price_inr   NUMERIC,
    high_52w_inr        NUMERIC,
    low_52w_inr         NUMERIC,
    prices_as_of        TIMESTAMPTZ,
    source              TEXT NOT NULL DEFAULT 'stockinsights',
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS dim_company_ticker_idx  ON dim_company (ticker);
CREATE INDEX IF NOT EXISTS dim_company_isin_idx    ON dim_company (isin);
CREATE INDEX IF NOT EXISTS dim_company_sector_idx  ON dim_company (sector);

-- ============================================================
-- fact_income_statement
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_income_statement (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          TEXT NOT NULL REFERENCES dim_company(company_id) ON DELETE CASCADE,
    ticker              TEXT NOT NULL,
    statement_scope     TEXT NOT NULL,              -- standalone | consolidated
    reporting_type      TEXT NOT NULL,              -- quarterly | annual
    fiscal_year         INT  NOT NULL,
    fiscal_quarter      INT,                        -- NULL for annual
    period_end_date     DATE NOT NULL,
    audit_status        TEXT,
    currency            TEXT,
    scale               TEXT,
    financials          JSONB NOT NULL DEFAULT '{}',
    source              TEXT NOT NULL DEFAULT 'stockinsights',
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (company_id, statement_scope, reporting_type, period_end_date)
);

CREATE INDEX IF NOT EXISTS fact_is_company_idx   ON fact_income_statement (company_id);
CREATE INDEX IF NOT EXISTS fact_is_ticker_idx    ON fact_income_statement (ticker);
CREATE INDEX IF NOT EXISTS fact_is_period_idx    ON fact_income_statement (period_end_date DESC);

-- ============================================================
-- fact_balance_sheet
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_balance_sheet (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          TEXT NOT NULL REFERENCES dim_company(company_id) ON DELETE CASCADE,
    ticker              TEXT NOT NULL,
    statement_scope     TEXT NOT NULL,
    fiscal_year         INT  NOT NULL,
    fiscal_quarter      INT,
    period_end_date     DATE NOT NULL,
    audit_status        TEXT,
    currency            TEXT,
    scale               TEXT,
    financials          JSONB NOT NULL DEFAULT '{}',
    source              TEXT NOT NULL DEFAULT 'stockinsights',
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (company_id, statement_scope, period_end_date)
);

CREATE INDEX IF NOT EXISTS fact_bs_company_idx ON fact_balance_sheet (company_id);
CREATE INDEX IF NOT EXISTS fact_bs_period_idx  ON fact_balance_sheet (period_end_date DESC);

-- ============================================================
-- fact_cash_flow
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_cash_flow (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          TEXT NOT NULL REFERENCES dim_company(company_id) ON DELETE CASCADE,
    ticker              TEXT NOT NULL,
    statement_scope     TEXT NOT NULL,
    reporting_type      TEXT NOT NULL,
    fiscal_year         INT  NOT NULL,
    fiscal_quarter      INT,
    period_end_date     DATE NOT NULL,
    audit_status        TEXT,
    currency            TEXT,
    scale               TEXT,
    financials          JSONB NOT NULL DEFAULT '{}',
    source              TEXT NOT NULL DEFAULT 'stockinsights',
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (company_id, statement_scope, reporting_type, period_end_date)
);

CREATE INDEX IF NOT EXISTS fact_cf_company_idx ON fact_cash_flow (company_id);

-- ============================================================
-- fact_results_calendar
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_results_calendar (
    id              BIGSERIAL PRIMARY KEY,
    company_id      TEXT REFERENCES dim_company(company_id) ON DELETE SET NULL,
    ticker          TEXT NOT NULL,
    company_name    TEXT,
    result_date     DATE,
    fiscal_year     INT,
    fiscal_quarter  INT,
    result_type     TEXT,
    raw_data        JSONB DEFAULT '{}',
    source          TEXT NOT NULL DEFAULT 'stockinsights',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, fiscal_year, fiscal_quarter)
);

CREATE INDEX IF NOT EXISTS fact_rc_result_date_idx ON fact_results_calendar (result_date ASC NULLS LAST);
CREATE INDEX IF NOT EXISTS fact_rc_ticker_idx      ON fact_results_calendar (ticker);

-- ============================================================
-- fact_filings  (transcripts, annual reports, presentations)
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_filings (
    filing_id       TEXT PRIMARY KEY,               -- SI.ai document id
    company_id      TEXT REFERENCES dim_company(company_id) ON DELETE SET NULL,
    ticker          TEXT,
    company_name    TEXT,
    document_type   TEXT NOT NULL,
    fiscal_year     INT,
    fiscal_quarter  INT,
    published_date  TIMESTAMPTZ,
    pdf_link        TEXT,
    html_link       TEXT,
    exchange_tickers JSONB DEFAULT '[]',
    source          TEXT NOT NULL DEFAULT 'stockinsights',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fact_filings_ticker_idx      ON fact_filings (ticker);
CREATE INDEX IF NOT EXISTS fact_filings_type_idx        ON fact_filings (document_type);
CREATE INDEX IF NOT EXISTS fact_filings_published_idx   ON fact_filings (published_date DESC);

-- ============================================================
-- fact_announcements_tagged  (AI-tagged BSE/NSE filings)
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_announcements_tagged (
    announcement_id     TEXT PRIMARY KEY,           -- SI.ai document id
    company_id          TEXT REFERENCES dim_company(company_id) ON DELETE SET NULL,
    ticker              TEXT,
    company_name        TEXT,
    announcement_type_id TEXT,
    announcement_type   TEXT,
    sentiment           TEXT,                       -- positive | negative | neutral
    summary_header      TEXT,
    summary_text        TEXT,
    source_link         TEXT,
    published_date      TIMESTAMPTZ,
    exchange_tickers    JSONB DEFAULT '[]',
    source              TEXT NOT NULL DEFAULT 'stockinsights',
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fact_ann_ticker_idx      ON fact_announcements_tagged (ticker);
CREATE INDEX IF NOT EXISTS fact_ann_type_idx        ON fact_announcements_tagged (announcement_type);
CREATE INDEX IF NOT EXISTS fact_ann_sentiment_idx   ON fact_announcements_tagged (sentiment);
CREATE INDEX IF NOT EXISTS fact_ann_published_idx   ON fact_announcements_tagged (published_date DESC);

-- ============================================================
-- job_run  (observability for every background job)
-- ============================================================
CREATE TABLE IF NOT EXISTS job_run (
    id          BIGSERIAL PRIMARY KEY,
    job_name    TEXT        NOT NULL,
    start_ts    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_ts      TIMESTAMPTZ,
    rows_in     INT         NOT NULL DEFAULT 0,
    rows_out    INT         NOT NULL DEFAULT 0,
    status      TEXT        NOT NULL DEFAULT 'running',  -- running | success | failed
    error       TEXT,
    metadata    JSONB       DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS job_run_name_idx    ON job_run (job_name);
CREATE INDEX IF NOT EXISTS job_run_start_idx   ON job_run (start_ts DESC);
CREATE INDEX IF NOT EXISTS job_run_status_idx  ON job_run (status);

-- ============================================================
-- data_quality_log  (reconciliation diffs SI.ai vs NSE/BSE)
-- ============================================================
CREATE TABLE IF NOT EXISTS data_quality_log (
    id              BIGSERIAL PRIMARY KEY,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    entity_type     TEXT NOT NULL,                  -- company | income_statement | etc.
    entity_id       TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    si_value        TEXT,
    nse_value       TEXT,
    winning_source  TEXT NOT NULL,                  -- stockinsights | nse_bse
    diff_magnitude  NUMERIC
);

CREATE INDEX IF NOT EXISTS dql_entity_idx    ON data_quality_log (entity_id);
CREATE INDEX IF NOT EXISTS dql_recorded_idx  ON data_quality_log (recorded_at DESC);

-- ============================================================
-- si_dlq  (dead letter queue for failed SI.ai calls)
-- ============================================================
CREATE TABLE IF NOT EXISTS si_dlq (
    id          BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    endpoint    TEXT NOT NULL,
    params      JSONB DEFAULT '{}',
    error_code  INT,
    error_msg   TEXT,
    retry_count INT  NOT NULL DEFAULT 0,
    resolved    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS si_dlq_resolved_idx  ON si_dlq (resolved);
CREATE INDEX IF NOT EXISTS si_dlq_endpoint_idx  ON si_dlq (endpoint);

-- ============================================================
-- RLS: grant anon read on lookup/feed tables; restrict writes to service role
-- ============================================================
ALTER TABLE dim_company            ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_results_calendar  ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_filings           ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_announcements_tagged ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_run                ENABLE ROW LEVEL SECURITY;

-- anon can read universe + feeds (dashboard queries)
CREATE POLICY "anon_read_dim_company"   ON dim_company           FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_calendar"      ON fact_results_calendar FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_filings"       ON fact_filings          FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_announcements" ON fact_announcements_tagged FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_job_run"       ON job_run               FOR SELECT TO anon USING (true);

-- financials: service role only (too large for public)
ALTER TABLE fact_income_statement  ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_balance_sheet     ENABLE ROW LEVEL SECURITY;
ALTER TABLE fact_cash_flow         ENABLE ROW LEVEL SECURITY;
