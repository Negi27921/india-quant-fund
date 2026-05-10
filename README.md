# 🏴‍☠️ One Piece Quant — Automated Indian Equity Trading System

> Production-grade automated hedge fund for NSE/BSE cash segment.
> Self-improving AI screeners, paper trading, and real-time dashboard.

**Live Dashboard:** [luffy-labs.vercel.app](https://luffy-labs.vercel.app)
**API:** [onepiece-labs.vercel.app](https://onepiece-labs.vercel.app)
**GitHub:** [Negi27921/india-quant-fund](https://github.com/Negi27921/india-quant-fund)

---

## What It Does

- **Screens 2,137 NSE stocks** across 7 strategies, 3× daily
- **Paper trades ₹25,000/pick** on every ≥95% confidence signal automatically
- **Self-improving AI agent** (Hermes-style) analyses win rates and improves strategies daily
- **10 PM daily Telegram + email report** with performance, insights, and top picks
- **Real-time dashboard** — market data, screener, portfolio, risk, strategies
- **Kill switch + target/SL** on every paper trade, automatic exit tracking

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
9 API routers          6 pages                  Trade exits
WebSocket              Matrix theme             10PM report
Groq AI chat           TanStack Query
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
npm run dev                   # → http://localhost:5173
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

| Strategy | Key Conditions | Target | SL | Hold Days |
|----------|---------------|--------|-----|-----------|
| **VCP** | Volatility contraction, volume dry-up, tight base | 8% | 4% | 15 |
| **IPO Base** | Recent IPO (<2yr), tight range, volume recovery | 12% | 5% | 20 |
| **Rocket Base** | Short tight base after >30% move, breakout vol | 15% | 6% | 10 |
| **Breakout** | 52W high, 3× avg volume, RSI 55–75 | 7% | 3% | 10 |
| **RSI Reversal** | RSI <35→50 reversal, above SMA200, vol pickup | 6% | 3% | 7 |
| **Golden Cross** | EMA50 crosses above EMA200, rising volume | 10% | 4% | 20 |
| **Multibagger** | 11-condition scan (below) | 20% | 7% | 30 |

### Multibagger 11 Conditions (≥10/11 = 95% confidence)
```
1.  EMA Stack:        EMA9 > EMA20 > EMA50
2.  Above SMA200:     Price > SMA200
3.  SMA200 Slope:     Rising >0.3% per 30 days
4.  RSI Zone:         55 ≤ RSI ≤ 78
5.  Recovery:         +15% from 90-day low
6.  Not Overextended: Within 40% of 52W High
7.  Base Forming:     20d range < 30% of 52W range
8.  Inst. Accum:      5d vol > 20d vol × 1.1
9.  Vol Re-entry:     3d avg ≥ 20d avg × 1.5
10. Not Extended:     LTP within 20% of EMA50
11. Liquidity:        Avg volume > 75,000 shares
```

**Confidence = conditions_passed / 11 × 100. Only ≥95% (≥10/11) passes.**

---

## Paper Trading System

**Script:** `scripts/paper_trader.py`

**Rules:**
- Fixed **₹25,000 per trade**
- Only stocks with confidence **≥ 95%**
- Max **30 open trades** simultaneously
- **Kill switch**: halt new trades if daily realised loss > 15%
- Auto-exit on: **target hit** / **SL hit** / held past **hold_days**

**Supabase table:** `paper_trades`

**Exit statuses:** `open` → `target_hit` / `sl_hit` / `expired` / `killed`

---

## Strategy Agent (Hermes-Inspired Self-Improving AI)

**Script:** `scripts/strategy_agent.py`

Based on the [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) tool-calling architecture.

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

## Daily Report (10 PM IST)

**Script:** `scripts/daily_report.py`

Sent via: **Telegram** + **Email (Resend)**

Report sections:
1. Screener hits per strategy (≥95% confidence count)
2. Paper trading today (exits, PNL, win rate, open exposure)
3. 30-day win rates by strategy
4. Strategy agent insights
5. Top picks for tomorrow (≥97% confidence)

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
GET  /api/screener/results?strategy=vcp&universe=nifty500
POST /api/screener/scan?strategy=multibagger&universe=full
GET  /api/screener/status
```

### Market
```
GET /api/market/indices      # Nifty 50, Sensex, Bank Nifty
GET /api/market/fii-dii      # FII/DII flows + 69-day history
GET /api/market/movers       # Top gainers/losers
GET /api/market/sectors      # Sector performance
GET /api/market/filings      # BSE corporate filings feed
```

### Portfolio / Trades / Risk
```
GET /api/portfolio/summary   # Value, P&L, drawdown
GET /api/portfolio/positions # Holdings list
GET /api/trades/history      # Trade blotter
GET /api/risk/metrics        # VaR, Sharpe, drawdown
GET /api/strategies/performance  # Per-strategy stats
```

### AI + System
```
POST /api/chat/message       # AI chat with live market context
POST /api/telegram           # Telegram webhook
GET  /health                 # Health check
WS   /ws                     # Live P&L WebSocket (5s interval)
```

---

## Frontend Pages

| Route | Page | Features |
|-------|------|---------|
| `/` | Market Terminal | Indices, FII/DII, sector heatmap, top movers, BSE filings |
| `/screener` | Screener | 7 strategies, confidence badges, Supabase cache, force-scan |
| `/portfolio` | Portfolio | HOLDINGS \| P&L \| TRADES \| LIVE tabs |
| `/risk` | Risk | VaR, drawdown chart, sector exposure, kill switch |
| `/strategies` | Strategies | Per-strategy performance + signal cards |
| `/settings` | Settings | Paper/live toggle, kill switch, thresholds |

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

-- Screener cache (if not exists)
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
| `RESEND_API_KEY` | ✅ Set | Email (re_faPbhjDX...) |
| `REPORT_EMAIL` | ✅ Set | negi2950@gmail.com |
| `TELEGRAM_BOT_TOKEN` | ✅ Set | Bot token |
| `TELEGRAM_CHAT_ID` | ✅ Set | Chat ID |
| `GROQ_API_KEY` | ⚠️ Add | Strategy agent LLM |
| `OPENROUTER_API_KEY` | Optional | LLM fallback |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11, Vercel serverless |
| Frontend | React 19 + Vite + TypeScript + Tailwind + Framer Motion |
| Charts | Recharts |
| Server state | TanStack Query v5 |
| UI state | Zustand |
| Database | Supabase (PostgreSQL cloud) |
| Local cache | DuckDB |
| AI Chat | Groq Llama 3.3 70B → DeepSeek → Gemini → OpenRouter |
| AI Agent | Groq + OpenRouter (Hermes tool-calling) |
| Email | Resend API |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions cron |
| Brokers | Dhan API (primary) + Shoonya/Finvasia (failover) |

---

## Design

- **Background:** `#020407` (space black)
- **Primary:** `#00ff87` (matrix green)
- **Font:** JetBrains Mono
- **Style:** Matrix/space terminal, glassmorphism cards
- **Logo:** Luffy straw hat silhouette in matrix green (`/favicon.svg`)
- **Title:** Luffy Labs | One Piece Quant Terminal

---

*Not financial advice. For educational and research purposes only.*
