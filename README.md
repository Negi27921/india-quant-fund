# One Piece

> Automated quant hedge fund for Indian equities (NSE/BSE). 7 AI-powered screener strategies, real-time dashboard, auto paper trading, AI market chat, Telegram alerts, and plug-and-play broker execution.

**Live Dashboard →** [luffy-labs.vercel.app](https://luffy-labs.vercel.app)
**API →** [onepiece-labs.vercel.app](https://onepiece-labs.vercel.app)
**Repo →** [github.com/Negi27921/one-piece](https://github.com/Negi27921/one-piece)

---

## What It Does

- Screens 500–2,137 NSE stocks across **7 strategies** with sub-second cached responses
- **Never-blocking scan** — GET always returns cached data instantly; fresh scans run in background threads
- Auto paper-trades ₹25,000/pick on every ≥70% confidence signal via GitHub Actions
- **10 PM daily report** — Telegram + email with P&L, strategy breakdown, and top picks
- Real-time dashboard with market data, AI chat, portfolio analytics, risk monitoring, and earnings results
- Kill switch with configurable drawdown limit; auto-exits on target/SL/expiry
- **Provider abstraction layer** — swap market data, AI, cache, broker, and notification providers by changing env vars

---

## System Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │         GitHub Actions (Cron, Mon–Fri)        │
                    │  9:30 AM  paper_trader --open                 │
                    │  10:30 AM multibagger_alert                   │
                    │  2:00 PM  multibagger_alert                   │
                    │  3:15 PM  paper_trader --check                │
                    │  10:00 PM strategy_agent + daily_report       │
                    │  1st/mo   monthly_report                      │
                    └─────────────────┬────────────────────────────┘
                                      │
                       ┌──────────────▼──────────────┐
                       │      Supabase (PostgreSQL)   │
                       │  paper_trades                │
                       │  app_config (kill switch)    │
                       │  cache_entries (L2 cache)    │
                       │  strategy_notes              │
                       │  journal_trades              │
                       └──────────────┬──────────────┘
                                      │
          ┌───────────────────────────┼────────────────────────────┐
          │                           │                            │
          ▼                           ▼                            ▼
  FastAPI Backend             React Dashboard              Telegram Bot
  onepiece-labs.vercel        luffy-labs.vercel            Alerts + Reports
  cloud_main.py               9 pages + lazy loading       Webhook via FastAPI
  11 API routers              TanStack Query v5
  core/ provider layer        Framer Motion
```

### Two Runtime Modes

| | Local Dev | Cloud (Vercel) |
|--|-----------|----------------|
| Entry point | `api/main.py` | `api/cloud_main.py` |
| Database | DuckDB (local file) | Supabase (PostgreSQL) |
| WebSocket `/ws` | Yes (5s portfolio broadcast) | No (serverless limitation) |
| System endpoints | Full (DuckDB-backed) | Lightweight stubs |

---

## Repository Structure

```
one-piece/
├── core/                           # ← NEW: Provider abstraction layer
│   ├── config.py                   # Unified Settings from env vars (single source of truth)
│   ├── market_data.py              # Unified price-fetch API (replaces 3 duplicates)
│   └── providers/
│       ├── base.py                 # Abstract interfaces (MarketDataProvider, AIProvider, etc.)
│       ├── registry.py             # Factory singletons: get_market_provider(), get_cache(), etc.
│       ├── market/
│       │   ├── yfinance_provider.py  # Default (15-min delayed, free tier)
│       │   ├── nse_provider.py       # nsepython (near real-time, unreliable)
│       │   └── mock_provider.py      # Deterministic fake data (testing)
│       ├── ai/
│       │   ├── groq_provider.py      # Llama 3.3 70B
│       │   ├── gemini_provider.py    # Gemini 2.0 Flash
│       │   ├── openrouter_provider.py
│       │   ├── chain_provider.py     # Cascades through AI_FALLBACK_CHAIN
│       │   └── mock_provider.py
│       ├── cache/
│       │   ├── memory_cache.py       # In-process TTL dict (default, free tier)
│       │   ├── supabase_cache.py     # cache_entries table (cross-lambda persistence)
│       │   └── redis_cache.py        # Upstash/Redis (distributed, best)
│       └── notifications/
│           ├── telegram_provider.py
│           ├── email_provider.py     # Resend API
│           └── multi_provider.py     # Sends to all configured channels
│
├── api/                            # FastAPI application
│   ├── _config.py                  # Shared CORS, versioning, prefixes
│   ├── main.py                     # Local dev entry point (DuckDB + WebSocket)
│   ├── cloud_main.py               # Vercel entry point (Supabase, no WebSocket)
│   ├── middleware/security.py      # Security headers
│   └── routers/
│       ├── chat.py                 # AI assistant (uses core.market_data — fast_info only, <1s)
│       ├── journal.py              # Live trading journal CRUD + NAV + prices
│       ├── market.py               # Live market data (indices, FII/DII, movers, filings)
│       ├── portfolio.py            # Paper portfolio positions and equity curve
│       ├── risk.py                 # Risk metrics, drawdown, kill switch
│       ├── screener.py             # NSE/BSE screener + background scan + L2 cache
│       ├── settings.py             # LLM providers, broker config, agent settings, system-info
│       ├── strategies.py           # Strategy performance, signals, allocation
│       ├── system.py               # Kill switch, audit log (local DuckDB)
│       ├── telegram_bot.py         # Telegram webhook (cloud only)
│       └── trades.py               # Screener auto-trade log
│
├── execution/                      # Order management system
│   ├── brokers/
│   │   ├── base.py                 # BrokerInterface ABC
│   │   ├── kite.py                 # ← NEW: Zerodha Kite Connect (real-time, recommended)
│   │   ├── dhan.py                 # Dhan (primary/fallback)
│   │   └── shoonya.py              # Shoonya/Finvasia (fallback)
│   ├── router.py                   # SmartOrderRouter: Kite → Dhan → Shoonya
│   ├── oms.py                      # Order lifecycle management
│   ├── slippage.py                 # Slippage estimation
│   └── reconciliation.py           # Position reconciliation
│
├── dashboard/                      # React + TypeScript frontend (Vite 5)
│   └── src/
│       ├── api/
│       │   ├── client.ts           # Typed HTTP wrapper (timeout, retry, ApiError)
│       │   ├── queries.ts          # Portfolio, risk, strategy, system hooks
│       │   ├── market-queries.ts   # Market data hooks (indices, FII/DII, screener)
│       │   ├── pnl-queries.ts      # P&L calendar, paper positions, journal hooks
│       │   ├── settings-queries.ts # LLM/broker/alert config hooks + useSystemInfo
│       │   └── types.ts            # Shared TypeScript types
│       ├── pages/
│       │   ├── Market.tsx          # Market terminal (indices, FII/DII, movers, chat)
│       │   ├── Screener.tsx        # Stock screener (7 strategies, confidence filters)
│       │   ├── Portfolio.tsx       # Holdings, P&L calendar, auto-trades, live tab
│       │   ├── Risk.tsx            # Drawdown, VaR, kill switch status
│       │   ├── Strategies.tsx      # Per-strategy performance + signal cards
│       │   ├── Settings.tsx        # Agent config, system-info panel, brokers, alerts
│       │   ├── TradingJournal.tsx  # Manual live trade journal
│       │   ├── Results.tsx         # Quarterly earnings results (rated cards)
│       │   └── Login.tsx           # Password-gated entry
│       └── App.tsx                 # Route-level lazy loading (code splitting per page)
│
├── scripts/
│   ├── paper_trader.py             # ₹25K/trade, all strategies, target/SL/kill-switch
│   ├── multibagger_alert.py        # High-conviction alert (3× daily)
│   ├── daily_report.py             # 10 PM Telegram + email report
│   ├── strategy_agent.py           # AI agent: analyses win rates, saves insights
│   ├── monthly_report.py           # 1st of month P&L summary
│   └── migrations/
│       ├── 001_app_config.sql      # ← NEW: app_config table (kill switch + agent config)
│       ├── 002_cache_entries.sql   # ← NEW: cache_entries table (cross-instance L2 cache)
│       └── 003_signals_table.sql   # ← NEW: normalized signals table (replaces screener JSONB)
│
├── risk/                           # Kill switch, position sizer, drawdown, limits
├── backtest/                       # Strategy backtesting engine
├── config/                         # Strategy and system configuration files
├── requirements-api.txt            # Vercel bundle (no DuckDB, no heavy ML libs)
├── requirements.txt                # Full local dev requirements
└── .github/workflows/
    ├── ci.yml                      # Lint/typecheck/build
    ├── screener_scan.yml           # Daily NSE 500 scan (weekdays)
    ├── paper_trading.yml           # Open/check paper trades (weekdays)
    ├── daily_report.yml            # 10 PM Telegram + email report
    ├── monthly_report.yml          # 1st of month P&L summary
    ├── multibagger_alert.yml       # Morning + afternoon high-conviction alerts
    └── keep-alive.yml              # Prevents Vercel cold starts
```

---

## Provider Abstraction Layer (`core/`)

Switch any provider by changing an env var — no code changes required.

### Market Data
| `MARKET_PROVIDER=` | Provider | Notes |
|--------------------|----------|-------|
| `yfinance` (default) | yFinance | 15-min delayed, free tier, reliable |
| `nse` | nsepython | Near real-time, scrapes NSE |
| `kite` | Zerodha Kite | Real-time L1 data, requires API key |
| `mock` | Fake data | Deterministic, for testing |

### AI / LLM
| `AI_PROVIDER=` | Provider | Notes |
|---------------|----------|-------|
| `groq` (default) | Groq Llama 3.3 70B | Free tier, fast |
| `gemini` | Gemini 2.0 Flash | Free tier fallback |
| `openrouter` | OpenRouter | Many free models |
| `mock` | Static response | Testing |

Cascade: `AI_FALLBACK_CHAIN=groq,gemini,openrouter` (tries each in order)

### Cache
| `CACHE_PROVIDER=` | Provider | Notes |
|------------------|----------|-------|
| `memory` (default) | In-process dict | Lost on cold start |
| `supabase` | `cache_entries` table | Cross-lambda persistence, free |
| `redis` | Upstash/Redis | Distributed, lowest latency |

> **Recommendation:** Set `CACHE_PROVIDER=supabase` on Vercel to survive cold starts. After running migration `002_cache_entries.sql`.

### Notifications
| `NOTIFY_PROVIDER=` | Provider |
|-------------------|----------|
| `telegram` (default) | Telegram Bot API |
| `email` | Resend API |
| `both` | Both channels simultaneously |

### Brokers (Execution)
SmartOrderRouter auto-picks the best available:
1. **Kite** — if `KITE_API_KEY` + `KITE_ACCESS_TOKEN` set (real-time data, recommended)
2. **Dhan** — if `DHAN_CLIENT_ID` + `DHAN_ACCESS_TOKEN` set
3. **Shoonya** — always available as final fallback

---

## Frontend Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Market Terminal | Live indices (Indian + global), FII/DII flows, sector heatmap, top movers, BSE filings feed, AI chatbot |
| `/screener` | Screener | 7 strategies, confidence filter, universe toggle (Nifty 500 / Full NSE), background scan |
| `/portfolio` | Portfolio | Holdings tab (Paper / Live subtabs), P&L calendar heatmap, Screener Auto-Trades, equity curve |
| `/risk` | Risk | Drawdown chart, VaR, Sharpe, kill switch status, position/sector limits |
| `/strategies` | Strategies | Per-strategy allocation bars, Sharpe ratios, signal cards with approve/reject |
| `/journal` | Trading Journal | Live trades CRUD — add, exit, delete manual positions; NAV from cost basis |
| `/results` | Earnings Results | Quarterly results with Excellent/Great/Good/Ok/Weak ratings, metric trends, mini sparklines |
| `/settings` | Settings | Trading Agent config · System Providers panel · LLM providers · Brokers · Alerts · Risk Monitor |

> All pages use route-level lazy loading (`React.lazy` + `Suspense`) — first paint loads ~80 KB instead of the full bundle.

---

## Screener Strategies

| Strategy | Signal | SL | Hold |
|----------|--------|----|------|
| **VCP** | 4-wave volatility contraction, drying volume, EMA stack | 4% | 15d |
| **IPO Base** | First consolidation after IPO (<4 months), tight range, vol dry-up | 6% | 20d |
| **Rocket Base** | 60%+ move in 90d, correction ≤20%, vol contracting into base | 10% | 10d |
| **Breakout** | Within 3% of 52W high, vol surge 1.8×, range expansion | 8% | 10d |
| **RSI Reversal** | RSI recovered from <33, positive divergence, vol surge | 6% | 7d |
| **Golden Cross** | EMA20 crossed EMA50 ≤10 bars ago, SMA200 slope rising | 8% | 20d |
| **Multibagger** | 12-condition deep scan (see below) | 15% | 30d |

### Multibagger 12 Conditions

```
Technical (from 16 FY2025–26 multi-bagger reverse-engineering):
1.  EMA Stack          EMA9 > EMA20 > EMA50
2.  Above SMA200       Price > SMA200
3.  SMA200 Slope       Rising over last 10 bars
4.  RSI Sweet Spot     55 ≤ RSI ≤ 78
5.  Recovery from Low  +15% from 90-day swing low
6.  52W Proximity      Within 40% of 52-week high
7.  Base Forming       20-day range < 30%

Fundamental Proxies (institutional behaviour signals):
8.  Revenue Accel      90d momentum > ½ × 180d momentum
9.  Institutional Buy  5d avg vol > 20d avg vol
10. Vol Re-entry       3d avg vol ≥ 1.5× 20d avg vol
11. Not Extended       Price within 20% of EMA50
12. Liquidity          Avg volume > 75,000 shares/day

Confidence = conditions_passed / 12 × 100%
Auto paper trade threshold: ≥ 70%
```

### Scan Performance
- **Nifty 500** (503 stocks): 30–60s first scan, instant from cache (6h in-process, 24h L2)
- **Full NSE** (~2,137 stocks): 3–8 min first scan, instant from cache
- **Architecture**: never-block GET → ThreadPoolExecutor background scan → L2 cache provider

---

## API Reference

### Market
```
GET /api/market/status                         # Market open/closed, IST time
GET /api/market/indices                        # Nifty50, Sensex, BankNifty, NiftyIT, Midcap
GET /api/market/global-indices                 # GIFT Nifty, Brent Crude, Dow Jones
GET /api/market/fii-dii                        # FII/DII flows (69-day history)
GET /api/market/fii-dii/today                  # Today's FII/DII data
GET /api/market/fii-dii/sectors                # Sector-wise FII ownership
GET /api/market/movers?limit=8                 # Top gainers/losers + breadth
GET /api/market/sectors                        # Sector performance
GET /api/market/filings?limit=15               # BSE corporate filings feed
GET /api/market/corporate-actions              # Dividends, splits, bonuses
GET /api/market/advances-declines              # Advances/declines/unchanged
GET /api/market/results-calendar               # Upcoming earnings meetings
GET /api/market/quarterly-results              # Rated earnings cards (Excellent→Weak)
GET /api/market/history/{ticker}?period&interval  # OHLCV candlestick data
GET /api/market/quote?tickers=RELIANCE,INFY   # Live stock quotes
```

### Screener
```
GET  /api/screener/results?strategy=vcp&universe=nifty500&min_confidence=70
POST /api/screener/scan?strategy=multibagger&universe=full   # force background scan
GET  /api/screener/status                                     # cache status per strategy
POST /api/screener/prewarm?universe=nifty500                 # warm cache on app load
```
Strategies: `vcp` | `ipo_base` | `rocket_base` | `breakout` | `rsi_reversal` | `golden_cross` | `multibagger`

### Portfolio
```
GET  /api/portfolio/summary
GET  /api/portfolio/positions
GET  /api/portfolio/equity-curve?days=252
GET  /api/portfolio/sector-exposure
GET  /api/portfolio/pnl-calendar?year=2025
GET  /api/portfolio/pnl-stats
GET  /api/portfolio/paper-positions
POST /api/portfolio/paper-positions
DELETE /api/portfolio/paper-positions/{ticker}
PUT  /api/portfolio/paper-positions/{ticker}/exit
GET  /api/portfolio/paper-trades?status=all&limit=200
GET  /api/portfolio/strategy-pnl
GET  /api/portfolio/live-positions
POST /api/portfolio/live-positions
DELETE /api/portfolio/live-positions/{ticker}
PUT  /api/portfolio/live-positions/{ticker}/exit
```

### Journal
```
GET    /api/journal/trades
POST   /api/journal/trades
PUT    /api/journal/trades/{id}
DELETE /api/journal/trades/{id}
GET    /api/journal/summary             # NAV (cost-basis), realized P&L
GET    /api/journal/prices              # Live prices for open positions (parallel fetch)
GET    /api/journal/positions           # Journal positions with current prices
GET    /api/journal/pnl-calendar?year=2025
```

### Risk
```
GET /api/risk/metrics                   # Drawdown, Sharpe, daily loss, utilization
GET /api/risk/limits                    # Position, sector, drawdown, liquidity limits
```

### Strategies
```
GET /api/strategies/performance         # Per-strategy Sharpe, return, drawdown, win rate
GET /api/strategies/signals             # Recent buy/sell signals
GET /api/strategies/allocation          # Strategy allocation weights
```

### Settings
```
GET  /api/settings/providers            # LLM providers (Groq, Gemini, OpenRouter, Ollama)
POST /api/settings/providers/probe      # Live test all LLM providers
GET  /api/settings/brokers              # Broker connection status
GET  /api/settings/alerts               # Telegram + email config
POST /api/settings/alerts/test-telegram # Send test Telegram message
GET  /api/settings/env                  # Environment summary (providers, mode, log level)
GET  /api/settings/system-info          # ← NEW: Full provider health + credential status
GET  /api/settings/agent-config         # Trading agent parameters
PUT  /api/settings/agent-config         # Update agent parameters (persisted to Supabase)
```

### System + Chat
```
GET  /api/system/health
GET  /api/system/kill-switch/status
GET  /api/system/audit-log
POST /api/chat/message                  # AI chat (Groq → Gemini → OpenRouter, <9s budget)
POST /api/telegram                      # Telegram webhook
GET  /health                            # Root health check
WS   /ws                                # Live portfolio broadcast (local only)
```

---

## AI Chat

**Endpoint:** `POST /api/chat/message`

Cascading fallback with strict per-provider timeouts:
1. **Groq** (Llama 3.3 70B) — 5s timeout, 800 tokens
2. **Gemini Flash** — 6s timeout, 800 tokens
3. **OpenRouter** (Claude Haiku / Mistral) — 6s timeout
4. **Helpful fallback message** if all fail

Total asyncio budget: 8.5s (within Vercel's 10s function limit).
Stock context uses `fast_info` only (< 1s) — never `ticker.info` which costs 3–10s.

---

## Paper Trading System

| Rule | Value |
|------|-------|
| Capital per trade | ₹25,000 |
| Min confidence | 70% |
| Max open trades | 30 |
| Kill switch trigger | Daily realized loss > 15% |
| Auto-exit conditions | Target hit / SL hit / held past `hold_days` |

Exit statuses: `open` → `target_hit` / `sl_hit` / `expired` / `killed`

---

## Scheduled Jobs

| Time (IST) | Days | Job |
|------------|------|-----|
| 9:30 AM | Mon–Fri | Open new paper trades from screener cache |
| 10:30 AM | Mon–Fri | Multibagger alert (morning) |
| 2:00 PM | Mon–Fri | Multibagger alert (afternoon) |
| 3:15 PM | Mon–Fri | Check exits (target/SL/expiry) before close |
| 10:00 PM | Mon–Fri | Strategy agent analysis + Telegram/email report |
| 1st of month | Always | Monthly P&L summary |

---

## Quick Start

### Prerequisites
```
Python 3.11+, Node 20+
Supabase account (free tier)
Resend API key (email alerts)
Telegram bot token
```

### Run migrations in Supabase SQL Editor (one-time)
```sql
-- Run each file in order:
scripts/migrations/001_app_config.sql   -- kill switch + agent config table
scripts/migrations/002_cache_entries.sql -- cross-lambda cache table
scripts/migrations/003_signals_table.sql -- normalized signals (future)
```

### Backend (local dev)
```bash
cp .env.example .env          # fill in keys
pip install -r requirements-api.txt
uvicorn api.main:app --reload --port 8000
```

### Frontend (local dev)
```bash
cd dashboard
npm install
npm run dev                   # → http://localhost:3000
```

### Frontend quality checks
```bash
cd dashboard
npm run typecheck    # tsc strict (no emit)
npm run lint         # ESLint v9
npm run build        # tsc + vite production build
```

### Backend quality checks
```bash
ruff check api/ core/
ruff format --check api/ core/
pyright api/
```

---

## Deployment

### Frontend → Vercel
```bash
cd dashboard && npx vercel --prod
```
Env var required: `VITE_API_URL=https://onepiece-labs.vercel.app`

### Backend → Vercel (Serverless)
Entry point: `api/cloud_main.py`. All state in Supabase. No DuckDB, no WebSocket.

---

## Environment Variables

### Minimum required
```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...

# At least one LLM key
GROQ_API_KEY=gsk_...

# Notifications
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
RESEND_API_KEY=re_...
REPORT_EMAIL=you@example.com
```

### Provider selection (all optional — defaults shown)
```bash
MARKET_PROVIDER=yfinance        # yfinance | nse | kite | mock
AI_PROVIDER=groq                # groq | gemini | openrouter | mock
AI_FALLBACK_CHAIN=groq,gemini,openrouter
CACHE_PROVIDER=memory           # memory | supabase | redis
NOTIFY_PROVIDER=telegram        # telegram | email | both

# Upgrade to supabase cache (survives cold starts — run migration 002 first):
CACHE_PROVIDER=supabase
```

### Optional broker credentials
```bash
# Kite (Zerodha) — real-time data + execution, replaces Dhan as primary
KITE_API_KEY=...
KITE_API_SECRET=...
KITE_ACCESS_TOKEN=...           # refreshed daily at 6AM IST

# Dhan — primary broker if Kite not set
DHAN_CLIENT_ID=...
DHAN_ACCESS_TOKEN=...

# Redis/Upstash — distributed cache
REDIS_URL=redis://...           # or use UPSTASH_REDIS_URL
UPSTASH_REDIS_URL=https://...
UPSTASH_REDIS_TOKEN=...
```

### Feature flags
```bash
ENABLE_PAPER_TRADING=true       # default
ENABLE_LIVE_TRADING=false       # set true to enable real orders
ENABLE_WEBSOCKET=false          # local only
DEPLOYMENT_MODE=cloud           # cloud | local | fly | railway
```

---

## Supabase Schema

### Core tables (run migration files in `scripts/migrations/`)

```sql
-- Migration 001: app_config (kill switch + agent config)
CREATE TABLE app_config (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migration 002: cache_entries (L2 cache, replaces in-process dict on cold start)
CREATE TABLE cache_entries (
    cache_key  TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migration 003: signals (normalized, replaces screener_cache JSONB blob)
CREATE TABLE signals (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id    UUID NOT NULL,
    strategy   TEXT NOT NULL,
    universe   TEXT NOT NULL,
    ticker     TEXT NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ltp        NUMERIC(12, 2),
    confidence INT,
    conditions JSONB,
    sl_pct     NUMERIC(6, 2),
    target_pct NUMERIC(6, 2),
    matched    BOOLEAN NOT NULL DEFAULT true
) PARTITION BY RANGE (scanned_at);

-- Paper trades (existing)
CREATE TABLE paper_trades (
    id            BIGSERIAL PRIMARY KEY,
    strategy      TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    entry_date    DATE NOT NULL,
    entry_price   DECIMAL(12,2) NOT NULL,
    target_price  DECIMAL(12,2) NOT NULL,
    sl_price      DECIMAL(12,2) NOT NULL,
    trade_amount  DECIMAL(12,2) DEFAULT 25000,
    shares        INTEGER DEFAULT 1,
    confidence    INTEGER DEFAULT 0,
    hold_days     INTEGER DEFAULT 15,
    exit_date     DATE,
    exit_price    DECIMAL(12,2),
    pnl           DECIMAL(12,2),
    pnl_pct       DECIMAL(8,4),
    status        TEXT DEFAULT 'open',
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Strategy agent insights
CREATE TABLE strategy_notes (
    strategy    TEXT PRIMARY KEY,
    insight     TEXT,
    action      TEXT,
    win_rate    DECIMAL(5,2),
    updated_at  DATE
);

-- Live trading journal
CREATE TABLE journal_trades (
    id          BIGSERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL,
    name        TEXT,
    quantity    INTEGER NOT NULL,
    buy_price   DECIMAL(12,2) NOT NULL,
    buy_date    DATE NOT NULL,
    sell_price  DECIMAL(12,2),
    sell_date   DATE,
    status      TEXT DEFAULT 'open',
    notes       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.111 + Python 3.11, Vercel serverless |
| Provider layer | `core/` — abstract interfaces + env-var-driven registry |
| Frontend | React 19, Vite 5, TypeScript (strict), Tailwind CSS |
| Animation | Framer Motion 11 |
| Charts | TradingView lightweight-charts (OHLCV) + Recharts (analytics) |
| Server state | TanStack Query v5 |
| UI state | Zustand 5 |
| Database | Supabase (PostgreSQL cloud), DuckDB (local dev) |
| AI Chat | Groq Llama 3.3 70B → Gemini Flash → OpenRouter (cascade, <9s) |
| Market data | yFinance (default), nsepython, BeautifulSoup4 (FII/DII scraping) |
| Email | Resend API |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions cron |
| Brokers | Zerodha Kite (primary), Dhan, Shoonya |
| CI | ESLint v9, Ruff, Pyright, GitHub Actions |

---

## GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `SUPABASE_URL` | Database URL |
| `SUPABASE_KEY` | Database service key |
| `RESEND_API_KEY` | Email (Resend) |
| `REPORT_EMAIL` | Recipient email address |
| `TELEGRAM_BOT_TOKEN` | Telegram bot |
| `TELEGRAM_CHAT_ID` | Telegram chat/group ID |
| `GROQ_API_KEY` | AI chat (primary) + strategy agent |
| `GEMINI_API_KEY` | AI chat fallback #1 |
| `OPENROUTER_API_KEY` | AI chat fallback #2 (optional) |
| `KITE_API_KEY` | Zerodha Kite (optional — enables real-time data + live trading) |
| `KITE_ACCESS_TOKEN` | Zerodha Kite session (refresh daily at 6AM IST) |
| `DHAN_CLIENT_ID` | Dhan broker (optional — fallback if Kite not set) |
| `DHAN_ACCESS_TOKEN` | Dhan broker session |

---

## Architecture Notes

**Provider abstraction** — All external dependencies (market data, AI, cache, notifications, broker) are abstracted behind interfaces in `core/providers/`. Switch providers by setting env vars. Adding `KITE_API_KEY` automatically routes orders through Kite. Setting `CACHE_PROVIDER=supabase` makes screener results survive Vercel cold starts.

**NAV computation** — `/api/journal/summary` uses cost-basis NAV (`buy_price × quantity`), not live prices. Avoids sequential yFinance calls in the critical path. Live prices fetched separately via `/api/journal/prices` with parallel `ThreadPoolExecutor` (6s timeout).

**Never-block screener** — GET `/api/screener/results` always returns instantly from L1 (in-process dict) or L2 cache (provider-selected). Background scans run in `ThreadPoolExecutor`. Partial results stream back during scan via `_scan_progress`.

**AI chat timeout** — `ticker.info` (3–10s) was replaced with `ticker.fast_info` (<1s) via `core.market_data.get_stock_context()`. Total chat budget is 8.5s, within Vercel's 10s function timeout.

**Route-level lazy loading** — All 8 pages use `React.lazy()` + `Suspense`. First paint downloads ~80 KB instead of the full ~235 KB bundle.

**Supabase migrations** — Run `scripts/migrations/001_*.sql` → `002_*.sql` → `003_*.sql` in order via Supabase SQL Editor. Migration 002 enables `CACHE_PROVIDER=supabase`. Migration 001 enables `/api/settings/agent-config` persistence.

For full system documentation see [ARCHITECTURE.md](ARCHITECTURE.md).

---

*Not financial advice. For educational and research purposes only.*
