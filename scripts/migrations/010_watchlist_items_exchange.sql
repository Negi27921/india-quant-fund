-- Migration 010: add exchange column to watchlist_items
-- Aligns watchlist_items with stock_universe schema.
-- Also adds result_rating index for breakout monitor queries.
-- Run once in Supabase SQL Editor.

ALTER TABLE watchlist_items
  ADD COLUMN IF NOT EXISTS exchange TEXT DEFAULT 'NSE';

CREATE INDEX IF NOT EXISTS wi_exchange_idx      ON watchlist_items (exchange);
CREATE INDEX IF NOT EXISTS wi_result_rating_idx ON watchlist_items (result_rating);
