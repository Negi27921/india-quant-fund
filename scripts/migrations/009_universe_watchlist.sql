-- Migration 009: Seed the UNIVERSE watchlist
-- Auto-updated daily by universe_agent.py
-- Run once in Supabase SQL Editor.

INSERT INTO watchlists (id, name, description, type, color)
VALUES (
    'bbbbbbbb-0000-0000-0000-000000000001',
    'Universe',
    'All investable BSE/NSE stocks with market cap > 1000 Cr — auto-updated daily by Universe Agent',
    'universe',
    '#60a5fa'
) ON CONFLICT (id) DO NOTHING;
