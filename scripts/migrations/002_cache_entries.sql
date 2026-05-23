-- Migration 002: cache_entries table
-- Enables cross-lambda-instance cache persistence when CACHE_PROVIDER=supabase.
-- Without this, in-process cache resets on every Vercel cold start.
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key  TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cache_entries_expires_idx ON cache_entries (expires_at)
    WHERE expires_at IS NOT NULL;

-- RLS: service role writes, anon reads (cache is not sensitive)
ALTER TABLE cache_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON cache_entries
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "anon_read" ON cache_entries
    FOR SELECT TO anon USING (
        expires_at IS NULL OR expires_at > now()
    );

-- Nightly cleanup function: delete expired entries older than 1 day
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE deleted INTEGER;
BEGIN
    DELETE FROM cache_entries
    WHERE expires_at IS NOT NULL AND expires_at < now() - INTERVAL '1 day';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;
