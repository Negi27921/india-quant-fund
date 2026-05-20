# 🏴‍☠️ One Piece Quant — Automated Indian Equity Trading System

> Production-grade automated hedge fund for NSE/BSE cash segment.
> Self-improving AI screeners, paper trading, and real-time dashboard.

**Live Dashboard:** [luffy-labs.vercel.app](https://luffy-labs.vercel.app)
**API:** [onepiece-labs.vercel.app](https://onepiece-labs.vercel.app)
**GitHub:** [Negi27921/india-quant-fund](https://github.com/Negi27921/india-quant-fund)

---

## What It Does

- **Screens 500–2,137 NSE stocks** across 7 strategies with sub-second cached responses
- **Never-block scan architecture** — HTTP returns immediately with stale/cached data; fresh scans run in the background and persist to Supabase
- **Paper trades ₹25,000/pick** on every ≥70% confidence signal automatically
- **Self-improving AI agent** (Hermes-style) analyses win rates and improves strategies daily
- **10 PM daily Telegram + email report** with performance, insights, and top picks
- **Real-time dashboard** — market data, screener, portfolio, risk, strategies, earnings results
- **Kill switch + target/SL** on every paper trade, automatic exit tracking
- **Earnings Results page** — earningspulse-style rating cards (Excellent → Weak) with metric trends
- **AI Chatbot** — Groq → Gemini → OpenRouter fallback, <9s total timeout budget

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions (Cron)                        │
│  9:30AM → paper_trader (open)    3:15PM → paper_trader (check)  │
│  10:30AM+2PM → multibagger_alert            10PM → daily_report │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Supabase (PostgreSQL)      │
              │  screener_cache              │
              │  paper_trades                │
              │  strategy_notes              │
              │  trades / daily_pnl          │
              └──────────────┬──────────────┘
                             │
    ┌────────────────────────┼────────────────────────┐
    │                        │                        │
    ▼                        ▼                        ▼
FastAPI Backend        React Dashboard          Telegram Bot
onepiece-labs.vercel   luffy-labs.vercel        Daily alerts
9 API routers          8 pages                  Trade exits
WebSocket              Luxury dark theme        10PM report
Groq/Gemini AI chat    TanStack Query
Screener cache         Framer Motion
```

---

## Quick Start

### Prerequisites
```bash
python 3.11+
node 18+
supabase account
resend.com account
telegram bot token
```

### Backend (local dev)
```bash
cd india-quant-fund
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

### Run screener alert manually
```bash
python scripts/multibagger_alert.py
```

### Run paper trader manually
```bash
python scripts/paper_trader.py --open    # open new trades from screener cache
python scripts/paper_trader.py --check   # check exits (target/SL/expiry)
python scripts/paper_trader.py --both    # do both
```

### Run daily report manually
```bash
python scripts/daily_report.py
```

---

## Screener Strategies

| Strategy | Key Conditions | Data Period | SL | Hold Days |
|----------|---------------|------------|-----|-----------|
| **VCP** | 4-wave volatility contraction, drying volume, EMA stack | 60d | 4% | 15 |
| **IPO Base** | Recent IPO (<4mo data), tight 15d range, vol dry-up | 60d | 6% | 20 |
| **Rocket Base** | 60%+ move in 90d, correction ≤20%, vol contracting | 120d | 10% | 10 |
| **Breakout** | Near 52W high (<3%), vol surge 1.8×, range expansion | 260d | 8% | 10 |
| **RSI Reversal** | RSI recovered from <33, positive divergence, vol surge | 60d | 6% | 7 |
| **Golden Cross** | EMA20 crossed EMA50 (≤10d ago), SMA200 slope ↑ | 260d | 8% | 20 |
| **Multibagger / CUSTOM** | 12-condition deep scan (below) | 260d | 15% | 30 |

### Multibagger 12 Conditions (confidence = conditions_passed / 12 × 100)
```
Technical DNA (from price analysis of 16 actual FY25-26 winners):
1.  EMA Stack:             EMA9 > EMA20 > EMA50
2.  Above SMA200:          Price > SMA200
3.  SMA200 Slope:          Rising over 10d
4.  RSI Sweet Spot:        55 ≤ RSI ≤ 78
5.  Recovery from Low:     +15% from 90-day swing low
6.  Within 40% of 52W High
7.  Base Forming:          20d range < 30%

Fundamental Proxies (from concall/rating/announcement research):
8.  Revenue Accel Proxy:   90d momentum > ½ × 180d (stock pricing in order wins)
9.  Inst. Accumulation:    5d avg vol > 20d avg vol (post-rating/concall buying)
10. Volume Re-entry:       3d avg ≥ 1.5× 20d avg
11. Not Extended:          Price within 20% of EMA50 (entry zone, not chasing)
12. Liquidity:             Avg volume > 75,000 shares
```

### Scan Performance
- **Nifty 500 (503 stocks):** ~30–60s first scan, instant from cache thereafter
- **Full NSE (2,137 stocks):** ~3–8 min first scan, instant from cache (4h TTL)
- **Cache architecture:** in-process memory → Supabase PostgreSQL (survives serverless restarts)
- **Never-block GET:** `/screener/results` always responds instantly; scans run in background threads

---

## Paper Trading System

**Script:** `scripts/paper_trader.py`

**Rules:**
- Fixed **₹25,000 per trade**
- Only stocks with confidence **≥ 70%** (Strong tier)
- Max **30 open trades** simultaneously
- **Kill switch**: halt new trades if daily realised loss > 15%
- Auto-exit on: **target hit** / **SL hit** / held past **hold_days**

**Frontend tracking:** High-confidence screener results are auto-recorded in browser localStorage as paper trades with real-time P&L, SL/TP monitoring, and per-strategy breakdown cards.

**Supabase table:** `paper_trades`

**Exit statuses:** `open` → `target_hit` / `sl_hit` / `expired` / `killed`

---

## Strategy Agent (Self-Improving AI)

**Script:** `scripts/strategy_agent.py`

Uses Groq Llama 3.3 70B with tool-calling to analyse win rates and improve strategies daily.

**Agent loop:**
1. **Observe** — queries 30 days of paper trade results
2. **Reason** — Groq Llama 3.3 70B calls tools to analyse each strategy
3. **Act** — saves insights + parameter notes to `strategy_notes` table
4. **Report** — returns summary included in 10 PM daily report

**Tools:**
```python
query_trade_performance(strategy, days=30)   # win rate, avg PNL, exit breakdown
get_overall_stats(days=30)                   # cross-strategy ranking
save_strategy_insight(strategy, insight, action, win_rate)  # persist learning
```

**Fallback:** pure Python statistical analysis if no LLM key configured

---

## AI Chatbot

**Endpoint:** `POST /api/chat/message`

**Fallback chain with strict timeouts:**
1. **Groq** (Llama 3.3 70B) — 5s timeout, max 800 tokens
2. **Gemini Flash** — 6s timeout, max 800 tokens
3. **OpenRouter** (Claude Haiku / Mistral) — 6s timeout
4. **Helpful fallback message** if all fail

Total asyncio budget: 8.5s (safely within Vercel 10s limit)

Context injected: live indices, FII/DII flows, sector performance, screener status, market regime.

---

## Earnings Results Page

**Route:** `/results`

Earningspulse.ai-style quarterly earnings analysis dashboard:
- **Rating system:** Excellent / Great / Good / Ok / Weak
- **Metric cards:** Revenue, Other Income, Operating Profit, OPM%, PAT, EPS with QoQ/YoY change
- **Mini trend charts:** Revenue, PAT, EPS inline bar sparklines
- **Filters:** Rating pills, search, sort (time/rating/sales/PAT), grid/list toggle
- **Live data:** Backend at `/api/market/quarterly-results`; falls back to curated sample data

---

## Daily Report (10 PM IST)

**Script:** `scripts/daily_report.py`

Sent via: **Telegram** + **Email (Resend)**

Report sections:
1. Screener hits per strategy (≥70% confidence count)
2. Paper trading today (exits, PNL, win rate, open exposure)
3. 30-day win rates by strategy
4. Strategy agent insights
5. Top picks for tomorrow (≥90% confidence)

**Failure handling:** Telegram fails → email error alert; Email fails → Telegram error alert

---

## Scheduled Jobs

| Time (IST) | Mon–Fri | Script |
|-----------|---------|--------|
| 9:30 AM | Open new paper trades from screener cache | `paper_trader.py --open` |
| 10:30 AM | Multibagger alert (morning run) | `multibagger_alert.py` |
| 2:00 PM | Multibagger alert (afternoon run) | `multibagger_alert.py` |
| 3:15 PM | Check paper trade exits before market close | `paper_trader.py --check` |
| 10:00 PM | Strategy agent analysis + daily Telegram/email report | `daily_report.py` |
| 1st of month | Monthly P&L summary | `monthly_report.py` |

---

## API Reference

### Screener
```
GET  /api/screener/results?strategy=vcp&universe=nifty500   # instant (cached)
GET  /api/screener/results?strategy=multibagger&universe=full
POST /api/screener/scan?strategy=multibagger&universe=nifty500  # force refresh
GET  /api/screener/status   # cache state for all strategies
```

**Strategies:** `vcp` | `ipo_base` | `rocket_base` | `breakout` | `rsi_reversal` | `golden_cross` | `multibagger` | `custom` (alias for multibagger)

### Market
```
GET /api/market/indices          # Nifty 50, Sensex, Bank Nifty, Nifty IT, Midcap
GET /api/market/global-indices   # GIFT NIFTY, Brent Crude, Dow Jones
GET /api/market/fii-dii          # FII/DII flows + 69-day history
GET /api/market/movers           # Top gainers/losers
GET /api/market/sectors          # Sector performance
GET /api/market/filings          # BSE corporate filings feed
GET /api/market/history/{ticker} # OHLCV candlestick data (lightweight-charts)
GET /api/market/quarterly-results # Earnings results with ratings
```

### Portfolio / Trades / Risk
```
GET /api/portfolio/summary       # Value, P&L, drawdown
GET /api/portfolio/positions     # Holdings list
GET /api/trades/history          # Trade blotter (filterable by status, date)
GET /api/risk/metrics            # VaR, Sharpe, drawdown
GET /api/strategies/performance  # Per-strategy stats
```

### Trading Journal
```
GET  /api/journal/trades         # All journal entries
POST /api/journal/trades         # Add trade
PUT  /api/journal/trades/{id}    # Update trade
DELETE /api/journal/trades/{id}  # Delete trade
GET  /api/journal/summary        # NAV (cost-basis), realized P&L, open count
GET  /api/journal/prices         # Live yFinance prices for open positions (parallel fetch)
GET  /api/journal/pnl-calendar   # Daily P&L calendar for equity curve
```

### AI + System
```
POST /api/chat/message           # AI chat with live market context
POST /api/telegram               # Telegram webhook
GET  /health                     # Health check
WS   /ws                         # Live P&L WebSocket (5s interval, local only)
```

---

## Frontend Pages

| Route | Page | Features |
|-------|------|---------|
| `/` | Market Terminal | Indices chips (Indian + Global), FII/DII flows, sector heatmap, top movers, BSE filings feed, AI chatbot |
| `/screener` | Screener | 7 strategies + CUSTOM, confidence badges, Supabase cache, background scan, paper trade auto-recording |
| `/portfolio` | Portfolio | HOLDINGS \| P&L \| TRADES \| LIVE tabs |
| `/results` | Earnings Results | Quarterly results with Excellent/Great/Good/Ok/Weak ratings, metric trends, mini charts |
| `/strategies` | Strategies | Per-strategy performance + signal cards |
| `/journal` | Trading Journal | Trade notes and analysis |
| `/settings` | Settings | Trading Agent Config \| Connections & Alerts \| Risk Monitor (3-tab, Risk merged here) |

---

## Chart System

OHLCV charts use **TradingView lightweight-charts** (native, no iframe):
- Data sourced from backend `/api/market/history/{ticker}` via yfinance
- Timeframes: 5m, 15m, 1h, 1D, 1W, 1M
- Candlestick + volume bars on separate price scale
- "Open in TradingView" external link preserved
- Slide-in drawer with spring animation
- Works for all NSE stocks + indices (^NSEI, BZ=F, ^DJI)

---

## Supabase Schema

```sql
-- Paper trades
CREATE TABLE IF NOT EXISTS paper_trades (
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
  status        TEXT DEFAULT 'open',  -- open/target_hit/sl_hit/expired/killed
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Strategy agent learnings
CREATE TABLE IF NOT EXISTS strategy_notes (
  strategy    TEXT PRIMARY KEY,
  insight     TEXT,
  action      TEXT,
  win_rate    DECIMAL(5,2),
  updated_at  DATE
);

-- Screener cache (survived serverless restarts)
CREATE TABLE IF NOT EXISTS screener_cache (
  strategy    TEXT NOT NULL,
  universe    TEXT NOT NULL,
  results     JSONB,
  scanned_at  TIMESTAMPTZ DEFAULT NOW(),
  is_scanning BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (strategy, universe)
);
```

---

## GitHub Secrets

| Secret | Status | Purpose |
|--------|--------|---------|
| `SUPABASE_URL` | ✅ Set | Database URL |
| `SUPABASE_KEY` | ✅ Set | Database service key |
| `RESEND_API_KEY` | ✅ Set | Email |
| `REPORT_EMAIL` | ✅ Set | Recipient email |
| `TELEGRAM_BOT_TOKEN` | ✅ Set | Bot token |
| `TELEGRAM_CHAT_ID` | ✅ Set | Chat ID |
| `GROQ_API_KEY` | ✅ Set | AI chat + strategy agent |
| `GEMINI_API_KEY` | ✅ Set | AI chat fallback #1 |
| `OPENROUTER_API_KEY` | Optional | AI chat fallback #2 |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11, Vercel serverless |
| Frontend | React 19 + Vite + TypeScript + Tailwind + Framer Motion |
| Charts | TradingView lightweight-charts (OHLCV candlesticks) + Recharts (analytics) |
| Server state | TanStack Query v5 |
| UI state | Zustand |
| Database | Supabase (PostgreSQL cloud) |
| AI Chat | Groq Llama 3.3 70B → Gemini Flash → OpenRouter (cascading fallback, <9s) |
| AI Agent | Groq + OpenRouter (tool-calling, self-improving strategy loop) |
| Market data | yfinance (batch downloads, 500 stocks / batch) |
| Email | Resend API |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions cron |
| Brokers | Zerodha Kite API (MCP integration) |

---

## Developer Tooling

```bash
# Frontend quality checks
cd dashboard
npm run typecheck   # tsc strict typecheck (no emit)
npm run lint        # ESLint v9 flat config (0 warnings allowed)
npm run build       # tsc + vite production build

# Backend checks
ruff check api/          # linting
ruff format --check api/ # formatting
```

**CI** (`.github/workflows/ci.yml`) runs automatically on every push to `main`:
- Frontend: lint → typecheck → build
- Backend: ruff lint → ruff format → pyright

**Architecture:** See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system map, data flows, and deployment guide.

---

## Performance Notes

- **Vercel hobby plan:** 10s function timeout — all endpoints designed to return in <2s
- **Screener:** GET /results never blocks; scans run in ThreadPoolExecutor background threads
- **AI chat:** 3-provider fallback with per-provider 5-6s timeout, total budget 8.5s
- **Caching:** 4h in-process + Supabase persistence; stale-while-revalidate pattern
- **yfinance batching:** 100 tickers per `yf.download()` call with `threads=True`

---

*Not financial advice. For educational and research purposes only.*
