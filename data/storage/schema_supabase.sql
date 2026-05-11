-- ─── IQF Supabase Schema ──────────────────────────────────────────────────────
-- Run this once in Supabase dashboard → SQL Editor → New query → Run

-- Paper trading positions (user-managed via dashboard)
CREATE TABLE IF NOT EXISTS paper_positions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker       TEXT NOT NULL,
    name         TEXT,
    sector       TEXT,
    quantity     INTEGER NOT NULL,
    avg_buy_price NUMERIC(12,4) NOT NULL,
    buy_date     DATE NOT NULL,
    strategy     TEXT DEFAULT 'paper_trading',
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_ticker ON paper_positions(UPPER(ticker));

-- Live positions (manually tracked real trades)
CREATE TABLE IF NOT EXISTS live_positions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker       TEXT NOT NULL,
    name         TEXT,
    sector       TEXT,
    quantity     INTEGER NOT NULL,
    avg_buy_price NUMERIC(12,4) NOT NULL,
    buy_date     DATE NOT NULL,
    strategy     TEXT DEFAULT 'live',
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_live_ticker ON live_positions(UPPER(ticker));

-- Daily portfolio P&L snapshots (3-month rolling window)
CREATE TABLE IF NOT EXISTS daily_pnl (
    date             DATE PRIMARY KEY,
    portfolio_value  NUMERIC(14,2) NOT NULL,
    cash             NUMERIC(14,2) NOT NULL DEFAULT 0,
    invested         NUMERIC(14,2) NOT NULL DEFAULT 0,
    day_pnl          NUMERIC(12,2) NOT NULL,
    day_pnl_pct      NUMERIC(8,4) NOT NULL,
    realized_pnl     NUMERIC(12,2) DEFAULT 0,
    unrealized_pnl   NUMERIC(12,2) DEFAULT 0,
    benchmark_ret    NUMERIC(8,4),
    alpha            NUMERIC(8,4),
    drawdown_pct     NUMERIC(8,4) DEFAULT 0,
    num_positions    INTEGER,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pnl_date ON daily_pnl(date DESC);

-- Trade log (buy/sell records, 3-month rolling window)
CREATE TABLE IF NOT EXISTS trades (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_date   DATE NOT NULL,
    ticker       TEXT NOT NULL,
    name         TEXT,
    side         TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    quantity     INTEGER NOT NULL,
    price        NUMERIC(12,4) NOT NULL,
    total_value  NUMERIC(14,2),
    pnl          NUMERIC(12,2),
    pnl_pct      NUMERIC(8,4),
    strategy     TEXT,
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);

-- Screener signal cache (written by multibagger_alert.py + API /screener/scan)
CREATE TABLE IF NOT EXISTS screener_cache (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy    TEXT NOT NULL,
    universe    TEXT NOT NULL DEFAULT 'nifty500',
    scanned_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    results     JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_screener_strategy_universe
    ON screener_cache(strategy, universe);
CREATE INDEX IF NOT EXISTS idx_screener_scanned ON screener_cache(scanned_at DESC);

-- Paper trading journal (written by paper_trader.py GitHub Action)
CREATE TABLE IF NOT EXISTS paper_trades (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy      TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    entry_date    DATE NOT NULL,
    entry_price   NUMERIC(12,4) NOT NULL,
    target_price  NUMERIC(12,4),
    sl_price      NUMERIC(12,4),
    exit_date     DATE,
    exit_price    NUMERIC(12,4),
    trade_amount  NUMERIC(14,2),
    shares        INTEGER,
    pnl           NUMERIC(12,2),
    pnl_pct       NUMERIC(8,4),
    confidence    INTEGER,
    hold_days     INTEGER,
    status        TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','target_hit','sl_hit','expired','manual_exit')),
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pt_status  ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_pt_ticker  ON paper_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_pt_entry   ON paper_trades(entry_date DESC);
-- Prevents duplicate entries for the same ticker+strategy on the same day
CREATE UNIQUE INDEX IF NOT EXISTS idx_pt_unique_daily
    ON paper_trades(ticker, strategy, entry_date);

-- Monthly report archive (email sent log + snapshot)
CREATE TABLE IF NOT EXISTS monthly_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_month TEXT NOT NULL,   -- 'YYYY-MM'
    sent_at     TIMESTAMPTZ DEFAULT NOW(),
    email_to    TEXT,
    mtd_pnl     NUMERIC(12,2),
    ytd_pnl     NUMERIC(12,2),
    total_trades INTEGER,
    report_data JSONB
);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_paper_updated
    BEFORE UPDATE ON paper_positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER trg_live_updated
    BEFORE UPDATE ON live_positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
