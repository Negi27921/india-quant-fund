# One Piece — System Architecture

> Last updated: 2026-05-23

## Overview

One Piece is a full-stack automated quantitative hedge fund for Indian equities (NSE/BSE). Two runtime environments:

| Mode | Entry point | Storage | WebSocket | Deployed on |
|------|------------|---------|-----------|-------------|
| **Local** | `api/main.py` | DuckDB | Yes (`/ws`) | Developer machine |
| **Cloud** | `api/cloud_main.py` | Supabase | No | Vercel (serverless) |

---

## Directory Map

```
one-piece/
├── core/                       # Provider abstraction layer ← NEW
│   ├── config.py               # Unified Settings class (all env vars, one import)
│   ├── market_data.py          # Public price-fetch API (replaces 3 duplicate helpers)
│   └── providers/
│       ├── base.py             # Abstract interfaces: MarketDataProvider, AIProvider,
│       │                       #   CacheProvider, NotificationProvider, BrokerProvider
│       ├── registry.py         # Factory singletons with @lru_cache — get_market_provider(),
│       │                       #   get_ai_provider(), get_cache(), get_notifier()
│       ├── market/             # yfinance (default), nse (nsepython), mock
│       ├── ai/                 # groq, gemini, openrouter, chain (cascade), mock
│       ├── cache/              # memory (default), supabase (cache_entries), redis
│       └── notifications/      # telegram, email (Resend), multi (both)
│
├── api/                        # FastAPI application
│   ├── _config.py              # Shared CORS, versioning, router prefixes
│   ├── main.py                 # Local dev entry point (DuckDB + WebSocket)
│   ├── cloud_main.py           # Vercel entry point (Supabase stubs, no WebSocket)
│   ├── middleware/
│   │   └── security.py         # HSTS, X-Frame, CSP, Referrer-Policy headers
│   └── routers/
│       ├── chat.py             # AI assistant — uses core.market_data (fast_info only)
│       ├── journal.py          # Trading journal CRUD + NAV + parallel price fetch
│       ├── market.py           # Indices, FII/DII, movers, filings, OHLCV
│       ├── portfolio.py        # Paper/live positions, equity curve, P&L calendar
│       ├── risk.py             # Drawdown, Sharpe, kill switch
│       ├── screener.py         # 7-strategy screener, L1+L2 cache, background scan
│       ├── settings.py         # LLM/broker/alert config, system-info endpoint
│       ├── strategies.py       # Strategy performance, signals, allocation
│       ├── system.py           # Kill switch, audit log (local DuckDB)
│       ├── telegram_bot.py     # Telegram webhook (cloud only)
│       └── trades.py           # Screener auto-trade log
│
├── execution/                  # Order management system
│   ├── brokers/
│   │   ├── base.py             # BrokerInterface ABC + dataclasses
│   │   ├── kite.py             # Zerodha Kite Connect — real-time, primary ← NEW
│   │   ├── dhan.py             # Dhan — fallback
│   │   └── shoonya.py          # Shoonya/Finvasia — final fallback
│   ├── router.py               # SmartOrderRouter: Kite → Dhan → Shoonya
│   ├── oms.py                  # Order lifecycle management
│   ├── slippage.py             # Slippage estimation
│   └── reconciliation.py       # Position reconciliation
│
├── dashboard/                  # React 19 + TypeScript (Vite 5)
│   └── src/
│       ├── App.tsx             # Route-level lazy loading (React.lazy + Suspense) ← UPDATED
│       ├── api/
│       │   ├── client.ts       # Typed HTTP wrapper (timeout, retry, ApiError)
│       │   ├── queries.ts      # Portfolio, risk, strategy, system hooks
│       │   ├── market-queries.ts
│       │   ├── pnl-queries.ts
│       │   ├── settings-queries.ts  # + useSystemInfo hook ← UPDATED
│       │   └── types.ts
│       └── pages/
│           ├── Settings.tsx    # + SystemInfoSection (provider health) ← UPDATED
│           └── [6 other pages]
│
├── scripts/
│   └── migrations/
│       ├── 001_app_config.sql      # app_config table (kill switch seed + agent config)
│       ├── 002_cache_entries.sql   # cache_entries table for CACHE_PROVIDER=supabase
│       └── 003_signals_table.sql   # Normalized signals table (future migration path)
│
├── risk/                       # Kill switch, position sizer, drawdown, limits
├── data/                       # Data pipeline, DuckDB + Supabase storage
├── backtest/                   # India equity backtester
└── .github/workflows/          # CI + scheduled jobs
```

