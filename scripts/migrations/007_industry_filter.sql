-- Migration 007: add sector/industry to watchlist_items
-- Run once in Supabase SQL Editor.

ALTER TABLE watchlist_items
  ADD COLUMN IF NOT EXISTS sector   TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS industry TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS wi_sector_idx   ON watchlist_items (sector);
CREATE INDEX IF NOT EXISTS wi_industry_idx ON watchlist_items (industry);
