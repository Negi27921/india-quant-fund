-- Migration 012: add score column to quarterly_results
-- score = numeric quality score (0-100) used for ranking/sorting results
-- Run once in Supabase SQL Editor.

ALTER TABLE quarterly_results
  ADD COLUMN IF NOT EXISTS score NUMERIC(6,2) DEFAULT 0;

CREATE INDEX IF NOT EXISTS qr_score_idx ON quarterly_results (score DESC);
