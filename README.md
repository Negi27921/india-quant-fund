# India Quant Fund (IQF)

> Automated quant hedge fund for Indian equities (NSE/BSE). Real-time dashboard, 7 screener strategies, automated paper trading, AI chat, Telegram alerts, and Zerodha Kite execution.

**Live Dashboard →** [luffy-labs.vercel.app](https://luffy-labs.vercel.app)
**API →** [onepiece-labs.vercel.app](https://onepiece-labs.vercel.app)
**Repo →** [github.com/Negi27921/india-quant-fund](https://github.com/Negi27921/india-quant-fund)

---

## What It Does

- Screens 500–2,137 NSE stocks across **7 strategies** with sub-second cached responses
- **Never-blocking scan** — GET always returns cached data instantly; fresh scans run in background threads
- Auto paper-trades ₹25,000/pick on every ≥70% confidence signal via GitHub Actions
- **10 PM daily report** — Telegram + email with P&L, strategy breakdown, and top picks
- Real-time dashboard with market data, AI chat, portfolio analytics, risk monitoring, and earnings results
- Kill switch with configurable drawdown limit; auto-exits on target/SL/expiry
- Live trading journal (LIVE tab) separate from screener paper trades

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
                       │  screener_cache              │
                       │  strategy_notes              │
                       │  journal_trades              │
                       └──────────────┬──────────────┘
                                      │
          ┌───────────────────────────┼────────────────────────────┐
          │                           │                            │
          ▼                           ▼                            ▼
  FastAPI Backend             React Dashboard              Telegram Bot
  onepiece-labs.vercel        luffy-labs.vercel            Alerts + Reports
  cloud_main.py               9 pages                      Webhook via FastAPI
  11 API routers              TanStack Query v5
                              Framer Motion
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
india-quant-fund/
├── api/                        # FastAPI application
│   ├── _config.py              # Shared CORS, versioning, prefixes (single source of truth)
│   ├── main.py                 # Local dev entry point (DuckDB + WebSocket)
│   ├── cloud_main.py           # Vercel entry point (Supabase, no WebSocket)
│   ├── middleware/security.py  # Security headers
│   └── routers/
│       ├── chat.py             # AI assistant (Groq → Gemini → OpenRouter cascade)
│       ├── journal.py          # Live trading journal CRUD + NAV + prices
│       ├── market.py           # Live market data (indices, FII/DII, movers, filings)
│       ├── portfolio.py        # Paper portfolio positions and equity curve
│       ├── risk.py             # Risk metrics, drawdown, kill switch
│       ├── screener.py         # NSE/BSE stock screener + background scan engine
│       ├── settings.py         # LLM providers, broker config, agent settings
│       ├── strategies.py       # Strategy performance, signals, allocation
│       ├── system.py           # Kill switch, audit log (local DuckDB)
│       ├── telegram_bot.py     # Telegram webhook (cloud only)
│       └── trades.py           # Screener auto-trade log
│
├── dashboard/                  # React + TypeScript frontend (Vite 5)
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts           # Typed HTTP wrapper (timeout, retry, ApiError)
│   │   │   ├── queries.ts          # Portfolio, risk, strategy, system hooks
│   │   │   ├── market-queries.ts   # Market data hooks (indices, FII/DII, screener)
│   │   │   ├── pnl-queries.ts      # P&L calendar, paper positions, journal hooks
│   │   │   ├── settings-queries.ts # LLM/broker/alert config hooks
│   │   │   └── types.ts            # Shared TypeScript types
│   │   ├── lib/
│   │   │   ├── constants.ts        # API_BASE, colors, strategy labels, refetch intervals
│   │   │   ├── nse-stocks.ts       # Static NSE 500 symbol list (lazy-loaded chunk)
│   │   │   └── utils.ts            # formatCurrency, formatPct, cn()
│   │   ├── pages/
│   │   │   ├── Market.tsx          # Market terminal (indices, FII/DII, movers, chat)
│   │   │   ├── Screener.tsx        # Stock screener (7 strategies, confidence filters)
│   │   │   ├── Portfolio.tsx       # Holdings, P&L calendar, auto-trades, live tab
│   │   │   ├── Risk.tsx            # Drawdown, VaR, kill switch status
│   │   │   ├── Strategies.tsx      # Per-strategy performance + signal cards
│   │   │   ├── TradingJournal.tsx  # Manual live trade journal
│   │   │   ├── Results.tsx         # Quarterly earnings results (rated cards)
│   │   │   ├── Settings.tsx        # Agent config, broker, alerts, risk monitor
│   │   │   └── Login.tsx           # Password-gated entry
│   │   └── components/
│   │       ├── charts/             # EquityChart, DrawdownChart, BarChart, MiniChart, SectorPieChart, ChartDrawer
│   │       ├── layout/             # Layout, Sidebar, Header
│   │       ├── ui/                 # AddPositionModal, ExitPositionModal, ChatBot, FilingsFeed,
│   │       │                       # GlobalSearch, KillSwitchBanner, Skeleton, Badge, StatCard,
│   │       │                       # AnimatedNumber, Tooltip
│   │       └── tables/
│   ├── vite.config.ts          # Code-split vendor chunks, cache-bust suffix
│   ├── eslint.config.js        # ESLint v9 flat config
│   └── vercel.json             # SPA rewrites, API proxy, security headers, asset caching
│
├── data/                       # Data pipeline and DuckDB storage layer
├── execution/                  # OMS, smart order routing, slippage, reconciliation
│   └── brokers/                # Dhan, Shoonya adapters + Zerodha Kite (MCP)
├── risk/                       # Kill switch, position sizer, drawdown, liquidity checks
├── backtest/                   # Strategy backtesting engine
├── orchestration/              # Job scheduling and coordination
├── monitoring/                 # Alerting and observability
├── reporting/                  # Daily/monthly report generators
├── config/                     # Strategy and system configuration files
└── .github/workflows/
    ├── ci.yml                  # Frontend lint/typecheck/build + backend ruff/pyright
    ├── screener_scan.yml       # Daily NSE 500 scan (weekdays)
    ├── paper_trading.yml       # Open/check paper trades (weekdays)
    ├── daily_report.yml        # 10 PM Telegram + email report
    ├── monthly_report.yml      # 1st of month P&L summary
    ├── multibagger_alert.yml   # Morning + afternoon high-conviction alerts
    └── keep-alive.yml          # Prevents Vercel cold starts
```

---

## Frontend Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Market Terminal | Live indices (Indian + global), FII/DII flows, sector heatmap, top movers, BSE filings feed, AI chatbot |
| `/screener` | Screener | 7 strategies, confidence filter, universe toggle (Nifty 500 / Full NSE), background scan, CHART badge hover |
| `/portfolio` | Portfolio | Holdings tab (Paper / Live subtabs), P&L calendar heatmap, Screener Auto-Trades, equity curve |
| `/risk` | Risk | Drawdown chart, VaR, Sharpe, kill switch status, position/sector limits |
| `/strategies` | Strategies | Per-strategy allocation bars, Sharpe ratios, signal cards with approve/reject |
| `/journal` | Trading Journal | Live trades CRUD — add, exit, delete manual positions; NAV from cost basis |
| `/results` | Earnings Results | Quarterly results with Excellent/Great/Good/Ok/Weak ratings, metric trends, mini sparklines |
| `/settings` | Settings | Trading Agent config, LLM providers, broker connections, Telegram/email alerts, risk monitor |

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
Threshold for auto paper trade: ≥ 70%
```

### Scan Performance
- **Nifty 500** (503 stocks): 30–60s first scan, instant from cache (4h TTL)
- **Full NSE** (~2,137 stocks): 3–8 min first scan, instant from cache
- **Architecture**: never-block GET → ThreadPoolExecutor background scan → Supabase persistence

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
POST /api/screener/prewarm?universe=nifty500                 # warm cache on app load
```
Strategies: `vcp` | `ipo_base` | `rocket_base` | `breakout` | `rsi_reversal` | `golden_cross` | `multibagger`

### Portfolio (Screener Paper Trades)
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

### Trading Journal (Live Portfolio)
```
GET    /api/journal/trades              # All journal entries
POST   /api/journal/trades              # Add trade
PUT    /api/journal/trades/{id}         # Update trade
DELETE /api/journal/trades/{id}         # Delete trade
GET    /api/journal/summary             # NAV (cost-basis), realized P&L, open count
GET    /api/journal/prices              # Live yFinance prices for open positions (parallel)
GET    /api/journal/positions           # Journal positions with current prices
GET    /api/journal/pnl-calendar?year=2025  # Daily P&L calendar for equity curve
```

### Risk
```
GET /api/risk/metrics                   # Drawdown, Sharpe, daily loss, position/sector utilization
GET /api/risk/limits                    # Position, sector, drawdown, liquidity limits
```

### Strategies
```
GET /api/strategies/performance         # Per-strategy Sharpe, return, drawdown, win rate
GET /api/strategies/signals             # Recent buy/sell signals with approval status
GET /api/strategies/allocation          # Current strategy allocation weights
```

### Trades
```
GET /api/trades/orders?status=all       # Order blotter
GET /api/trades/fills?days=30           # Filled trades
GET /api/trades/stats?days=30           # Summary stats
```

### Settings
```
GET  /api/settings/providers            # LLM providers (Groq, Gemini, OpenRouter)
POST /api/settings/providers/probe      # Live test all providers
GET  /api/settings/brokers              # Broker connections (Zerodha, Dhan, Shoonya)
GET  /api/settings/alerts               # Telegram + email config
POST /api/settings/alerts/test-telegram # Send test Telegram message
GET  /api/settings/env                  # Environment summary
GET  /api/settings/agent-config         # Trading agent parameters
PUT  /api/settings/agent-config         # Update agent parameters
```

### System + Chat
```
GET  /api/system/health
GET  /api/system/kill-switch/status
GET  /api/system/audit-log
POST /api/chat/message                  # AI chat (Groq → Gemini → OpenRouter, <9s budget)
POST /api/telegram                      # Telegram webhook
GET  /health                            # Root health check
WS   /ws                                # Live portfolio broadcast, 5s interval (local only)
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
Context injected: live indices, FII/DII flows, sector performance, screener cache status, market regime.

---

## Paper Trading System

**Runs via:** `.github/workflows/paper_trading.yml` → `scripts/paper_trader.py`

| Rule | Value |
|------|-------|
| Capital per trade | ₹25,000 |
| Min confidence | 70% |
| Max open trades | 30 |
| Kill switch trigger | Daily realized loss > 15% |
| Auto-exit conditions | Target hit / SL hit / held past `hold_days` |

**Exit statuses:** `open` → `target_hit` / `sl_hit` / `expired` / `killed`

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
Supabase account
Resend API key (email)
Telegram bot token
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

### Scripts (run manually)
```bash
python scripts/paper_trader.py --open     # open new trades
python scripts/paper_trader.py --check    # check exits
python scripts/paper_trader.py --both     # open + check
python scripts/multibagger_alert.py       # send high-conviction alert
python scripts/daily_report.py            # 10 PM report
python scripts/strategy_agent.py          # AI strategy analysis
```

### Frontend quality checks
```bash
cd dashboard
npm run typecheck    # tsc strict (no emit)
npm run lint         # ESLint v9, 0 warnings allowed
npm run build        # tsc + vite production build
```

### Backend quality checks
```bash
ruff check api/           # lint
ruff format --check api/  # formatting
pyright api/              # type checking
```

---

## Deployment

### Frontend → Vercel
```bash
cd dashboard
npx vercel --prod       # builds dist/ and deploys
```
Env var required: `VITE_API_URL=https://onepiece-labs.vercel.app`

### Backend → Vercel (Serverless)
Entry point: `api/cloud_main.py` (configured in root `vercel.json`).
All state in Supabase. No DuckDB, no WebSocket.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.111 + Python 3.11, Vercel serverless |
| Frontend | React 19, Vite 5, TypeScript (strict), Tailwind CSS |
| Animation | Framer Motion 11 |
| Charts | TradingView lightweight-charts (OHLCV) + Recharts (analytics) |
| Server state | TanStack Query v5 |
| UI state | Zustand 5 |
| Database | Supabase (PostgreSQL cloud), DuckDB (local dev) |
| AI Chat | Groq Llama 3.3 70B → Gemini Flash → OpenRouter (cascade, <9s) |
| Market data | yFinance, nsepython, BeautifulSoup4 (FII/DII scraping) |
| Portfolio optimisation | PyPortfolioOpt |
| Email | Resend API |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions cron |
| Brokers | Zerodha Kite (MCP), Dhan, Shoonya |
| CI | ESLint v9, Ruff, Pyright, GitHub Actions |

---

## Bundle Chunks (Vite Code Splitting)

| Chunk | Contents | Gzip |
|-------|---------|------|
| `vendor-charts` | recharts | ~112 KB |
| `vendor-motion` | framer-motion | ~40 KB |
| `vendor-icons` | lucide-react | ~6 KB |
| `vendor-query` | @tanstack/react-query | ~15 KB |
| `nse-data` | NSE 500 symbol list | ~38 KB |
| `index` | App code | ~235 KB |

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

---

## Supabase Schema

```sql
-- Screener auto paper trades
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
  status        TEXT DEFAULT 'open',  -- open | target_hit | sl_hit | expired | killed
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Strategy agent learnings
CREATE TABLE strategy_notes (
  strategy    TEXT PRIMARY KEY,
  insight     TEXT,
  action      TEXT,
  win_rate    DECIMAL(5,2),
  updated_at  DATE
);

-- Screener results cache (survives serverless restarts)
CREATE TABLE screener_cache (
  strategy    TEXT NOT NULL,
  universe    TEXT NOT NULL,
  results     JSONB,
  scanned_at  TIMESTAMPTZ DEFAULT NOW(),
  is_scanning BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (strategy, universe)
);

-- Manual live trading journal
CREATE TABLE journal_trades (
  id          BIGSERIAL PRIMARY KEY,
  ticker      TEXT NOT NULL,
  name        TEXT,
  quantity    INTEGER NOT NULL,
  buy_price   DECIMAL(12,2) NOT NULL,
  buy_date    DATE NOT NULL,
  sell_price  DECIMAL(12,2),
  sell_date   DATE,
  status      TEXT DEFAULT 'open',  -- open | closed
  notes       TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Architecture Notes

**NAV computation** — `/api/journal/summary` computes NAV from `buy_price × quantity` (cost basis), not live prices. This avoids sequential yFinance HTTP calls in the critical path which can exceed Vercel's 10s function timeout. Live prices are fetched separately via `/api/journal/prices` using parallel `ThreadPoolExecutor` with a 6-second total timeout.

**Screener cache** — Results are never computed on GET. A POST `/scan` triggers a background thread that writes to Supabase. The GET always returns the last cached result plus an `is_scanning` flag. Cache TTL is 4 hours.

**Bundle caching** — All JS chunks are named `[name]-[hash]-v2.js`. The `v2` suffix ensures browsers fetch new files after any deployment, bypassing CDN/browser cache.

For full system documentation see [ARCHITECTURE.md](ARCHITECTURE.md).

---

*Not financial advice. For educational and research purposes only.*
