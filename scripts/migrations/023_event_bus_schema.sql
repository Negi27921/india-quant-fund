-- Migration 023: fact_market_events — event bus for AI reactions and alerts
--
-- Events are written by market_realtime_poller.py after each price update cycle.
-- Consumers: AI agents, alert engine, dashboard notification feed.
--
-- Event types emitted by the poller:
--   NEW_52W_HIGH        — ltp > week_high_52
--   NEAR_52W_HIGH       — ltp within 2% of week_high_52
--   NEAR_52W_LOW        — ltp within 5% of week_low_52
--   VOLUME_SURGE        — volume > 3× 20-day average
--   PLEDGE_SPIKE        — promoter_pledge_pct increased > 5pp since last scrape
--   ROCE_FALL           — roce_pct dropped below 8% (large/mid cap)
--   CIRCUIT_HIT         — pct_change ≥ upper/lower circuit limit
--   PE_ANOMALY          — pe > 200 or pe < 0 (unusual)
--   PRICE_GAP_UP        — day_open > prev_close * 1.03
--   PRICE_GAP_DOWN      — day_open < prev_close * 0.97
--
-- Severity levels:
--   INFO   — informational, no action required
--   WARN   — monitor, may require review
--   ALERT  — high priority, warrants immediate attention
--
-- Run after 020_market_realtime_schema.sql

CREATE TABLE IF NOT EXISTS fact_market_events (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'INFO'
                    CHECK (severity IN ('INFO', 'WARN', 'ALERT')),
    metadata        JSONB NOT NULL DEFAULT '{}',
    is_processed    BOOLEAN NOT NULL DEFAULT FALSE,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fme_symbol_idx        ON fact_market_events (symbol, triggered_at DESC);
CREATE INDEX IF NOT EXISTS fme_event_type_idx    ON fact_market_events (event_type, triggered_at DESC);
CREATE INDEX IF NOT EXISTS fme_unprocessed_idx   ON fact_market_events (is_processed, triggered_at DESC)
    WHERE is_processed = FALSE;
CREATE INDEX IF NOT EXISTS fme_triggered_at_idx  ON fact_market_events (triggered_at DESC);
CREATE INDEX IF NOT EXISTS fme_severity_idx      ON fact_market_events (severity, triggered_at DESC)
    WHERE severity IN ('WARN', 'ALERT');

-- Dedupe guard: one event per (type, symbol) per calendar day
CREATE UNIQUE INDEX IF NOT EXISTS fme_daily_dedup_idx
    ON fact_market_events (event_type, symbol, DATE(triggered_at));

-- RLS
ALTER TABLE fact_market_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_market_events"
    ON fact_market_events FOR SELECT TO anon USING (true);
