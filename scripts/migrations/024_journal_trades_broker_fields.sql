-- Migration 024: Add broker-sourced fields to journal_trades
-- These columns capture the exact values from Upstox Realized P&L export
-- so the UI can show correct position size, actual broker P&L, and tax category.

ALTER TABLE journal_trades
  ADD COLUMN IF NOT EXISTS sell_amt         NUMERIC(14, 2),   -- actual gross sell amount
  ADD COLUMN IF NOT EXISTS broker_pl        NUMERIC(14, 2),   -- actual P&L reported by broker (after FIFO matching)
  ADD COLUMN IF NOT EXISTS days_held        INT,              -- holding period in calendar days
  ADD COLUMN IF NOT EXISTS short_term_pl    NUMERIC(14, 2),   -- STCG portion
  ADD COLUMN IF NOT EXISTS long_term_pl     NUMERIC(14, 2),   -- LTCG portion
  ADD COLUMN IF NOT EXISTS speculation_pl   NUMERIC(14, 2),   -- intraday/speculation portion
  ADD COLUMN IF NOT EXISTS turnover         NUMERIC(16, 2),   -- segment turnover (buy_amt + sell_amt)
  ADD COLUMN IF NOT EXISTS isin             TEXT,
  ADD COLUMN IF NOT EXISTS scrip_code       TEXT,             -- BSE scrip code
  ADD COLUMN IF NOT EXISTS scrip_name       TEXT;             -- full company name from broker

-- Index for ISIN lookups (useful for corporate action tracking)
CREATE INDEX IF NOT EXISTS journal_trades_isin_idx ON journal_trades (isin) WHERE isin IS NOT NULL;