---

## Provider Abstraction Layer

The `core/` package decouples all external dependencies from business logic. Every router that needs market data, AI, or caching imports from `core/` — never directly from `yfinance`, `groq`, etc.

### Pattern

```python
# Any router — one line to swap providers
from core.providers.registry import get_cache, get_market_provider

cache = get_cache()            # memory | supabase | redis — per CACHE_PROVIDER env var
prices = get_market_provider() # yfinance | nse | kite — per MARKET_PROVIDER env var
```

### Singleton lifecycle

Registry functions use `@lru_cache(maxsize=1)` — each process creates exactly one instance per provider type. First call reads the env var and constructs; subsequent calls return the same object. On Vercel serverless, each lambda worker has its own singleton (not shared across instances — that's why `CACHE_PROVIDER=supabase` matters for cross-instance state).

### Adding a new provider

1. Create `core/providers/<type>/<name>_provider.py` implementing the ABC from `base.py`
2. Add a branch in `registry.py` matching the new env var value
3. Set `MARKET_PROVIDER=yourname` — zero other code changes needed

---

## Screener Cache Architecture

Two-level cache designed for Vercel serverless cold starts:

```
Request arrives
      │
      ▼
L1: in-process dict          ← warm after first request in this lambda worker
    TTL = 6h
    (lost on cold start)
      │ miss
      ▼
L2: CacheProvider            ← configured via CACHE_PROVIDER
    TTL = 24h
    ┌─────────────────────────────────────┐
    │ memory   → same as L1 (no benefit)  │
    │ supabase → cache_entries table      │ ← recommended on Vercel
    │ redis    → Upstash/Redis            │ ← best for high traffic
    └─────────────────────────────────────┘
      │ miss
      ▼
Background scan              ← ThreadPoolExecutor, never blocks GET
Returns stale or []          ← GET responds immediately with is_scanning=true
```

Cache keys: `"screener:{strategy}:{universe}"` (e.g. `"screener:vcp:nifty500"`)

---

## Smart Order Router

```
place_order(order)
      │
      ▼
_default_primary()
  ├─ settings.has_kite → KiteBroker()   (KITE_API_KEY + KITE_ACCESS_TOKEN set)
  └─ fallback          → DhanBroker()   (DHAN_CLIENT_ID + DHAN_ACCESS_TOKEN set)
      │
      ▼
primary.place_order(order)
  │ success → return result
  │ failure (≥3 consecutive) → ShoonyaBroker fallback
      │
      ▼
fallback.place_order(order)
```

To upgrade to Kite execution: add `KITE_API_KEY` and `KITE_ACCESS_TOKEN` to env — no code changes.

---

## Frontend Architecture

### Routing
`react-router-dom` v6 with a shared `<Layout>` wrapper. All 8 pages are **lazy-loaded** via `React.lazy()` — each page JS chunk is downloaded only when the user first navigates to that route.

```
/               → MarketPage      (lazy)
/screener       → ScreenerPage    (lazy)
/portfolio      → PortfolioPage   (lazy)
/risk           → RiskPage        (lazy)
/strategies     → StrategiesPage  (lazy)
/journal        → TradingJournalPage (lazy)
/results        → ResultsPage     (lazy)
/settings       → SettingsPage    (lazy)
```

First paint downloads ~80 KB instead of ~235 KB.

### Data Fetching
All server state uses `@tanstack/react-query`. Key behaviours:
- Default timeout: 10s, chat endpoints: 35s
- GET: one automatic retry on network failure (not 4xx/5xx)
- Errors surface as `ApiError(message, status, path)`

### Bundle Chunks (Vite `manualChunks`)
| Chunk | Contents | Gzip |
|-------|---------|------|
| `vendor-charts` | recharts | ~112 KB |
| `vendor-motion` | framer-motion | ~40 KB |
| `vendor-icons` | lucide-react | ~6 KB |
| `vendor-query` | @tanstack/react-query | ~15 KB |
| `nse-data` | NSE 500 symbol list | ~38 KB |
| Per-page chunks | Each page file | 5–30 KB each |

---

## Settings Page — Provider Health

The Settings → Connections tab shows a live provider status grid via `GET /api/settings/system-info`:

```json
{
  "market": "yfinance",
  "ai": "groq",
  "ai_chain": ["groq", "gemini", "openrouter"],
  "cache": "memory",
  "notify": "telegram",
  "has_kite": false,
  "has_dhan": false,
  "has_groq": true,
  "has_gemini": false,
  "has_redis": false,
  "live_trading": false,
  "paper_trading": true,
  "deployment": "cloud",
  "brokers": { "dhan": false, "kite": false, "shoonya": false },
  "notifications": { "telegram": true, "email": false }
}
```

---

## Backend: Key Design Decisions

### Timeout budget (Vercel 10s limit)
| Operation | Old time | New time | Fix |
|-----------|---------|----------|-----|
| `ticker.info` in chat context | 3–10s | — | Replaced with `fast_info` (<1s) |
| Bulk price fetch | Sequential | Parallel | `ThreadPoolExecutor`, 7s total timeout |
| Screener scan | Blocks GET | Background | Never blocks; returns immediately with `is_scanning` |
| AI cascade | No timeout | 5s + 6s + 6s | Hard per-provider timeout, 8.5s total budget |

### NAV computation
`/api/journal/summary` computes NAV from `buy_price × quantity` (cost basis) — no yFinance in the critical path. Live prices fetched separately via `/api/journal/prices` using parallel threads.

### WebSocket (local only)
Vercel serverless doesn't support persistent connections. `/ws` (portfolio snapshots every 5s) is only in `main.py`. Cloud frontend polls HTTP endpoints.

### Dual system router
- `api/routers/system.py` — full DuckDB-backed (local dev)
- Inline stubs in `cloud_main.py` — lightweight (Vercel)

---

## Supabase Migrations

Run once in Supabase SQL Editor in order:

| File | Creates | Enables |
|------|---------|---------|
| `001_app_config.sql` | `app_config` | Persistent kill switch + agent config |
| `002_cache_entries.sql` | `cache_entries` | `CACHE_PROVIDER=supabase` (cross-lambda cache) |
| `003_signals_table.sql` | `signals` | Normalized signal history (future screener path) |

---

## Data Flows

### Screener / Auto-Trades
```
GitHub Actions (paper_trading.yml) — 9:30 AM
  → scripts/paper_trader.py --open
      → GET /api/screener/results?strategy=vcp&min_confidence=70
          → L1/L2 cache hit (instant)
      → POST /api/portfolio/paper-positions  → Supabase paper_trades

GitHub Actions — 3:15 PM
  → scripts/paper_trader.py --check
      → fetch LTP via core.market_data.get_prices_bulk()
      → PUT /api/portfolio/paper-positions/{ticker}/exit
```

### Daily Report
```
GitHub Actions (daily_report.yml) — 10:00 PM
  → scripts/strategy_agent.py
      → Groq function-calling → reads paper_trades (30d)
      → saves insights → Supabase strategy_notes
  → scripts/daily_report.py
      → screener hits, P&L summary, top picks, agent insights
      → Telegram + Email (Resend)
```

### AI Chat Request
```
POST /api/chat/message { symbol: "RELIANCE", messages: [...] }
  → core.market_data.get_stock_context("RELIANCE", fast=True)   # <1s, fast_info only
  → core.providers.registry.get_ai_chain().complete(...)
      → GroqProvider  (timeout: 5s)
      → GeminiProvider (timeout: 6s, if Groq fails)
      → OpenRouterProvider (timeout: 6s, if Gemini fails)
  → response within 8.5s total budget
```

---

## CI/CD

### `.github/workflows/ci.yml`
1. **Frontend**: `npm ci` → `eslint` → `tsc --noEmit` → `vite build`
2. **Backend**: `ruff check` → `ruff format --check` → `pyright`

### Scheduled automation (independent of CI)
| File | Schedule | Job |
|------|---------|-----|
| `screener_scan.yml` | Daily weekdays | NSE 500 full scan |
| `paper_trading.yml` | 9:30 AM + 3:15 PM | Open/check paper trades |
| `daily_report.yml` | 10:00 PM | Strategy agent + report |
| `monthly_report.yml` | 1st of month | P&L summary |
| `multibagger_alert.yml` | 10:30 AM + 2:00 PM | High-conviction alerts |
| `keep-alive.yml` | Every 20h | Prevent Vercel cold start |
