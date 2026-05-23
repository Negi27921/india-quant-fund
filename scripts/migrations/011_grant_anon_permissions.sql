-- Migration 011: Grant INSERT/UPDATE/DELETE to anon role
-- ────────────────────────────────────────────────────────
-- Supabase anon key only has SELECT by default.
-- Our GitHub Actions scripts and Vercel API use SUPABASE_KEY (anon key).
-- This migration grants the required DML permissions so inserts don't
-- silently fail with 403 permission denied.
-- Run once in Supabase SQL Editor.

GRANT USAGE ON SCHEMA public TO anon;

-- Core app tables
GRANT SELECT, INSERT, UPDATE, DELETE ON public.watchlists          TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.watchlist_items     TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.quarterly_results   TO anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.stock_universe      TO anon;

-- Supporting tables (screener, paper trading, etc.)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon;

-- Auto-apply to future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon;
