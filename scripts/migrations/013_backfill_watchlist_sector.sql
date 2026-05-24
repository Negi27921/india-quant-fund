-- Migration 013: Backfill sector/industry for existing watchlist_items from stock_universe
-- Also backfill quarterly_results sector/industry for rows that have blank sector
-- Run once in Supabase SQL Editor.

-- 1. Backfill watchlist_items sector/industry from stock_universe
UPDATE watchlist_items wi
SET
    sector   = su.sector,
    industry = su.industry
FROM stock_universe su
WHERE wi.symbol = su.symbol
  AND (wi.sector   IS NULL OR wi.sector   = '')
  AND su.sector IS NOT NULL AND su.sector != '';

-- 2. Backfill quarterly_results sector/industry from stock_universe
UPDATE quarterly_results qr
SET
    sector   = su.sector,
    industry = su.industry
FROM stock_universe su
WHERE qr.symbol = su.symbol
  AND (qr.sector   IS NULL OR qr.sector   = '')
  AND su.sector IS NOT NULL AND su.sector != '';

-- Show what was updated
SELECT
    'watchlist_items' AS tbl,
    COUNT(*) FILTER (WHERE sector != '' AND sector IS NOT NULL) AS with_sector,
    COUNT(*) AS total
FROM watchlist_items
UNION ALL
SELECT
    'quarterly_results',
    COUNT(*) FILTER (WHERE sector != '' AND sector IS NOT NULL),
    COUNT(*)
FROM quarterly_results;
