# One Piece Quant — System Context

> Complete reference for all working components. Updated 2026-05-10.
> This file exists so future sessions never lose context.

---

## Live URLs

| Service | URL |
|---------|-----|
| **Dashboard** | https://luffy-labs.vercel.app |
| **API (primary)** | https://onepiece-labs.vercel.app |
| **API (alias)** | https://india-quant-fund.vercel.app → 307 → above |
| **GitHub** | https://github.com/Negi27921/india-quant-fund |
| **Telegram webhook** | https://onepiece-labs.vercel.app/api/telegram |

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11, deployed on Vercel serverless |
| Database | Supabase (PostgreSQL cloud) |
| Local cache | DuckDB (`data/db/iqf.duckdb`) |
| Frontend | React 19 + Vite + TypeScript + Tailwind + Framer Motion |
| State | TanStack Query v5 (server) + Zustand (UI) |
| Charts | Recharts |
| Icons | Lucide |
| Brokers | Dhan (primary) + Shoonya/Finvasia (failover) |
| LLM (chat) | Groq Llama 3.3 70B + DeepSeek → Gemini → OpenRouter fallback |
| LLM (agent) | Groq Llama 3.3 70B + OpenRouter Mixtral fallback |
| Email | Resend API |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions cron |
| Branding | One Piece Quant / Luffy Labs |

---

## Directory Structure

```
india-quant-fund/
├── api/                      # FastAPI backend (Vercel serverless)
│   ├── main.py               # App factory, CORS, WebSocket, 9 routers
│   ├── cloud_main.py         # Vercel entry point
│   ├── full_universe.py      # 2,137 NSE tickers
│   ├── fii_dii_data/         # Static FII/DII JSON (history, sectors, latest)
│   └── routers/
│       ├── screener.py       # 7-strategy screener with Supabase L2 cache
│       ├── market.py         # Indices, FII/DII, top movers, sectors, filings
│       ├── portfolio.py      # Holdings, P&L, allocation
│       ├── trades.py         # Trade history blotter
│       ├── risk.py           # VaR, drawdown, Sharpe, sector exposure
│       ├── strategies.py     # Per-strategy performance metrics
│       ├── settings.py       # App config (paper/live mode, kill switch)
│       ├── chat.py           # AI chat (Groq + context injection)
│       ├── system.py         # Health, version, status
│       └── telegram_bot.py   # Telegram webhook handler
│
├── scripts/                  # Operational agents (run via GitHub Actions)
│   ├── multibagger_alert.py  # 3× daily alert: BSE + 11-condition scan → email + Telegram
│   ├── paper_trader.py       # Paper trading: ₹25K/trade, all 8 screeners, target/SL
│   ├── strategy_agent.py     # Hermes-style AI agent: analyses trades, improves strategies
│   ├── daily_report.py       # 10 PM Telegram+email daily report
│   ├── auto_trader.py        # Live/paper order placement via Dhan API
│   └── monthly_report.py     # 1st of month P&L summary
│
├── dashboard/                # React frontend (Vercel)
│   ├── public/
│   │   └── favicon.svg       # Luffy straw hat silhouette (matrix green)
│   └── src/
│       ├── pages/            # 6 pages: Market, Screener, Portfolio, Risk, Strategies, Settings
│       ├── components/       # Layout, Charts, UI (ChatBot, MatrixRain, etc.)
│       ├── api/              # React Query hooks + axios client
│       ├── store/            # Zustand stores (live, ui)
│       └── styles/globals.css # Matrix/space theme: #020407 bg, #00ff87 primary
│
├── .github/workflows/
│   ├── multibagger_alert.yml # 10:30AM / 2PM / 10PM IST Mon–Fri
│   ├── paper_trading.yml     # 9:30AM (open) + 3:15PM (check exits) Mon–Fri
│   ├── daily_report.yml      # 10PM IST Mon–Fri (strategy agent + report)
│   ├── monthly_report.yml    # 1st of month 8:30AM IST
│   └── keep-alive.yml        # Ping /health every 20h
│
├── agents/                   # AI agent layer
│   ├── director.py, research.py, signal.py, execution.py, monitoring.py, reporting.py
│   └── prompts/              # System prompts for each agent
│
├── data/                     # Data pipeline
│   ├── pipeline/             # Loaders (yfinance, NSE, Screener.in), transformers, validators
│   └── storage/              # DuckDB + Supabase interfaces, schemas
│
├── risk/                     # Risk management (Kelly sizing, kill switch, limits)
├── execution/                # OMS, Dhan + Shoonya broker adapters
├── strategies/               # BaseStrategy + momentum, factor, mean-reversion, event
├── backtest/                 # India equity backtester + walk-forward validator
└── SYSTEM_CONTEXT.md         # This file
```

