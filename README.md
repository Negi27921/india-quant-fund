---
title: India Quant Fund API
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
pinned: true
app_port: 7860
---

# India Quant Fund — System Architecture

> Production-grade automated hedge fund for Indian equity markets. Full-stack FastAPI + React/TypeScript system with real-time data feeds, multi-strategy screener, risk management, and AI-assisted trade analysis.

**Live Dashboard:** https://dashboard-two-plum-91.vercel.app  
**Backend (tunnel):** https://thoughts-ourselves-scheduling-dna.trycloudflare.com  
**GitHub:** https://github.com/Negi27921/india-quant-fund

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Directory Structure](#directory-structure)
3. [Backend API](#backend-api)
4. [Frontend Dashboard](#frontend-dashboard)
5. [Stock Screener](#stock-screener)
6. [FII / DII Data Pipeline](#fii--dii-data-pipeline)
7. [Market Data Layer](#market-data-layer)
8. [Strategy Engine](#strategy-engine)
9. [Risk Management](#risk-management)
10. [Deployment](#deployment)
11. [Data Sources](#data-sources)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Vercel (React + Vite)                                       │
│  dashboard-two-plum-91.vercel.app                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Market   │ │ Screener │ │Portfolio │ │  Strategies  │   │
│  │Dashboard │ │  Page    │ │  Page    │ │   Page       │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS (Cloudflare Tunnel)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Backend  (uvicorn, port 8000)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ /market  │ │/screener │ │/portfolio│ │  /strategies │   │
│  └────┬─────┘ └────┬─────┘ └──────────┘ └──────────────┘   │
│       │            │                                         │
│  ┌────▼─────┐ ┌────▼─────────────┐                         │
│  │ Data     │ │  Scan Engine      │                         │
│  │ Cache    │ │  (yfinance batch) │                         │
│  │ (dict)   │ │  503 / 2137 stks  │                         │
│  └────┬─────┘ └──────────────────┘                         │
│       │                                                      │
│  ┌────▼──────────────────────────────────────────────────┐  │
│  │  Data Sources                                          │  │
│  │  • fii_dii_data/ (history.json, latest.json, sectors) │  │
│  │  • yfinance (OHLCV, quotes, history)                  │  │
│  │  • NSE API (indices, movers, corporate actions)        │  │
│  │  • BSE API (filings, advances/declines)               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
india-quant-fund/
├── api/                        # FastAPI backend
│   ├── main.py                 # App factory, router registration, CORS
│   ├── routers/
│   │   ├── market.py           # Market data endpoints (indices, FII/DII, movers, sectors)
│   │   ├── screener.py         # Multi-strategy stock screener
│   │   ├── portfolio.py        # Portfolio holdings, P&L, allocation
│   │   ├── trades.py           # Trade history, blotter
│   │   ├── risk.py             # Risk metrics (VaR, drawdown, Sharpe)
│   │   ├── strategies.py       # Strategy performance dashboard
│   │   ├── settings.py         # App configuration
│   │   ├── chat.py             # AI chat assistant (Claude)
│   │   └── system.py           # Health checks, system status
│   └── fii_dii_data/           # Rich FII/DII dataset (from MrChartist/fii-dii-data)
│       ├── history.json        # 69 rows: cash + futures + options + PCR + sentiment
│       ├── latest.json         # Most recent full-day FAO summary
│       └── sectors.json        # Sector-wise FII ownership data
│
├── dashboard/                  # React + TypeScript + Vite frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Market.tsx      # Market dashboard (indices, FII/DII, movers, sectors)
│   │   │   ├── Screener.tsx    # Multi-strategy stock screener
│   │   │   ├── Portfolio.tsx   # Portfolio page
│   │   │   ├── Strategies.tsx  # Strategy performance
│   │   │   └── ...
│   │   ├── api/
│   │   │   ├── client.ts       # Axios client with baseURL from VITE_API_URL
│   │   │   └── market-queries.ts # React Query hooks + TypeScript interfaces
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx # Navigation sidebar
│   │   │   │   └── Header.tsx  # Page header
│   │   │   └── charts/         # Recharts wrappers
│   │   ├── styles/
│   │   │   └── globals.css     # Chakra UI design tokens (full dark/light theme)
│   │   └── lib/
│   │       └── nse-stocks.ts   # 2,137 NSE EQ-series stocks (from sharewatch)
│   └── vercel.json             # Vite framework, SPA rewrite rules
│
├── strategies/                 # Strategy definitions and backtesting
├── backtest/                   # Backtesting engine
├── risk/                       # Risk management modules
├── execution/                  # Order execution layer
├── agents/                     # AI agent layer
├── monitoring/                 # Monitoring and alerting
└── pyproject.toml              # Python dependencies (requires-python: >=3.11,<3.13)
```

---

## Backend API

### Startup

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### CORS

All origins allowed in development. Production locks to Vercel domain.

### Routers

| Prefix | File | Description |
|--------|------|-------------|
| `/api/market` | `market.py` | Market data, indices, FII/DII, movers |
| `/api/screener` | `screener.py` | Multi-strategy NSE screener |
| `/api/portfolio` | `portfolio.py` | Holdings, P&L, allocation |
| `/api/trades` | `trades.py` | Trade blotter |
| `/api/risk` | `risk.py` | Risk metrics |
| `/api/strategies` | `strategies.py` | Strategy analytics |
| `/api/chat` | `chat.py` | AI assistant |
| `/api/system` | `system.py` | Health, status |

### Caching Pattern

All expensive endpoints use an in-memory TTL cache:

```python
_cache: dict[str, tuple[Any, float]] = {}

def _cached(key: str, ttl: int = 300):
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            if key in _cache:
                value, ts = _cache[key]
                if time.time() - ts < ttl:
                    return value
            result = await fn(*args, **kwargs)
            _cache[key] = (result, time.time())
            return result
        return wrapper
    return decorator
```

---

## Frontend Dashboard

### Design System

Implements the complete Chakra UI v3 design token system (`globals.css`):

**Color Palette:**
| Token | Dark | Light |
|-------|------|-------|
| `--bg` | `#09090b` (gray.950) | `#fafafa` (gray.50) |
| `--surface` | `#111111` | `#ffffff` |
| `--surface-2` | `#18181b` (gray.900) | `#f4f4f5` (gray.100) |
| `--surface-3` | `#27272a` (gray.800) | `#e4e4e7` (gray.200) |
| `--border` | `#27272a` (gray.800) | `#e4e4e7` (gray.200) |
| `--text-1` | `#fafafa` | `#09090b` |
| `--text-2` | `#d4d4d8` (gray.300) | `#3f3f46` (gray.700) |
| `--text-3` | `#71717a` (gray.500) | `#71717a` |
| `--blue` | `#3b82f6` (blue.500) | `#2563eb` (blue.600) |
| `--green` | `#22c55e` (green.500) | `#16a34a` (green.600) |
| `--red` | `#ef4444` (red.500) | `#dc2626` (red.600) |
| `--amber` | `#f97316` (orange.500) | `#ea580c` (orange.600) |

**Typography:**
- Heading: Inter (variable weight)
- Body: Inter
- Mono: JetBrains Mono

**Radii (Chakra v3 exact):**
| Token | Value |
|-------|-------|
| `--r-xs` | 4px |
| `--r-sm` | 6px |
| `--r-md` | 8px |
| `--r-lg` | 12px |
| `--r-xl` | 16px |
| `--r-2xl` | 24px |
| `--r-pill` | 9999px |

**Spacing:** 4px base grid (space-1=4px, space-2=8px, space-3=12px, space-4=16px, space-6=24px)

### React Query Hooks

All data is fetched via React Query with typed generics:

```typescript
// FII/DII with full FAO fields
export const useFiiDii = () =>
  useQuery<FiiDiiRow[]>({ queryKey: ["market", "fii-dii"], staleTime: 5 * 60_000 });

export const useFiiDiiToday = () =>
  useQuery<FiiDiiRow>({ queryKey: ["market", "fii-dii-today"], staleTime: 60_000 });

export const useFiiDiiSectors = () =>
  useQuery<FiiDiiSector[]>({ queryKey: ["market", "fii-dii-sectors"], staleTime: 60 * 60_000 });

// Screener with strategy + universe
export const useScreener = (
  strategy: ScreenerStrategy,
  minConfidence: number,
  minPrice: number,
  maxPrice: number,
  symbol: string,
  universe: "nifty500" | "full" = "nifty500",
) => useQuery<ScreenerResponse>({ ... });
```

---

## Stock Screener

### Stock Universe

| Universe | Stocks | Source |
|----------|--------|--------|
| Nifty 500 (`nifty500`) | 503 | `ind_nifty500list.csv` |
| Full NSE (`full`) | 2,137 | NSE EQUITY_L.csv via sharewatch |

### Strategies

#### 1. VCP — Volatility Contraction Pattern
Inspired by Mark Minervini's SEPA methodology.

**Conditions checked:**
- 4-wave volatility contraction (each swing ≤ previous)
- Volume drying up in contraction (last vol < 60% of 20-day avg)
- Price above EMA10 > EMA20
- RSI > 50 (momentum positive)
- ATR % declining (tightening range)

**Implementation:** `_evaluate_stock(ticker, df, "vcp")` in `screener.py`

#### 2. IPO Base
Tight consolidation after a strong listing pop.

**Conditions checked:**
- Strong move in first 60 days (>30% from open)
- Price within 15% of recent high
- EMA10 above EMA20 (uptrend preserved)
- Volume drying up (avg of last 5 < 50% of 20-day avg)
- ADX > 20 (trending, not choppy)

#### 3. Rocket Base
Post-momentum consolidation. 80%+ move followed by ≤20% pullback.

**Conditions checked:**
- 80%+ rally from 52W low to recent high
- Current pullback ≤ 20% from peak
- Price holding above EMA20
- Volume declining in consolidation
- RSI still > 45 (no mean-reversion)

#### 4. Breakout (PKScreener-inspired)
Near 52-week high with volume confirmation.

**Conditions checked:**
- Price within 3% of 52W high
- Volume surge ≥ 1.8× 20-day average
- RSI between 50–75 (momentum zone, not overbought)
- EMA20 > EMA50 (trend aligned)

#### 5. RSI Reversal (PKScreener-inspired)
Oversold stocks recovering with volume.

**Conditions checked:**
- RSI dipped below 35 in last 5 days
- Current RSI > 35 (recovering)
- Volume surge ≥ 1.5× average (accumulation)
- Price > EMA20 (trend not broken)

#### 6. Golden Cross (PKScreener-inspired)
EMA crossover with SMA200 filter.

**Conditions checked:**
- EMA20 crossed above EMA50 in last 5 days
- Current EMA20 > EMA50 (cross confirmed)
- Price above SMA200 (long-term uptrend)
- Volume surge ≥ 1.3× average

### Confidence Scoring

```python
confidence = (matched_conditions / total_conditions) * 100
```

| Score | Badge |
|-------|-------|
| ≥ 70% | Strong (green) |
| 45–69% | Moderate (amber) |
| < 45% | Weak (gray) |

### Stop-Loss / Take-Profit

```python
sl = ltp * (1 - atr_pct * 1.5)        # 1.5× ATR below entry
tp1 = ltp * (1 + atr_pct * 2.5)       # 2.5× ATR (1:1.67 R:R)
tp2 = ltp * (1 + atr_pct * 4.0)       # 4× ATR (1:2.67 R:R)
```

### API Endpoints

```
GET  /api/screener/results?strategy=vcp&universe=nifty500&min_confidence=0&min_price=0&max_price=0&symbol=
POST /api/screener/scan?strategy=vcp&universe=nifty500
GET  /api/screener/status
```

### Cache

- Per strategy+universe combination (e.g. `vcp_nifty500`, `golden_cross_full`)
- 1-hour TTL
- Background scan triggered on cache miss; returns cached data immediately

---

## FII / DII Data Pipeline

### Data Source

Rich dataset from [MrChartist/fii-dii-data](https://github.com/MrChartist/fii-dii-data) copied to `api/fii_dii_data/`.

### Schema

Each row in `history.json`:

```json
{
  "date": "06-May-2026",
  "fii_buy": 14459.21,
  "fii_sell": 20294.11,
  "fii_net": -5834.9,
  "dii_buy": 22888.16,
  "dii_sell": 16051.29,
  "dii_net": 6836.87,
  "fii_idx_fut_net": -194595,
  "fii_stk_fut_net": 799040,
  "fii_idx_call_net": -382956,
  "fii_idx_put_net": 163867,
  "pcr": 0.53,
  "sentiment_score": 31.3,
  "sentiment": "Bearish",
  "_fao_summary": {
    "sentiment": "Bearish",
    "pcr": 0.53,
    "fii_fut_net": 604445,
    "fii_call_net": -382956,
    "fii_put_net": 163867
  }
}
```

### Endpoint Priority Chain

```
GET /api/market/fii-dii
  1. Read history.json (69 rows, guaranteed non-zero)
  2. Fallback: NSE API (fiidiiTradeReact) — skipped if returns zeros
  3. Final fallback: deterministic mock (Random seed=42)

GET /api/market/fii-dii/today
  1. Read latest.json (full FAO data)
  2. Fallback: last row of /fii-dii history

GET /api/market/fii-dii/sectors
  1. Read sectors.json (sector-wise FII ownership + alpha)
  2. Returns [] on error
```

### PCR Interpretation

| PCR | Signal |
|-----|--------|
| > 1.2 | Bullish (put heavy = hedging) |
| 0.8–1.2 | Neutral |
| < 0.8 | Bearish (call heavy = speculation) |

---

## Market Data Layer

### Indices (`GET /api/market/indices`)

Fetches via `nsepython` + yfinance fallback:
- NIFTY 50, BANKNIFTY, NIFTY IT, NIFTY MIDCAP 150, NIFTY SMALLCAP 250

### Top Movers (`GET /api/market/movers`)

NSE `gainersandlosers` API → top 5 gainers + top 5 losers by change%.

### Sectors (`GET /api/market/sectors`)

NSE sector indices → sorted by performance.

### Corporate Actions (`GET /api/market/corporate-actions`)

NSE corporate actions API → dividends, splits, bonus.

### Advances/Declines (`GET /api/market/advances-declines`)

NSE breadth data for Nifty 500.

---

## Strategy Engine

Located in `strategies/`. Each strategy implements:

```python
class BaseStrategy:
    def generate_signals(self, data: pd.DataFrame) -> pd.Series: ...
    def compute_position_size(self, signal: float, capital: float) -> float: ...
```

### Indicator Library (from PKScreener)

| Indicator | Parameters | Usage |
|-----------|-----------|-------|
| RSI | 14 periods | Momentum, reversal detection |
| MACD | 12, 26, 9 | Trend confirmation |
| EMA | 10, 20, 50 | Trend direction |
| SMA | 200 | Long-term trend filter |
| ATR | 14 | Volatility, stop-loss sizing |
| Volume Ratio | 20-day avg | Surge detection |
| ADX | 14 | Trend strength |

---

## Risk Management

### Position Sizing

Kelly Criterion with half-Kelly cap:
```python
kelly_f = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
position_pct = min(kelly_f * 0.5, MAX_POSITION_PCT)  # half-Kelly, capped at 5%
```

### Portfolio Limits

- Max single position: 5% of portfolio
- Max sector concentration: 25%
- Max drawdown threshold: 15% (triggers risk-off)
- VaR confidence: 95%, 1-day horizon

### Stop-Loss Framework

All screener entries use ATR-based stops:
```
SL = Entry × (1 - ATR% × 1.5)
TP1 = Entry × (1 + ATR% × 2.5)   # Risk:Reward = 1.67
TP2 = Entry × (1 + ATR% × 4.0)   # Risk:Reward = 2.67
```

---

## Deployment

### Frontend (Vercel)

```bash
cd dashboard/
vercel --prod --yes
```

**Environment variables:**
- `VITE_API_URL` — Cloudflare tunnel URL for the backend

### Backend (Local + Cloudflare Tunnel)

```bash
# Start backend
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Expose via Cloudflare tunnel (no account required)
cloudflared tunnel --url http://localhost:8000 --no-autoupdate

# Update Vercel env with new tunnel URL
vercel env rm VITE_API_URL production --yes
vercel env add VITE_API_URL production <<< "<new-tunnel-url>"
vercel --prod --yes
```

> **Note:** Cloudflare trycloudflare.com URLs are ephemeral. Each session generates a new URL. Run the above 3 commands whenever the tunnel restarts.

### Python Requirements

```toml
requires-python = ">=3.11,<3.13"
```

> Constrained to <3.13 due to `NorenRestApiPy` (Shoonya broker API) not supporting Python 3.13 yet.

---

## Data Sources

| Source | Data | Update Frequency |
|--------|------|-----------------|
| [fii-dii-data](https://github.com/MrChartist/fii-dii-data) | FII/DII cash + FAO + PCR + sentiment | Daily |
| NSE India API | Indices, movers, corporate actions | Real-time (15min delay) |
| yfinance | OHLCV history, quotes | Real-time (15min delay) |
| nsepython | NSE sector data, breadth | Real-time |
| [sharewatch](https://github.com/anjulgarg/sharewatch) | All 2,137 NSE EQUITY_L stocks | Static |
| [PKScreener](https://github.com/pkjmesra/PKScreener) | Indicator logic & strategies | Static |
| [project-neo](https://github.com/Negi27921/project-neo) | VCP / IPO Base / Rocket Base patterns | Static |

---

## Key Design Decisions

1. **No database**: All market data is fetched live and cached in-memory. Historical data comes from yfinance on demand. This keeps the architecture simple and avoids database ops cost on Vercel.

2. **Cloudflare tunnel for backend**: The FastAPI backend runs locally and is exposed via Cloudflare's free tunnel. This means zero cloud hosting cost for compute-heavy tasks (screener scans, yfinance downloads).

3. **Nifty 500 as default screener universe**: Full 2,137-stock scans take 15–25 minutes. Nifty 500 scans complete in 3–5 minutes. Both are supported via `?universe=nifty500|full`.

4. **Background scanning**: Screener responds immediately from cache. New scan is triggered in background thread. Frontend polls every 5 minutes.

5. **fii-dii-data file fallback**: NSE's FII/DII API returns zeros after market hours. The local `history.json` always has accurate data, making the endpoint reliable 24/7.

6. **Chakra UI design tokens in CSS**: Rather than using Chakra's React components, we implement the exact Chakra v3 token values as CSS custom properties. This gives us Chakra's precise design language with zero runtime overhead.

---

*Generated 2026-05-06 — India Quant Fund v1.0*
