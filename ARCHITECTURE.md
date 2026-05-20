# One Piece — System Architecture

## Overview

One Piece is a full-stack automated quantitative hedge fund for Indian equities (NSE/BSE). It consists of a FastAPI backend, a React dashboard, and a set of Python strategy/execution modules. The system supports two runtime environments:

| Mode | Entry point | Storage | WebSocket | Deployed on |
|------|------------|---------|-----------|-------------|
| **Local** | `api/main.py` | DuckDB | Yes (`/ws`) | Developer machine |
| **Cloud** | `api/cloud_main.py` | Supabase | No | Vercel (serverless) |

---

## Directory Map

```
one-piece/
├── api/                    # FastAPI application
│   ├── _config.py          # Shared CORS, versioning, router prefixes (single source of truth)
│   ├── main.py             # Local dev entry point (DuckDB + WebSocket)
│   ├── cloud_main.py       # Vercel entry point (Supabase stubs, no WebSocket)
│   ├── middleware/
│   │   └── security.py     # Security headers middleware
│   └── routers/
│       ├── chat.py         # Claude AI assistant (streaming)
│       ├── journal.py      # Trading journal CRUD + NAV summary
│       ├── market.py       # Live market data (yFinance)
│       ├── portfolio.py    # Portfolio positions and equity curve
│       ├── risk.py         # Risk metrics and drawdown analysis
│       ├── screener.py     # NSE/BSE stock screener + auto-scanner
│       ├── settings.py     # User preferences (stored in Supabase)
│       ├── strategies.py   # Strategy definitions and backtests
│       ├── system.py       # Kill switch, audit log (local DuckDB)
│       ├── telegram_bot.py # Telegram alerts (cloud only)
│       └── trades.py       # Screener auto-trade log
├── dashboard/              # React + TypeScript frontend (Vite)
│   ├── src/
│   │   ├── api/client.ts   # Typed HTTP wrapper (timeout, retry, ApiError)
│   │   ├── lib/
│   │   │   ├── constants.ts    # API_BASE, env config
│   │   │   ├── nse-stocks.ts   # Static NSE 500 symbol list (~large, lazy chunk)
│   │   │   └── utils.ts        # formatCurrency, formatPct, etc.
│   │   ├── pages/          # One file per route
│   │   ├── components/     # Reusable UI (cards, charts, tables, layout)
│   │   └── hooks/          # React Query hooks (data fetching)
│   ├── vite.config.ts      # Build config — code-split vendor chunks
│   └── vercel.json         # SPA rewrite rules for Vercel
├── data/                   # Data pipeline and storage layer
│   ├── storage/            # DuckDB abstraction
│   └── pipeline/           # EOD data ingestion jobs
├── execution/              # Order management system
│   ├── brokers/            # Broker adapters (Zerodha Kite)
│   ├── oms.py              # Order lifecycle management
│   ├── router.py           # Smart order routing
│   ├── slippage.py         # Slippage estimation
│   └── reconciliation.py   # Position reconciliation
├── risk/                   # Risk management layer
│   ├── kill_switch.py      # Automated circuit breaker
│   ├── manager.py          # Unified risk checks
│   ├── limits.py           # Position / portfolio limits
│   ├── drawdown.py         # Drawdown tracking
│   ├── liquidity.py        # Liquidity checks
│   └── position_sizer.py   # Kelly / fixed-fraction sizing
├── backtest/               # Strategy backtesting engine
├── orchestration/          # Scheduling and job coordination
├── monitoring/             # Alerting and observability
├── reporting/              # Report generation (daily/monthly)
├── config/                 # Strategy and system configuration files
└── .github/workflows/      # CI/CD pipelines
```

---

## Frontend Architecture

### Routing
`react-router-dom` v6 with a shared `<Layout>` wrapper. All pages are statically imported (no lazy loading at the route level — pages are small; the large chunks are vendor libraries).

