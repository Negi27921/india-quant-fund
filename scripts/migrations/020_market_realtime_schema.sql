-- Migration 020: Live market state — fact_market_realtime
-- Strict separation: this table NEVER holds fundamental snapshot data.
-- Refresh cadence: every 5–15 min during market hours (market_realtime_poller.py).
-- Primary key is clean ticker symbol (no .NS / .BO suffix).
-- Run after 019_screener_schema.sql

CREATE TABLE IF NOT EXISTS fact_market_realtime (
    symbol              TEXT PRIMARY KEY,            -- clean ticker e.g. RELIANCE
    exchange            TEXT NOT NULL DEFAULT 'NSE',
    -- Price state
    ltp                 NUMERIC,                     -- last traded price
    prev_close          NUMERIC,
    day_open            NUMERIC,
    day_high            NUMERIC,
    day_low             NUMERIC,
    -- Volume / value
    volume              BIGINT,
    volume_cr           NUMERIC,                     -- volume × ltp / 1e7 (Cr)
    value_traded_cr     NUMERIC,
    delivery_pct        NUMERIC,
    -- Derived
    pct_change          NUMERIC,                     -- (ltp - prev_close)/prev_close * 100
    abs_change          NUMERIC,                     -- ltp - prev_close
    vwap                NUMERIC,
    -- Live cap (computed, not from screener snapshot)
    market_cap_live_cr  NUMERIC,
    -- Rolling 52W (updated on EOD run from yFinance fast_info)
    week_high_52        NUMERIC,
    week_low_52         NUMERIC,
    pct_from_52w_high   NUMERIC,                     -- ((ltp - 52wh) / 52wh) * 100
    -- Circuit limits (where available)
    upper_circuit       NUMERIC,
    lower_circuit       NUMERIC,
    -- Market status
    market_status       TEXT DEFAULT 'CLOSED',       -- OPEN | PRE_OPEN | CLOSED
    last_trade_time     TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS fmr_updated_at_idx      ON fact_market_realtime (updated_at DESC);
CREATE INDEX IF NOT EXISTS fmr_pct_change_idx      ON fact_market_realtime (pct_change DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS fmr_market_cap_live_idx ON fact_market_realtime (market_cap_live_cr DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS fmr_volume_idx          ON fact_market_realtime (volume DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS fmr_52w_high_idx        ON fact_market_realtime (pct_from_52w_high);

-- RLS: anon read only
ALTER TABLE fact_market_realtime ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_read_market_realtime" ON fact_market_realtime;
CREATE POLICY "anon_read_market_realtime"
    ON fact_market_realtime FOR SELECT TO anon USING (true);
