# One Piece Quant — System Context

> Complete reference for all working components. Updated 2026-05-23.
> This file exists so future sessions never lose context.

---

## Live URLs

| Service | URL |
|---------|-----|
| **Dashboard** | https://luffy-labs.vercel.app |
| **API** | https://onepiece-labs.vercel.app |
| **GitHub** | https://github.com/Negi27921/one-piece |
| **Telegram webhook** | https://onepiece-labs.vercel.app/api/telegram |

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11, Vercel serverless |
| Provider layer | `core/` — abstract interfaces + env-var registry |
| Database | Supabase (PostgreSQL cloud) |
| Local cache | DuckDB (`data/db/iqf.duckdb`) |
| Frontend | React 19 + Vite 5 + TypeScript + Tailwind + Framer Motion |
| State | TanStack Query v5 (server) + Zustand (UI) |
| Charts | Recharts + TradingView lightweight-charts |
| Icons | Lucide |
| Brokers | Kite (primary, when set) → Dhan → Shoonya (SmartOrderRouter) |
| LLM (chat) | Groq Llama 3.3 70B → Gemini → OpenRouter cascade |
| LLM (agent) | Groq Llama 3.3 70B |
| Email | Resend API |
| Notifications | Telegram Bot API |
| Scheduling | GitHub Actions cron |

---

## Directory Structure

```
one-piece/
│
├── core/                         # ← NEW (2026-05-23)
│   ├── config.py                 # Unified Settings from env vars
│   ├── market_data.py            # Unified price-fetch API (no duplicates)
│   └── providers/
│       ├── base.py               # Abstract interfaces (ABCs)
│       ├── registry.py           # @lru_cache singletons — get_cache(), etc.
│       ├── market/               # yfinance (default), nse, mock
│       ├── ai/                   # groq, gemini, openrouter, chain, mock
│       ├── cache/                # memory (default), supabase, redis
│       └── notifications/        # telegram, email, multi
│
├── api/
│   ├── main.py                   # Local dev (DuckDB + WebSocket)
│   ├── cloud_main.py             # Vercel entry point
│   └── routers/
│       ├── screener.py           # L1 + L2 provider cache (not hardcoded Supabase)
│       ├── chat.py               # Uses core.market_data (fast_info only, <1s)
│       ├── portfolio.py          # Uses core.market_data.get_prices_bulk()
│       ├── journal.py            # Uses core.market_data.get_prices_bulk()
│       └── settings.py           # /env + /system-info endpoints
│
├── execution/
│   └── brokers/
│       ├── kite.py               # ← NEW: Zerodha Kite Connect adapter
│       ├── dhan.py               # Dhan (fallback if Kite not set)
│       └── shoonya.py            # Shoonya (final fallback)
│   └── router.py                 # SmartOrderRouter: Kite → Dhan → Shoonya
│
├── dashboard/src/
│   ├── App.tsx                   # Route-level lazy loading (8 pages)
│   ├── api/settings-queries.ts   # + useSystemInfo, updated EnvSummary type
│   └── pages/Settings.tsx        # + SystemInfoSection (provider health panel)
│
└── scripts/migrations/
    ├── 001_app_config.sql         # app_config table
    ├── 002_cache_entries.sql      # cache_entries (CACHE_PROVIDER=supabase)
    └── 003_signals_table.sql      # normalized signals (future)
```

---

## Provider System (core/)

Switch any provider by setting env var — no code changes:

| Env Var | Default | Options |
|---------|---------|---------|
| `MARKET_PROVIDER` | `yfinance` | `yfinance` \| `nse` \| `kite` \| `mock` |
| `AI_PROVIDER` | `groq` | `groq` \| `gemini` \| `openrouter` \| `mock` |
| `AI_FALLBACK_CHAIN` | `groq,gemini,openrouter` | comma-separated list |
| `CACHE_PROVIDER` | `memory` | `memory` \| `supabase` \| `redis` |
| `NOTIFY_PROVIDER` | `telegram` | `telegram` \| `email` \| `both` |

**Critical:** Set `CACHE_PROVIDER=supabase` on Vercel so screener results survive cold starts (run migration 002 first).

