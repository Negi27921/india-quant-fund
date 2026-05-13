-- ─── IQF: Fix RLS + Seed paper_trades and daily_pnl ──────────────────────────
-- Run this in Supabase Dashboard → SQL Editor → New Query → Run
-- (Paste the whole file and click Run)

-- ── 1. Disable RLS on data tables (single-user dashboard, no multi-tenant auth)
ALTER TABLE paper_trades  DISABLE ROW LEVEL SECURITY;
ALTER TABLE daily_pnl     DISABLE ROW LEVEL SECURITY;
ALTER TABLE paper_positions DISABLE ROW LEVEL SECURITY;
ALTER TABLE live_positions  DISABLE ROW LEVEL SECURITY;
ALTER TABLE trades          DISABLE ROW LEVEL SECURITY;
ALTER TABLE screener_cache  DISABLE ROW LEVEL SECURITY;

-- ── 2. Add paper_trades column 'status' check to accept OPEN/CLOSED too
-- The existing check only allows lowercase. Drop and recreate to be flexible.
ALTER TABLE paper_trades DROP CONSTRAINT IF EXISTS paper_trades_status_check;
ALTER TABLE paper_trades ADD CONSTRAINT paper_trades_status_check
  CHECK (UPPER(status) IN ('OPEN','CLOSED','TARGET_HIT','SL_HIT','EXPIRED','MANUAL_EXIT'));

-- ── 3. Clear existing seed data
DELETE FROM paper_trades WHERE entry_date >= '2026-01-01';
DELETE FROM daily_pnl    WHERE date        >= '2026-01-01';

-- ── 4. Insert paper trades (15 trades: 9 CLOSED, 6 OPEN)
INSERT INTO paper_trades
  (strategy, ticker, entry_date, entry_price, target_price, sl_price, shares,
   confidence, hold_days, exit_date, exit_price, pnl, pnl_pct, status, notes)
VALUES
  -- CLOSED WINNERS
  ('vcp',          'RELIANCE',   '2026-04-01', 1285.50, 1420.00, 1245.00, 50, 82, 18,
   '2026-04-19', 1412.80,  6365.00,  4.95, 'CLOSED', 'VCP breakout on volume. Nailed the move.'),

  ('breakout',     'HDFCBANK',   '2026-04-03', 1745.00, 1900.00, 1700.00, 40, 75, 14,
   '2026-04-17', 1889.50,  5780.00,  8.27, 'CLOSED', '52-week high breakout, clean close above resistance.'),

  ('golden_cross', 'INFY',       '2026-04-07', 1582.00, 1720.00, 1540.00, 35, 70, 12,
   '2026-04-19', 1695.00,  3955.00,  7.14, 'CLOSED', '50 DMA crossed above 200 DMA. IT rally.'),

  ('multibagger',  'TITAN',      '2026-04-10', 3415.00, 3900.00, 3300.00, 15, 88, 20,
   '2026-04-30', 3892.00,  7155.00, 13.97, 'CLOSED', 'Strong fundamentals + Q4 earnings beat.'),

  ('rsi_reversal', 'SUNPHARMA',  '2026-04-14', 1685.00, 1780.00, 1640.00, 30, 68, 10,
   '2026-04-24', 1762.50,  2325.00,  4.60, 'CLOSED', 'RSI bounced from 32. Pharma sector rotation.'),

  ('breakout',     'LTIM',       '2026-04-16', 5280.00, 5800.00, 5100.00, 10, 72,  9,
   '2026-04-25', 5694.00,  4140.00,  7.84, 'CLOSED', 'LTIM breakout post Q4. Strong deal wins.'),

  -- CLOSED LOSERS
  ('vcp',          'ADANIENT',   '2026-04-08', 2385.00, 2620.00, 2300.00, 20, 60,  6,
   '2026-04-14', 2298.00, -1740.00, -3.65, 'CLOSED', 'Stop triggered. Adani news overhang.'),

  ('golden_cross', 'WIPRO',      '2026-04-21',  568.50,  620.00,  548.00, 80, 65,  7,
   '2026-04-28',  545.00, -1880.00, -4.13, 'CLOSED', 'Weak IT guidance, cut losses early.'),

  ('ipo_base',     'ONGC',       '2026-04-22',  268.00,  300.00,  255.00,150, 58,  5,
   '2026-04-27',  257.50, -1575.00, -3.92, 'CLOSED', 'Oil prices dropped. Stop out.'),

  -- OPEN POSITIONS
  ('vcp',          'TCS',        '2026-05-02', 3845.00, 4200.00, 3720.00, 15, 85, NULL,
   NULL, NULL, NULL, NULL, 'OPEN', 'VCP setup, tight coil. Strong volume on base.'),

  ('breakout',     'BAJFINANCE', '2026-05-05', 7215.00, 7900.00, 6980.00,  8, 78, NULL,
   NULL, NULL, NULL, NULL, 'OPEN', 'Multi-month consolidation breakout on high volume.'),

  ('multibagger',  'AXISBANK',   '2026-05-07', 1185.00, 1340.00, 1140.00, 45, 80, NULL,
   NULL, NULL, NULL, NULL, 'OPEN', 'Strong Q4 results. Banking sector tailwinds.'),

  ('rsi_reversal', 'ICICIBANK',  '2026-05-08', 1248.00, 1380.00, 1200.00, 40, 76, NULL,
   NULL, NULL, NULL, NULL, 'OPEN', 'RSI recovery from oversold. Accumulation pattern.'),

  ('golden_cross', 'TATAMOTORS', '2026-05-09',  718.50,  820.00,  685.00, 70, 74, NULL,
   NULL, NULL, NULL, NULL, 'OPEN', '50 DMA cross. EV + JLR recovery thesis.'),

  ('vcp',          'KOTAKBANK',  '2026-05-12', 2045.00, 2280.00, 1980.00, 25, 82, NULL,
   NULL, NULL, NULL, NULL, 'OPEN', 'VCP on weekly chart. Clean base, low volatility coil.');

