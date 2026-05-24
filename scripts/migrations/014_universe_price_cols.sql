-- Migration 014: Add prev_close and 52W high/low to stock_universe
-- These power the Market Breadth and 52-Week Highs widgets
-- without external API calls at query time.
-- Run once in Supabase SQL Editor.

ALTER TABLE stock_universe
  ADD COLUMN IF NOT EXISTS prev_close   NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS week_high_52 NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS week_low_52  NUMERIC(12,2);

-- Add intelligence JSONB column to quarterly_results for management
-- commentary, guidance, and confidence scoring.
ALTER TABLE quarterly_results
  ADD COLUMN IF NOT EXISTS intelligence JSONB;

-- Index helps 52W highs query
CREATE INDEX IF NOT EXISTS su_week_high_idx
  ON stock_universe (week_high_52)
  WHERE is_active = true;
