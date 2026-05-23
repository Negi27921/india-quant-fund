-- Migration 006: watchlists + watchlist_items
-- Supports: manual lists, auto-results list, breakout tracking
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS watchlists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    type        TEXT DEFAULT 'manual',   -- 'manual' | 'auto_results'
    color       TEXT DEFAULT '#a78bfa',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id        UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    ticker              TEXT,
    company             TEXT DEFAULT '',
    added_at            TIMESTAMPTZ DEFAULT NOW(),
    added_reason        TEXT DEFAULT 'manual',   -- 'manual'|'result_excellent'|'result_great'|'result_good'
    result_date         TEXT,
    result_high         NUMERIC(12,2),           -- result-day price high (breakout reference)
    result_volume_avg   BIGINT,                  -- 20-day avg volume on result day
    result_rating       TEXT,
    breakout_alerted    BOOLEAN DEFAULT FALSE,
    breakout_date       TEXT,
    notes               TEXT DEFAULT '',
    UNIQUE(watchlist_id, symbol)
);

-- Seed the auto-results watchlist (always exists, id is stable)
INSERT INTO watchlists (id, name, description, type, color)
VALUES (
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Results Radar',
    'Auto-populated from BSE filings with Good / Great / Excellent ratings',
    'auto_results',
    '#34d399'
) ON CONFLICT (id) DO NOTHING;

-- Indexes
CREATE INDEX IF NOT EXISTS wi_watchlist_id_idx ON watchlist_items (watchlist_id);
CREATE INDEX IF NOT EXISTS wi_symbol_idx        ON watchlist_items (symbol);
CREATE INDEX IF NOT EXISTS wi_breakout_idx      ON watchlist_items (breakout_alerted, result_date);

-- auto updated_at
CREATE OR REPLACE FUNCTION _wl_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS wl_updated_at ON watchlists;
CREATE TRIGGER wl_updated_at
    BEFORE UPDATE ON watchlists
    FOR EACH ROW EXECUTE FUNCTION _wl_set_updated_at();