-- ── 5. Insert 45 trading days of daily_pnl (Apr 1 – May 14 2026)
INSERT INTO daily_pnl (date, portfolio_value, cash, invested, day_pnl, day_pnl_pct, drawdown_pct)
VALUES
  ('2026-04-01', 1001450.00, 200290.00, 801160.00,  1450.00, 0.1450, 0.0000),
  ('2026-04-02', 1003820.00, 200764.00, 803056.00,  2370.00, 0.2366, 0.0000),
  ('2026-04-03', 1002190.00, 200438.00, 801752.00, -1630.00,-0.1625, 0.0000),
  ('2026-04-04', 1005680.00, 201136.00, 804544.00,  3490.00, 0.3482, 0.0000),
  ('2026-04-07', 1008340.00, 201668.00, 806672.00,  2660.00, 0.2643, 0.0000),
  ('2026-04-08', 1010920.00, 202184.00, 808736.00,  2580.00, 0.2558, 0.0000),
  ('2026-04-09', 1009150.00, 201830.00, 807320.00, -1770.00,-0.1750, 0.0000),
  ('2026-04-10', 1013250.00, 202650.00, 810600.00,  4100.00, 0.4062, 0.0000),
  ('2026-04-11', 1015870.00, 203174.00, 812696.00,  2620.00, 0.2586, 0.0000),
  ('2026-04-14', 1014120.00, 202824.00, 811296.00, -1750.00,-0.1722, 0.0000),
  ('2026-04-15', 1017680.00, 203536.00, 814144.00,  3560.00, 0.3511, 0.0000),
  ('2026-04-16', 1020430.00, 204086.00, 816344.00,  2750.00, 0.2702, 0.0000),
  ('2026-04-17', 1023190.00, 204638.00, 818552.00,  2760.00, 0.2705, 0.0000),
  ('2026-04-22', 1021450.00, 204290.00, 817160.00, -1740.00,-0.1700, 0.0000),
  ('2026-04-23', 1025230.00, 205046.00, 820184.00,  3780.00, 0.3700, 0.0000),
  ('2026-04-24', 1028760.00, 205752.00, 823008.00,  3530.00, 0.3443, 0.0000),
  ('2026-04-25', 1032420.00, 206484.00, 825936.00,  3660.00, 0.3558, 0.0000),
  ('2026-04-28', 1030680.00, 206136.00, 824544.00, -1740.00,-0.1685, 0.0000),
  ('2026-04-29', 1034520.00, 206904.00, 827616.00,  3840.00, 0.3726, 0.0000),
  ('2026-04-30', 1037890.00, 207578.00, 830312.00,  3370.00, 0.3258, 0.0000),
  ('2026-05-01', 1036340.00, 207268.00, 829072.00, -1550.00,-0.1493, 0.0000),
  ('2026-05-02', 1040120.00, 208024.00, 832096.00,  3780.00, 0.3648, 0.0000),
  ('2026-05-05', 1038570.00, 207714.00, 830856.00, -1550.00,-0.1490,-0.0015),
  ('2026-05-06', 1042680.00, 208536.00, 834144.00,  4110.00, 0.3957, 0.0000),
  ('2026-05-07', 1045930.00, 209186.00, 836744.00,  3250.00, 0.3118, 0.0000),
  ('2026-05-08', 1044280.00, 208856.00, 835424.00, -1650.00,-0.1578,-0.0016),
  ('2026-05-09', 1048550.00, 209710.00, 838840.00,  4270.00, 0.4089, 0.0000),
  ('2026-05-12', 1051820.00, 210364.00, 841456.00,  3270.00, 0.3119, 0.0000),
  ('2026-05-13', 1054390.00, 210878.00, 843512.00,  2570.00, 0.2443, 0.0000),
  ('2026-05-14', 1057630.00, 211526.00, 846104.00,  3240.00, 0.3073, 0.0000);

-- ── 6. Verify counts
SELECT 'paper_trades' AS tbl, COUNT(*) AS rows FROM paper_trades
UNION ALL
SELECT 'daily_pnl', COUNT(*) FROM daily_pnl
UNION ALL
SELECT 'paper_trades OPEN', COUNT(*) FROM paper_trades WHERE UPPER(status) = 'OPEN'
UNION ALL
SELECT 'paper_trades CLOSED', COUNT(*) FROM paper_trades WHERE UPPER(status) = 'CLOSED';
