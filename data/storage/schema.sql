-- ─── India Quant Fund — DuckDB Schema ────────────────────────────────────────

-- Raw OHLCV (back-adjusted for splits/dividends)
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker      VARCHAR NOT NULL,
    date        DATE NOT NULL,
    open        DOUBLE NOT NULL,
    high        DOUBLE NOT NULL,
    low         DOUBLE NOT NULL,
    close       DOUBLE NOT NULL,
    volume      BIGINT NOT NULL,
    adj_close   DOUBLE,            -- Dividend + split adjusted
    adj_factor  DOUBLE DEFAULT 1.0,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON ohlcv(date);
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker ON ohlcv(ticker);

-- Universe (Nifty 500 + metadata)
CREATE TABLE IF NOT EXISTS universe (
    ticker          VARCHAR PRIMARY KEY,
    name            VARCHAR,
    sector          VARCHAR,
    industry        VARCHAR,
    exchange        VARCHAR DEFAULT 'NSE',
    isin            VARCHAR,
    market_cap_cr   DOUBLE,
    is_active       BOOLEAN DEFAULT TRUE,
    added_date      DATE,
    removed_date    DATE,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fundamental data (weekly refresh from Screener.in)
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker          VARCHAR NOT NULL,
    date            DATE NOT NULL,
    pe_ratio        DOUBLE,
    pb_ratio        DOUBLE,
    ev_ebitda       DOUBLE,
    roe             DOUBLE,
    roce            DOUBLE,
    gross_margin    DOUBLE,
    net_margin      DOUBLE,
    debt_equity     DOUBLE,
    current_ratio   DOUBLE,
    market_cap_cr   DOUBLE,
    eps_ttm         DOUBLE,
    revenue_cr      DOUBLE,
    eps_est_next    DOUBLE,        -- Analyst estimate
    PRIMARY KEY (ticker, date)
);

-- Corporate actions (splits, dividends, bonuses)
CREATE TABLE IF NOT EXISTS corporate_actions (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    ticker          VARCHAR NOT NULL,
    action_date     DATE NOT NULL,
    action_type     VARCHAR NOT NULL,  -- 'dividend' | 'split' | 'bonus' | 'rights'
    value           DOUBLE,            -- Dividend amount or split ratio
    adj_factor      DOUBLE,            -- Cumulative adjustment factor
    announced_date  DATE,
    source          VARCHAR DEFAULT 'BSE'
);
CREATE INDEX IF NOT EXISTS idx_ca_ticker_date ON corporate_actions(ticker, action_date);

-- Market metadata (circuit limits, FII/DII, delivery %)
CREATE TABLE IF NOT EXISTS market_data (
    ticker          VARCHAR NOT NULL,
    date            DATE NOT NULL,
    delivery_pct    DOUBLE,
    upper_circuit   DOUBLE,
    lower_circuit   DOUBLE,
    fii_net_cr      DOUBLE,        -- FII net buy/sell (index level)
    dii_net_cr      DOUBLE,        -- DII net buy/sell
    vix_india       DOUBLE,
    PRIMARY KEY (ticker, date)
);

-- Computed features (refreshed daily)
CREATE TABLE IF NOT EXISTS features (
    ticker          VARCHAR NOT NULL,
    date            DATE NOT NULL,
    -- Returns
    ret_1d          DOUBLE,
    ret_5d          DOUBLE,
    ret_20d         DOUBLE,
    ret_63d         DOUBLE,
    ret_126d        DOUBLE,
    ret_252d        DOUBLE,
    -- Momentum
    mom_score_st    DOUBLE,        -- Short-term momentum score
    mom_score_mt    DOUBLE,        -- Medium-term momentum score
    -- Technical
    rsi_14          DOUBLE,
    sma_20          DOUBLE,
    sma_50          DOUBLE,
    sma_200         DOUBLE,
    bb_upper        DOUBLE,
    bb_lower        DOUBLE,
    bb_pct          DOUBLE,        -- %B indicator
    adx_14          DOUBLE,
    -- Volume
    adv_5d          DOUBLE,        -- 5-day average daily value (₹)
    adv_20d         DOUBLE,
    adv_60d         DOUBLE,
    volume_ratio    DOUBLE,        -- 5d/60d volume ratio
    -- Risk
    vol_20d         DOUBLE,        -- 20-day realized vol (annualized)
    vol_60d         DOUBLE,        -- 60-day realized vol (annualized)
    beta_252d       DOUBLE,
    -- Factor
    factor_value    DOUBLE,
    factor_quality  DOUBLE,
    factor_lowvol   DOUBLE,
    factor_composite DOUBLE,
    PRIMARY KEY (ticker, date)
);