```
/               → Market (live market overview)
/screener       → Screener (stock scanner)
/portfolio      → Portfolio (holdings, P&L, equity curve)
/risk           → Risk (drawdown, kill switch status)
/strategies     → Strategies (backtest results)
/journal        → Trading Journal (manual trade log)
/settings       → Settings
/results        → Backtest results detail
```

### Data Fetching
All server state uses `@tanstack/react-query`. The typed HTTP client at `api/client.ts` is the only place `fetch()` is called. Key behaviours:
- Default timeout: 10 seconds
- Chat endpoints: 35 seconds
- GET requests: one automatic retry on network failure (not on 4xx/5xx)
- Errors surface as `ApiError(message, status, path)`

### Bundle Chunks (Vite `manualChunks`)
| Chunk | Contents |
|-------|---------|
| `vendor-charts` | recharts |
| `vendor-motion` | framer-motion |
| `vendor-icons` | lucide-react |
| `vendor-query` | @tanstack/react-query |
| `nse-data` | nse-stocks.ts (static symbol list) |

---

## Backend Architecture

### Shared Configuration (`api/_config.py`)
Single source of truth for CORS origins, allowed methods/headers, and router prefix strings. Both `main.py` and `cloud_main.py` import from here.

### Key Design Decisions

**NAV computation (journal)**
The `/api/journal/summary` endpoint computes NAV from `buy_price × quantity` (cost basis) rather than live prices. This avoids yFinance HTTP calls in the critical path, which exceeded Vercel's serverless timeout. Live prices are fetched separately via `/api/journal/prices` using parallel `ThreadPoolExecutor` with a 6-second total timeout.

**WebSocket (local only)**
Vercel's serverless functions do not support persistent connections. The `/ws` WebSocket endpoint (portfolio snapshots every 5s) is only available in `main.py` (local). The cloud frontend polls HTTP endpoints instead.

**System router (dual implementation)**
- `api/routers/system.py` — full DuckDB-backed implementation (local)
- Inline stubs in `cloud_main.py` — lightweight responses (cloud); DuckDB not available on Vercel

### Security Middleware (`api/middleware/security.py`)
Adds HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, and CSP headers to all responses.

---

## Data Flow: Live Portfolio

```
Trading Journal (manual entries)
    │
    ▼
POST /api/journal/trades  →  Supabase (cloud) / DuckDB (local)
    │
GET /api/journal/summary  →  cost-basis NAV + realized P&L (no yFinance)
GET /api/journal/prices   →  live prices via yFinance (parallel, 6s timeout)
    │
    ▼
Portfolio page: LIVE tab merges summary + prices to show unrealized P&L
```

## Data Flow: Screener / Auto-Trades

```
GitHub Actions cron (screener_scan.yml, paper_trading.yml)
    │
    ▼
Python strategy engine → signals
    │
    ▼
POST /api/trades  →  Supabase paper_trades table
    │
GET /api/trades   →  Portfolio SCREENER AUTO-TRADES tab
```

---

## Deployment

### Frontend (Vercel)
```bash
cd dashboard
npm run build        # tsc + vite build → dist/
vercel --prod        # deploy dist/ with vercel.json rewrite rules
```
Environment variable required: `VITE_API_BASE` (URL of the deployed API).

### Backend (Vercel Serverless)
Entry point: `api/cloud_main.py` (configured in `vercel.json`).
No persistent state — all data in Supabase.

### Local Development
```bash
# Backend
uvicorn api.main:app --reload --port 8000

# Frontend
cd dashboard && npm run dev   # http://localhost:3000
```

---

## CI/CD (`.github/workflows/ci.yml`)

Runs on every push/PR to `main`:
1. **Frontend job**: `npm ci` → `eslint` → `tsc --noEmit` → `vite build`
2. **Backend job**: `ruff check` → `ruff format --check` → `pyright` (informational)

Scheduled automation workflows (independent of CI):
- `screener_scan.yml` — daily NSE 500 scan
- `paper_trading.yml` — paper trade execution
- `daily_report.yml` / `monthly_report.yml` — performance reports
- `multibagger_alert.yml` — high-momentum alerts
- `keep-alive.yml` — prevents Vercel cold starts
