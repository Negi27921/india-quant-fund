-- ============================================================
-- 025_earnings_results.sql
-- Stores quarterly earnings cards sourced from @earnings_pulse
-- Telegram channel (OCR via Gemini Flash) + BSE XBRL fallback.
-- ============================================================

CREATE TABLE IF NOT EXISTS earnings_results (
  id               uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker           varchar(20) NOT NULL,
  company          varchar(200),
  sector           varchar(100),
  quarter          varchar(10),        -- "Q4FY26"
  period_end       date,               -- 2026-03-31

  -- P&L (₹ Cr)
  sales_cr         numeric,
  sales_prev_q_cr  numeric,
  sales_prev_y_cr  numeric,
  sales_qoq_pct    numeric,
  sales_yoy_pct    numeric,

  other_income_cr  numeric,
  other_income_prev_q_cr numeric,
  other_income_prev_y_cr numeric,

  op_cr            numeric,
  op_prev_q_cr     numeric,
  op_prev_y_cr     numeric,
  op_qoq_pct       numeric,
  op_yoy_pct       numeric,

  opm_pct          numeric,
  opm_prev_q_pct   numeric,
  opm_prev_y_pct   numeric,
  opm_qoq_bps      numeric,
  opm_yoy_bps      numeric,

  pat_cr           numeric,
  pat_prev_q_cr    numeric,
  pat_prev_y_cr    numeric,
  pat_qoq_pct      numeric,
  pat_yoy_pct      numeric,

  eps              numeric,
  eps_prev_q       numeric,
  eps_prev_y       numeric,
  eps_qoq_pct      numeric,
  eps_yoy_pct      numeric,

  -- Market data at filing time
  cmp              numeric,
  pe_ratio         numeric,
  market_cap_cr    numeric,

  -- Quality / provenance
  pulse_rating     varchar(20),        -- Great | Good | Mixed | Poor
  pulse_score      numeric,
  source           varchar(30),        -- telegram_ocr | bse_xbrl | manual
  confidence_score numeric,
  raw_image_url    text,
  telegram_msg_id  bigint,
  bse_ann_id       varchar(50),

  filed_at         timestamptz,
  created_at       timestamptz DEFAULT now(),
  updated_at       timestamptz DEFAULT now(),

  CONSTRAINT earnings_results_unique UNIQUE (ticker, quarter)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_earnings_filed_at  ON earnings_results (filed_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_earnings_ticker     ON earnings_results (ticker);
CREATE INDEX IF NOT EXISTS idx_earnings_quarter    ON earnings_results (quarter);
CREATE INDEX IF NOT EXISTS idx_earnings_rating     ON earnings_results (pulse_rating);
CREATE INDEX IF NOT EXISTS idx_earnings_sector     ON earnings_results (sector);

-- Auto-update timestamp
CREATE OR REPLACE FUNCTION _update_earnings_ts()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_earnings_updated ON earnings_results;
CREATE TRIGGER trg_earnings_updated
  BEFORE UPDATE ON earnings_results
  FOR EACH ROW EXECUTE FUNCTION _update_earnings_ts();

-- RLS: service key can read/write; anon can only read
ALTER TABLE earnings_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS earnings_read_all  ON earnings_results;
DROP POLICY IF EXISTS earnings_write_svc ON earnings_results;

CREATE POLICY earnings_read_all ON earnings_results
  FOR SELECT USING (true);

CREATE POLICY earnings_write_svc ON earnings_results
  FOR ALL USING (auth.role() = 'service_role');

GRANT SELECT ON earnings_results TO anon, authenticated;
GRANT ALL    ON earnings_results TO service_role;