---

## Supabase Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `screener_cache` | Cache screener results per strategy | strategy, universe, results (jsonb), scanned_at, is_scanning |
| `paper_trades` | All paper trading activity | strategy, ticker, entry_date, entry_price, target_price, sl_price, shares, confidence, exit_date, exit_price, pnl, pnl_pct, status, hold_days |
| `strategy_notes` | Agent insights per strategy | strategy, insight, action, win_rate, updated_at |
| `trades` | Live/paper order log | ticker, side, quantity, price, trade_date, strategy, pnl, order_id, mode |
| `daily_pnl` | Daily portfolio performance | date, day_pnl, day_pnl_pct, portfolio_value |
| `monthly_reports` | Monthly summaries | report_month, email_to, mtd_pnl, ytd_pnl, total_trades, report_data |

### SQL to create new tables

```sql
-- Paper trades (run once in Supabase SQL editor)
CREATE TABLE IF NOT EXISTS paper_trades (
  id            BIGSERIAL PRIMARY KEY,
  strategy      TEXT NOT NULL,
  ticker        TEXT NOT NULL,
  entry_date    DATE NOT NULL,
  entry_price   DECIMAL(12,2) NOT NULL,
  target_price  DECIMAL(12,2) NOT NULL,
  sl_price      DECIMAL(12,2) NOT NULL,
  trade_amount  DECIMAL(12,2) NOT NULL DEFAULT 25000,
  shares        INTEGER NOT NULL DEFAULT 1,
  confidence    INTEGER NOT NULL DEFAULT 0,
  hold_days     INTEGER NOT NULL DEFAULT 15,
  exit_date     DATE,
  exit_price    DECIMAL(12,2),
  pnl           DECIMAL(12,2),
  pnl_pct       DECIMAL(8,4),
  status        TEXT DEFAULT 'open',
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_paper_trades_strategy ON paper_trades(strategy);
CREATE INDEX IF NOT EXISTS idx_paper_trades_status   ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_paper_trades_entry    ON paper_trades(entry_date);

-- Strategy notes (agent insights)
CREATE TABLE IF NOT EXISTS strategy_notes (
  strategy    TEXT PRIMARY KEY,
  insight     TEXT,
  action      TEXT,
  win_rate    DECIMAL(5,2),
  updated_at  DATE
);
```

---

## Screener Strategies

All strategies are in `api/routers/screener.py`. Each returns a list of stocks with a `confidence` score (0–100%).

| Strategy | Key Conditions | Target | SL | Hold |
|----------|---------------|--------|-----|------|
| **VCP** | EMA contraction, low-volatility base, volume dry-up | 8% | 4% | 15d |
| **IPO Base** | Recent IPO (<2yr), tight range, volume recovery | 12% | 5% | 20d |
| **Rocket Base** | Short tight base after >30% move, breakout volume | 15% | 6% | 10d |
| **Breakout** | Price at 52W high, 3× avg volume, RSI 55–75 | 7% | 3% | 10d |
| **RSI Reversal** | RSI <35→50 reversal, above SMA200, volume pickup | 6% | 3% | 7d |
| **Golden Cross** | EMA50 crosses above EMA200, rising volume | 10% | 4% | 20d |
| **Multibagger** | 11-condition: EMA stack + SMA200 slope + RSI zone + base + vol | 20% | 7% | 30d |
| **Custom** | Screener.in: YOY sales >20%, OPM >12%, Debt/Eq <0.5, ROE >15% | 10% | 5% | 15d |

### Multibagger 11 Conditions
1. EMA Stack (9 > 20 > 50)
2. Price > SMA200
3. SMA200 Slope > 0.3% (per 30 days)
4. RSI 55–78 (momentum zone)
5. Recovered ≥15% from 90-day low
6. Within 40% of 52W High
7. Base Forming <30% range
8. Institutional accumulation (5d vol > 20d vol × 1.1)
9. Volume re-entry (3d avg ≥ 20d avg × 1.5)
10. Not extended (<20% above EMA50)
11. Liquidity (avg vol >75K)

