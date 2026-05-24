-- Migration 015: Fix RLS write policies for stock_universe and related tables
-- The anon key needs INSERT/UPDATE permission for the pipeline scripts.
-- Run once in Supabase SQL Editor.

-- stock_universe: public market data, safe to allow full anon access
DROP POLICY IF EXISTS "allow_anon_all" ON stock_universe;
CREATE POLICY "allow_anon_all" ON stock_universe
  FOR ALL TO anon
  USING (true)
  WITH CHECK (true);

-- watchlist_items: universe sync also writes here
DROP POLICY IF EXISTS "allow_anon_all" ON watchlist_items;
CREATE POLICY "allow_anon_all" ON watchlist_items
  FOR ALL TO anon
  USING (true)
  WITH CHECK (true);

-- quarterly_results: pipeline writes here
DROP POLICY IF EXISTS "allow_anon_all" ON quarterly_results;
CREATE POLICY "allow_anon_all" ON quarterly_results
  FOR ALL TO anon
  USING (true)
  WITH CHECK (true);