---

## Supabase Tables

| Table | Purpose |
|-------|---------|
| `paper_trades` | Auto paper trading activity |
| `strategy_notes` | Agent insights per strategy |
| `journal_trades` | Manual live trading journal |
| `app_config` | Kill switch state + agent config (migration 001) |
| `cache_entries` | L2 cache for CACHE_PROVIDER=supabase (migration 002) |
| `signals` | Normalized signal history (migration 003, future) |
| `screener_cache` | Legacy JSONB blob (still exists, being phased out) |
| `trades` | Live/paper order log |
| `daily_pnl` | Daily portfolio performance |
| `monthly_reports` | Monthly P&L summaries |

### Supabase credentials
- URL: `https://ohwgibzmaxfxivenbfhm.supabase.co`
- Anon key: in `.env` as `SUPABASE_KEY`
- Use service role key or SQL Editor for seeding/DDL

---

## Screener Cache Architecture

L1 (in-process dict, 6h TTL) → L2 (provider, 24h TTL) → background scan

L2 provider determined by `CACHE_PROVIDER`:
- `memory` — same as L1, lost on cold start
- `supabase` — `cache_entries` table, survives restarts
- `redis` — Upstash/Redis, distributed

Cache keys: `"screener:{strategy}:{universe}"`

---

## SmartOrderRouter Priority

1. `KiteBroker` — if `KITE_API_KEY` + `KITE_ACCESS_TOKEN` set
2. `DhanBroker` — if `DHAN_CLIENT_ID` + `DHAN_ACCESS_TOKEN` set
3. `ShoonyaBroker` — always available (paper mode if no live creds)

---

## Screener Strategies

| Strategy | Key Conditions | SL | Hold |
|----------|---------------|-----|------|
| **VCP** | 4-wave contraction, tight base, vol dry-up, EMA stack | 4% | 15d |
| **IPO Base** | First consolidation ≤120d data, tight range, vol dry-up | 6% | 20d |
| **Rocket Base** | 60%+ in 90d, ≤20% correction, vol contracting | 10% | 10d |
| **Breakout** | Within 3% of 52W high, 1.8× vol surge, range expansion | 8% | 10d |
| **RSI Reversal** | RSI recovered from <33, positive divergence, vol surge | 6% | 7d |
| **Golden Cross** | EMA20 crossed EMA50 ≤10 bars ago, SMA200 slope up | 8% | 20d |
| **Multibagger** | 12 conditions: tech DNA + fundamental proxies | 15% | 30d |

---

## Scheduled Jobs

| Time (IST) | Days | Script |
|-----------|------|--------|
| 9:30 AM | Mon–Fri | `paper_trader.py --open` |
| 10:30 AM | Mon–Fri | `multibagger_alert.py` |
| 2:00 PM | Mon–Fri | `multibagger_alert.py` |
| 3:15 PM | Mon–Fri | `paper_trader.py --check` |
| 10:00 PM | Mon–Fri | `daily_report.py` (incl. strategy_agent) |
| 1st of month | Always | `monthly_report.py` |

---

## Environment Variables

### Required
```
SUPABASE_URL, SUPABASE_KEY
GROQ_API_KEY (or GEMINI_API_KEY or OPENROUTER_API_KEY)
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
RESEND_API_KEY, REPORT_EMAIL
```

### Provider selection (all optional)
```
MARKET_PROVIDER=yfinance
AI_PROVIDER=groq
AI_FALLBACK_CHAIN=groq,gemini,openrouter
CACHE_PROVIDER=memory           # → supabase recommended on Vercel
NOTIFY_PROVIDER=telegram
```

### Broker credentials (all optional)
```
KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN
DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN
UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN
```

### Feature flags
```
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false
DEPLOYMENT_MODE=cloud
```

---

## GitHub Secrets Status (as of 2026-05-23)