**Confidence = (conditions_passed / 11) × 100. Only ≥95% (≥10/11) passes the alert threshold.**

---

## Scheduled Jobs

| Job | Cron (UTC) | IST | Script |
|-----|-----------|-----|--------|
| Multibagger alert (morning) | `0 5 * * 1-5` | 10:30 AM | `scripts/multibagger_alert.py` |
| Multibagger alert (afternoon) | `30 8 * * 1-5` | 2:00 PM | `scripts/multibagger_alert.py` |
| Paper trader — open | `0 4 * * 1-5` | 9:30 AM | `scripts/paper_trader.py --open` |
| Paper trader — check exits | `45 9 * * 1-5` | 3:15 PM | `scripts/paper_trader.py --check` |
| Daily report + strategy agent | `30 16 * * 1-5` | 10:00 PM | `scripts/daily_report.py` |
| Monthly report | `0 3 1 * *` | 8:30 AM 1st | `scripts/monthly_report.py` |
| Keep-alive | `0 */20 * * *` | every 20h | curl /health |

---

## Paper Trading System

**Script:** `scripts/paper_trader.py`

**Rules:**
- Fixed ₹25,000 per trade
- Only stocks with confidence ≥ 95%
- Maximum 30 open trades at once
- Kill switch: halt new trades if daily realised loss > 15%
- Strategy-specific targets and stop-losses (see table above)

**Exit logic:**
- `target_hit`: price ≥ target → exit at target
- `sl_hit`: price ≤ SL → exit at SL
- `expired`: held longer than `hold_days` → exit at market price

**Data stored in Supabase `paper_trades`:** entry/exit prices, PNL, confidence, strategy

---

## Strategy Agent (Hermes-inspired)

**Script:** `scripts/strategy_agent.py`

Architecture follows NousResearch/hermes-agent (tool-calling loop):
1. **Observe**: query last 30 days of paper trades
2. **Reason**: LLM (Groq Llama 3.3 70B) analyses performance with tool calls
3. **Act**: calls `save_strategy_insight` for each finding
4. **Report**: returns summary text for inclusion in daily report

**Tools:**
- `query_trade_performance(strategy, days)` → win rate, avg PNL, target/SL hit counts
- `get_overall_stats(days)` → cross-strategy comparison
- `save_strategy_insight(strategy, insight, action, win_rate)` → Supabase upsert

**Fallback:** if no LLM key, runs static data analysis

---

## Daily Report (10 PM)

**Script:** `scripts/daily_report.py`

Sections:
1. Screener hits per strategy (≥95% confidence count)
2. Paper trading today (exits, PNL, win rate, open exposure)
3. 30-day win rates by strategy
4. Agent insights (from `strategy_notes` table)
5. Top picks for tomorrow (≥97% confidence)

