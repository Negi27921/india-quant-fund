-- Migration 001: Journal trades table
-- Run in: Supabase Dashboard → SQL Editor → New query → Run
-- Or: any PostgreSQL client connected to your Supabase project

CREATE TABLE IF NOT EXISTS journal_trades (
    id            TEXT PRIMARY KEY,
    stock_name    TEXT NOT NULL,
    buy_price     NUMERIC(14,4) NOT NULL,
    quantity      INTEGER NOT NULL,
    entry_date    DATE NOT NULL,
    capital_used  NUMERIC(14,2) NOT NULL,
    trade_type    TEXT NOT NULL CHECK (trade_type IN ('Swing', 'Investment')),
    status        TEXT NOT NULL CHECK (status IN ('Open', 'Closed')),
    sell_price    NUMERIC(14,4),
    exit_date     DATE,
    strategy      TEXT,
    notes         TEXT,
    planned_sl    NUMERIC(14,4),
    planned_tp    NUMERIC(14,4),
    emotion_entry TEXT,
    emotion_exit  TEXT,
    market_cond   TEXT,
    rule_followed TEXT CHECK (rule_followed IN ('Yes', 'No', 'Partial')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-update updated_at on every UPDATE
CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_journal_trades_updated_at ON journal_trades;
CREATE TRIGGER trg_journal_trades_updated_at
  BEFORE UPDATE ON journal_trades
  FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- Index for date-ordered queries
CREATE INDEX IF NOT EXISTS idx_journal_trades_entry_date ON journal_trades (entry_date DESC);