```
SUPABASE_URL ✅
SUPABASE_KEY ✅
RESEND_API_KEY ✅
REPORT_EMAIL ✅ (negi2950@gmail.com)
TELEGRAM_BOT_TOKEN ✅
TELEGRAM_CHAT_ID ✅
GROQ_API_KEY ✅
GEMINI_API_KEY → add for fallback
OPENROUTER_API_KEY → add for fallback
KITE_API_KEY → add when ready for live Zerodha integration
```

---

## API Endpoints (full list)

### Screener
```
GET  /api/screener/results?strategy=vcp&universe=nifty500&min_confidence=70
POST /api/screener/scan?strategy=multibagger
GET  /api/screener/status
POST /api/screener/prewarm
```

### Market
```
GET /api/market/status, /indices, /global-indices, /fii-dii, /fii-dii/today
GET /api/market/fii-dii/sectors, /movers, /sectors, /filings
GET /api/market/corporate-actions, /advances-declines, /results-calendar
GET /api/market/quarterly-results, /history/{ticker}, /quote
```

### Portfolio / Journal / Risk / Strategies
```
GET/POST/PUT/DELETE /api/portfolio/* (positions, equity-curve, pnl-calendar, paper-trades, live)
GET/POST/PUT/DELETE /api/journal/* (trades, summary, prices, positions, pnl-calendar)
GET /api/risk/metrics, /risk/limits
GET /api/strategies/performance, /signals, /allocation
GET /api/trades/orders, /fills, /stats
```

### Settings
```
GET  /api/settings/providers
POST /api/settings/providers/probe
GET  /api/settings/brokers
GET  /api/settings/alerts
POST /api/settings/alerts/test-telegram
GET  /api/settings/env                  # provider names + mode
GET  /api/settings/system-info          # full credential status
GET  /api/settings/agent-config
PUT  /api/settings/agent-config
```

### System + Chat
```
GET  /api/system/health, /kill-switch/status, /audit-log
POST /api/chat/message
POST /api/telegram
GET  /health
WS   /ws  (local only)
```

---

## Frontend Pages

| Route | Page | Key Features |
|-------|------|-------------|
| `/` | Market Terminal | Indices, FII/DII bars, sector heatmap, movers, BSE filings, AI chat |
| `/screener` | Screener | 7 strategies × 2 universes, confidence badges, background scan |
| `/portfolio` | Portfolio | HOLDINGS \| P&L \| TRADES \| LIVE tabs |
| `/risk` | Risk | Drawdown chart, VaR, Sharpe, kill switch, sector limits |
| `/strategies` | Strategies | Per-strategy cards, signals, approve/reject |
| `/journal` | Trading Journal | Add/exit/delete manual trades; cost-basis NAV |
| `/results` | Earnings Results | Quarterly rated cards (Excellent→Weak), mini sparklines |
| `/settings` | Settings | Agent config · System Providers panel · LLM · Brokers · Alerts · Risk |

All pages lazy-loaded via `React.lazy()` + `Suspense`.

---

## Key Design Decisions

1. **Provider abstraction** — All external deps abstracted. Swap by changing env vars.
2. **L2 cache** — Screener results go through `get_cache()`, not hardcoded Supabase. `CACHE_PROVIDER=supabase` recommended on Vercel.
3. **fast_info only** — `ticker.info` banned from all API paths (3–10s). All context uses `fast_info` (<1s).
4. **Route-level lazy loading** — 8 pages split into separate chunks; first paint ~80 KB.
5. **SmartOrderRouter** — Auto-selects best available broker from credentials.
6. **Fixed ₹25,000 paper trades** — Simplifies strategy comparison.
7. **Hermes-style agent loop** — Groq function-calling analyses 30d paper trades nightly.
8. **Matrix/space terminal theme** — #020407 bg, #00ff87 primary, glassmorphism cards, JetBrains Mono.
9. **Dual-channel failure alerts** — Email fails → Telegram; Telegram fails → email.
10. **Vercel 10s budget** — Every endpoint has been profiled to fit.

---

## Documentation Files
- `README.md` — Full project guide with API reference, setup, env vars
- `ARCHITECTURE.md` — Deep technical architecture (flows, provider layer, bundle chunks)
- `SYSTEM_CONTEXT.md` — This file: operational reference for future sessions
