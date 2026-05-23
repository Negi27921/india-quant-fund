-- Migration 003: signals table (replaces JSONB blob screener_cache)
-- One row per signal per scan — queryable, indexable, historical.
-- This is the target architecture; screener_cache remains for backward compat.
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS signals (
    id           UUID NOT NULL DEFAULT gen_random_uuid(),
    scan_id      UUID NOT NULL,          -- groups all signals from one scan run
    strategy     TEXT NOT NULL,
    universe     TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    scanned_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ltp          NUMERIC(12, 2),
    confidence   INT,                    -- 0–100
    conditions   JSONB,                  -- per-condition met/not breakdown
    sl_pct       NUMERIC(6, 2),
    target_pct   NUMERIC(6, 2),
    matched      BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (id, scanned_at)        -- partition key must be in PK
) PARTITION BY RANGE (scanned_at);

-- Create the first partition (current year)
CREATE TABLE IF NOT EXISTS signals_2026
    PARTITION OF signals
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- Indexes for the common query patterns
CREATE INDEX IF NOT EXISTS signals_strategy_universe_idx
    ON signals (strategy, universe, scanned_at DESC);

CREATE INDEX IF NOT EXISTS signals_ticker_idx
    ON signals (ticker, scanned_at DESC);

CREATE INDEX IF NOT EXISTS signals_scan_id_idx
    ON signals (scan_id);

-- RLS
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON signals
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "anon_read" ON signals
    FOR SELECT TO anon USING (true);

-- View: latest scan per (strategy, universe) — drop-in replacement for screener_cache reads
CREATE OR REPLACE VIEW latest_signals AS
SELECT DISTINCT ON (strategy, universe)
    strategy,
    universe,
    scan_id,
    scanned_at,
    json_agg(
        json_build_object(
            'ticker', ticker,
            'confidence', confidence,
            'ltp', ltp,
            'sl_pct', sl_pct,
            'target_pct', target_pct,
            'conditions', conditions
        ) ORDER BY confidence DESC
    ) AS results
FROM signals
WHERE matched = true
GROUP BY strategy, universe, scan_id, scanned_at
ORDER BY strategy, universe, scanned_at DESC;