Sent to: Telegram + Email
Failure handling: if Telegram fails → email alert; if email fails → Telegram alert

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/screener/results` | GET | Cached screener results (`?strategy=vcp&universe=nifty500`) |
| `/api/screener/scan` | POST | Trigger fresh scan (`?strategy=multibagger&universe=full`) |
| `/api/screener/status` | GET | Scan status and cache timestamps |
| `/api/market/indices` | GET | Nifty 50, Sensex, Bank Nifty |
| `/api/market/fii-dii` | GET | FII/DII daily flows + 69-day history |
| `/api/market/movers` | GET | Top gainers/losers |
| `/api/market/sectors` | GET | Sector performance |
| `/api/portfolio/summary` | GET | Portfolio value, P&L, positions |
| `/api/trades/history` | GET | Trade blotter |
| `/api/risk/metrics` | GET | VaR, drawdown, Sharpe ratio |
| `/api/strategies/performance` | GET | Per-strategy P&L and stats |
| `/api/chat/message` | POST | AI chat with live context |
| `/api/telegram` | POST | Telegram webhook |
| `/health` | GET | Health check |
| `/ws` | WS | WebSocket: live P&L every 5s |

---

## Frontend Pages

| Route | Page | Key Features |
|-------|------|-------------|
| `/` | Market Terminal | Indices, FII/DII bars, sector performance, top movers, BSE filings |
| `/screener` | Screener | 7 strategies × 2 universes, Supabase cache, confidence badges |
| `/portfolio` | Portfolio | HOLDINGS \| P&L \| TRADES \| LIVE tabs merged |
| `/risk` | Risk | VaR, drawdown chart, sector exposure, kill switch |
| `/strategies` | Strategies | Per-strategy cards with signals and example trades |
| `/settings` | Settings | Paper/live toggle, kill switch, API config |

---

## Environment Variables

### Vercel (API + Dashboard)
```
VITE_API_URL          = https://onepiece-labs.vercel.app
GROQ_API_KEY          = gsk_...
SUPABASE_URL          = https://xxx.supabase.co
SUPABASE_KEY          = eyJ...
DHAN_CLIENT_ID        = ...
DHAN_ACCESS_TOKEN     = ...
```

### GitHub Secrets
```
RESEND_API_KEY        ✅ set (re_faPbhjDX...)
REPORT_EMAIL          ✅ negi2950@gmail.com
TELEGRAM_BOT_TOKEN    ✅ 8632500920:AAE...
TELEGRAM_CHAT_ID      ✅ 7166042146
SUPABASE_URL          ✅
SUPABASE_KEY          ✅
GROQ_API_KEY          → add for strategy agent LLM
OPENROUTER_API_KEY    → optional fallback
```

---

## Data Flow

```
GitHub Actions (cron)
  │
  ├─ 9:30 AM → paper_trader.py --open
  │    └─ reads screener_cache → Supabase paper_trades (new rows)
  │    └─ Telegram: new trades notification
  │
  ├─ 10:30 AM + 2 PM → multibagger_alert.py
  │    ├─ BSE API → credit ratings
  │    ├─ yfinance → 2,137 NSE stocks (11-condition scan)
  │    ├─ Supabase: store screener_cache
  │    ├─ Email (Resend) + Telegram → alert
  │    └─ API: refresh all strategy caches
  │
  ├─ 3:15 PM → paper_trader.py --check
  │    └─ reads open paper_trades → checks LTP vs target/SL
  │    └─ updates exits in Supabase
  │    └─ Telegram: exit notifications
  │
  └─ 10:00 PM → daily_report.py
       ├─ strategy_agent.py (Groq LLM analysis)
       │    └─ reads paper_trades (30d) → saves to strategy_notes
       ├─ screener hits (from screener_cache)
       ├─ paper P&L (from paper_trades)
       ├─ 30d win rates (from paper_trades)
       ├─ top picks (from screener_cache, ≥97%)
       └─ Telegram + Email → daily report

FastAPI (onepiece-labs.vercel.app)
  ├─ /api/screener/* → reads screener_cache from Supabase
  ├─ /api/market/*   → yfinance + FII/DII static JSON
  ├─ /api/portfolio/* → DuckDB daily_pnl + positions
  ├─ /api/chat/*     → Groq LLM with context
  ├─ /api/telegram   → Telegram bot webhook
  └─ /ws             → WebSocket live P&L (5s interval)

React Dashboard (luffy-labs.vercel.app)
  ├─ TanStack Query → polls all /api/* endpoints
  ├─ Zustand → paper/live mode, sidebar collapse state
  └─ WebSocket → live P&L updates
```

---

## Key Design Decisions

1. **Supabase as L2 cache**: Screener results are stored in `screener_cache` so tab-switching never re-scans. TTL = 4h.
2. **Fixed ₹25,000 paper trades**: Simplifies performance comparison across strategies.
3. **Confidence threshold = 95%**: Only ≥10/11 multibagger conditions trigger alerts/trades.
4. **Hermes-style agent loop**: Strategy agent uses Groq function-calling with tool definitions mirroring NousResearch/hermes-agent architecture.
5. **Dual-channel failure alerts**: Email failure → Telegram alert; Telegram failure → email alert. Silent degradation.
6. **Matrix/space terminal theme**: #020407 bg, #00ff87 primary, glassmorphism cards, JetBrains Mono font.
7. **Luffy logo**: SVG favicon — straw hat silhouette in matrix green.

---

## GitHub Secrets to Add

```
GROQ_API_KEY   — needed for strategy agent LLM analysis (10 PM report)
```

All other secrets already set as of 2026-05-10.
