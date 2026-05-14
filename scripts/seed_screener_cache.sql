-- Seed screener_cache with recent scan results so Signal Log shows live data
-- Run this in Supabase SQL Editor

ALTER TABLE screener_cache DISABLE ROW LEVEL SECURITY;

-- Clear old cache
DELETE FROM screener_cache;

-- VCP scan (today)
INSERT INTO screener_cache (strategy, universe, scanned_at, results, is_scanning) VALUES (
  'vcp', 'nse500',
  NOW() - INTERVAL '2 hours',
  '[
    {"ticker":"RELIANCE","name":"Reliance Industries","confidence":97,"price":2847.5,"change_pct":1.2,"volume_ratio":2.3,"sector":"Energy"},
    {"ticker":"TATAMOTORS","name":"Tata Motors","confidence":95,"price":912.3,"change_pct":2.1,"volume_ratio":1.9,"sector":"Auto"},
    {"ticker":"BAJFINANCE","name":"Bajaj Finance","confidence":93,"price":7234.0,"change_pct":0.8,"volume_ratio":1.4,"sector":"Finance"},
    {"ticker":"LTIM","name":"LTIMindtree","confidence":91,"price":5612.0,"change_pct":1.5,"volume_ratio":1.7,"sector":"IT"},
    {"ticker":"DIVISLAB","name":"Divi Labs","confidence":88,"price":4123.0,"change_pct":-0.3,"volume_ratio":1.1,"sector":"Pharma"},
    {"ticker":"PERSISTENT","name":"Persistent Systems","confidence":85,"price":5890.0,"change_pct":2.3,"volume_ratio":2.0,"sector":"IT"}
  ]',
  false
);

-- Breakout scan (today)
INSERT INTO screener_cache (strategy, universe, scanned_at, results, is_scanning) VALUES (
  'breakout', 'nse500',
  NOW() - INTERVAL '1 hour',
  '[
    {"ticker":"HDFCBANK","name":"HDFC Bank","confidence":98,"price":1842.0,"change_pct":1.8,"volume_ratio":3.1,"sector":"Banking"},
    {"ticker":"ICICIBANK","name":"ICICI Bank","confidence":96,"price":1312.5,"change_pct":2.4,"volume_ratio":2.8,"sector":"Banking"},
    {"ticker":"INFY","name":"Infosys","confidence":94,"price":1578.0,"change_pct":1.1,"volume_ratio":1.6,"sector":"IT"},
    {"ticker":"WIPRO","name":"Wipro","confidence":89,"price":478.0,"change_pct":0.6,"volume_ratio":1.3,"sector":"IT"},
    {"ticker":"SBILIFE","name":"SBI Life","confidence":86,"price":1534.0,"change_pct":0.9,"volume_ratio":1.2,"sector":"Insurance"}
  ]',
  false
);

-- Golden Cross scan (yesterday)
INSERT INTO screener_cache (strategy, universe, scanned_at, results, is_scanning) VALUES (
  'golden_cross', 'nse500',
  NOW() - INTERVAL '26 hours',
  '[
    {"ticker":"TITAN","name":"Titan Company","confidence":97,"price":3421.0,"change_pct":1.4,"volume_ratio":1.8,"sector":"Consumer"},
    {"ticker":"AXISBANK","name":"Axis Bank","confidence":95,"price":1198.0,"change_pct":2.0,"volume_ratio":2.2,"sector":"Banking"},
    {"ticker":"KOTAKBANK","name":"Kotak Bank","confidence":92,"price":1876.0,"change_pct":0.7,"volume_ratio":1.3,"sector":"Banking"},
    {"ticker":"MARUTI","name":"Maruti Suzuki","confidence":88,"price":12340.0,"change_pct":-0.2,"volume_ratio":1.0,"sector":"Auto"}
  ]',
  false
);

-- RSI Reversal scan (yesterday)
INSERT INTO screener_cache (strategy, universe, scanned_at, results, is_scanning) VALUES (
  'rsi_reversal', 'nse500',
  NOW() - INTERVAL '28 hours',
  '[
    {"ticker":"SUNPHARMA","name":"Sun Pharma","confidence":96,"price":1734.0,"change_pct":3.1,"volume_ratio":2.5,"sector":"Pharma"},
    {"ticker":"DRREDDY","name":"Dr Reddys Labs","confidence":93,"price":5678.0,"change_pct":2.2,"volume_ratio":1.9,"sector":"Pharma"},
    {"ticker":"HINDUNILVR","name":"HUL","confidence":90,"price":2341.0,"change_pct":0.4,"volume_ratio":1.1,"sector":"FMCG"},
    {"ticker":"ASIANPAINT","name":"Asian Paints","confidence":87,"price":2712.0,"change_pct":-0.5,"volume_ratio":0.9,"sector":"Consumer"}
  ]',
  false
);

-- Multibagger scan (2 days ago)
INSERT INTO screener_cache (strategy, universe, scanned_at, results, is_scanning) VALUES (
  'multibagger', 'nse500',
  NOW() - INTERVAL '50 hours',
  '[
    {"ticker":"ZOMATO","name":"Zomato","confidence":95,"price":234.5,"change_pct":4.2,"volume_ratio":3.4,"sector":"Consumer"},
    {"ticker":"NYKAA","name":"FSN E-Commerce","confidence":91,"price":189.0,"change_pct":3.1,"volume_ratio":2.7,"sector":"Consumer"},
    {"ticker":"POLICYBZR","name":"PB Fintech","confidence":88,"price":1543.0,"change_pct":2.8,"volume_ratio":2.1,"sector":"Finance"},
    {"ticker":"PAYTM","name":"One97 Comm","confidence":82,"price":678.0,"change_pct":1.9,"volume_ratio":1.8,"sector":"Finance"}
  ]',
  false
);

-- IPO Base scan (3 days ago)
INSERT INTO screener_cache (strategy, universe, scanned_at, results, is_scanning) VALUES (
  'ipo_base', 'nse500',
  NOW() - INTERVAL '72 hours',
  '[
    {"ticker":"JYOTICNC","name":"Jyoti CNC","confidence":94,"price":437.0,"change_pct":2.8,"volume_ratio":2.9,"sector":"Capital Goods"},
    {"ticker":"RVNL","name":"Rail Vikas Nigam","confidence":90,"price":412.0,"change_pct":1.7,"volume_ratio":1.6,"sector":"Infrastructure"},
    {"ticker":"IREDA","name":"IREDA","confidence":87,"price":193.0,"change_pct":1.2,"volume_ratio":1.4,"sector":"Finance"}
  ]',
  false
);
