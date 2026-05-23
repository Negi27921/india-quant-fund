-- Migration 004: journal_trades table
-- Persists trading journal entries to Supabase so they survive
-- browser clears, device switches, and cold-start resets.
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS journal_trades (
    id             TEXT PRIMARY KEY,
    stock_name     TEXT NOT NULL,
    buy_price      NUMERIC(14, 4) NOT NULL,
    quantity       INT NOT NULL,
    entry_date     DATE NOT NULL,
    capital_used   NUMERIC(14, 2) NOT NULL,
    trade_type     TEXT NOT NULL DEFAULT 'Swing',    -- Swing | Investment
    status         TEXT NOT NULL DEFAULT 'Open',     -- Open | Closed
    sell_price     NUMERIC(14, 4),
    exit_date      DATE,
    strategy       TEXT,
    notes          TEXT,
    planned_sl     NUMERIC(14, 4),
    planned_tp     NUMERIC(14, 4),
    emotion_entry  TEXT,
    emotion_exit   TEXT,
    market_cond    TEXT,
    rule_followed  TEXT,                             -- Yes | No | Partial
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for the common list query (newest first)
CREATE INDEX IF NOT EXISTS journal_trades_entry_date_idx
    ON journal_trades (entry_date DESC);

CREATE INDEX IF NOT EXISTS journal_trades_status_idx
    ON journal_trades (status, entry_date DESC);

-- RLS
ALTER TABLE journal_trades ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON journal_trades
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "anon_all" ON journal_trades
    FOR ALL TO anon USING (true) WITH CHECK (true);