-- Strategy signals (output of each signal engine)
CREATE TABLE IF NOT EXISTS signals (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    date            DATE NOT NULL,
    ticker          VARCHAR NOT NULL,
    strategy        VARCHAR NOT NULL,
    signal          DOUBLE NOT NULL,   -- -1 to 1
    signal_raw      DOUBLE,
    rank            INTEGER,
    approved        BOOLEAN DEFAULT TRUE,
    rejection_reason VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date);

-- Target portfolio (output of portfolio constructor)
CREATE TABLE IF NOT EXISTS target_portfolio (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    date            DATE NOT NULL,
    ticker          VARCHAR NOT NULL,
    target_weight   DOUBLE NOT NULL,
    strategy        VARCHAR,
    signal_strength DOUBLE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_target_date ON target_portfolio(date);

-- Orders (OMS)
CREATE TABLE IF NOT EXISTS orders (
    order_id        VARCHAR PRIMARY KEY,
    idempotency_key VARCHAR UNIQUE NOT NULL,
    ticker          VARCHAR NOT NULL,
    exchange        VARCHAR DEFAULT 'NSE',
    side            VARCHAR NOT NULL,      -- 'BUY' | 'SELL'
    order_type      VARCHAR NOT NULL,      -- 'MARKET' | 'LIMIT'
    quantity        INTEGER NOT NULL,
    limit_price     DOUBLE,
    trigger_price   DOUBLE,
    product         VARCHAR DEFAULT 'CNC', -- 'CNC' for delivery
    strategy        VARCHAR,
    status          VARCHAR DEFAULT 'CREATED',
    broker          VARCHAR,
    broker_order_id VARCHAR,
    filled_quantity INTEGER DEFAULT 0,
    avg_fill_price  DOUBLE,
    slippage_pct    DOUBLE,
    commission      DOUBLE,
    stt             DOUBLE,
    total_cost      DOUBLE,
    submitted_at    TIMESTAMP,
    filled_at       TIMESTAMP,
    cancelled_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message   VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON orders(ticker);

-- Positions (current live positions)
CREATE TABLE IF NOT EXISTS positions (
    ticker          VARCHAR PRIMARY KEY,
    quantity        INTEGER NOT NULL,
    avg_buy_price   DOUBLE NOT NULL,
    current_price   DOUBLE,
    unrealized_pnl  DOUBLE,
    realized_pnl    DOUBLE DEFAULT 0,
    strategy        VARCHAR,
    buy_date        DATE NOT NULL,         -- T+1 tracking
    last_updated    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily PnL snapshots
CREATE TABLE IF NOT EXISTS daily_pnl (
    date            DATE PRIMARY KEY,
    portfolio_value DOUBLE NOT NULL,
    cash            DOUBLE NOT NULL,
    invested        DOUBLE NOT NULL,
    day_pnl         DOUBLE NOT NULL,
    day_pnl_pct     DOUBLE NOT NULL,
    realized_pnl    DOUBLE DEFAULT 0,
    unrealized_pnl  DOUBLE DEFAULT 0,
    benchmark_ret   DOUBLE,               -- Nifty 500 daily return
    alpha           DOUBLE,
    drawdown_pct    DOUBLE,
    num_positions   INTEGER,
    gross_exposure  DOUBLE,
    portfolio_beta  DOUBLE,
    sharpe_rolling  DOUBLE,               -- Rolling 63d Sharpe
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log (immutable, append-only)
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGINT PRIMARY KEY,
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type      VARCHAR NOT NULL,
    actor           VARCHAR NOT NULL,      -- agent name
    entity_type     VARCHAR,
    entity_id       VARCHAR,
    action          VARCHAR NOT NULL,
    payload         JSON,
    result          VARCHAR,
    error           VARCHAR
);

-- System health
CREATE TABLE IF NOT EXISTS system_health (
    timestamp       TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP,
    component       VARCHAR NOT NULL,
    status          VARCHAR NOT NULL,     -- 'ok' | 'degraded' | 'down'
    latency_ms      INTEGER,
    message         VARCHAR,
    details         JSON
);

-- Backtest results
CREATE TABLE IF NOT EXISTS backtest_results (
    id              VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::VARCHAR,
    strategy        VARCHAR NOT NULL,
    run_date        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    total_return    DOUBLE,
    annual_return   DOUBLE,
    sharpe_ratio    DOUBLE,
    sortino_ratio   DOUBLE,
    calmar_ratio    DOUBLE,
    max_drawdown    DOUBLE,
    win_rate        DOUBLE,
    profit_factor   DOUBLE,
    num_trades      INTEGER,
    avg_hold_days   DOUBLE,
    params          JSON,
    equity_curve    JSON            -- Serialized for quick retrieval
);
