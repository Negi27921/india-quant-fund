-- Migration 016: Clear pre-May 2026 results data
-- Removes all quarterly_results rows with report_date before 2026-05-01.
-- These were inserted by earlier pipeline runs using Yahoo Finance or other
-- non-authoritative sources that don't meet the official-filing-only policy.
-- Run once in Supabase SQL Editor BEFORE running the results pipeline.

DELETE FROM quarterly_results
WHERE report_date < '2026-05-01';

-- Also clear any rows where report_date is null (corrupt entries)
DELETE FROM quarterly_results
WHERE report_date IS NULL;

-- Optional: if you want a full reset (run only if needed)
-- TRUNCATE quarterly_results;
