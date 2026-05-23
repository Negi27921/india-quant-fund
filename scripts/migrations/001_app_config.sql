-- Migration 001: app_config table
-- Stores persistent key-value config: kill switch state, agent config, etc.
-- Run once in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS app_config (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the kill switch row so cloud_main.py can always SELECT it
INSERT INTO app_config (key, value)
VALUES ('kill_switch', '{"active": false, "triggered_at": null, "reason": null}')
ON CONFLICT (key) DO NOTHING;

-- Seed default agent config
INSERT INTO app_config (key, value)
VALUES ('agent_config', '{
    "min_confidence": 95,
    "trade_amount": 25000,
    "max_open_trades": 30,
    "kill_drawdown": 15.0,
    "risk_pct_per_trade": 2.0,
    "strategies": ["vcp", "breakout", "golden_cross", "multibagger", "ipo_base", "rocket_base", "rsi_reversal"]
}')
ON CONFLICT (key) DO NOTHING;

-- Row-Level Security: only service role can write; anon role can read kill_switch
ALTER TABLE app_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON app_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "anon_read_kill_switch" ON app_config
    FOR SELECT TO anon USING (key = 'kill_switch');
