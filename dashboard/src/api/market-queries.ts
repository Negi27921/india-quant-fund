import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export interface FiiDiiRow {
  date: string;
  fii_buy: number; fii_sell: number; fii_net: number;
  dii_buy: number; dii_sell: number; dii_net: number;
  fii_idx_fut_net?: number;
  fii_stk_fut_net?: number;
  fii_idx_call_net?: number;
  fii_idx_put_net?: number;
  pcr?: number;
  sentiment_score?: number;
  sentiment?: string;
  updated_at?: string;
}
export interface FiiDiiSector {
  name: string;
  aumPct: number;
  fortnightCr: number;
  oneYearCr: number;
  fiiOwn: number;
  alpha: number;
}
export interface Filing {
  id: string;
  company: string;
  scrip_code: string;
  category: string;
  headline: string;
  exchange: string;
  dt: string;
  has_pdf: boolean;
  pdf_url?: string;
}
export interface CorporateAction {
  symbol: string; company: string; action: string;
  ex_date: string; record_date: string; details: string;
}
export interface AdvancesDeclines {
  advances: number; declines: number; unchanged: number; total: number; ratio: number;
}
export interface ResultsMeeting {
  symbol: string; company: string; meeting_date: string; purpose: string; description: string;
}

export interface MarketStatus {
  is_open: boolean;
  session: "OPEN" | "PRE-OPEN" | "CLOSED" | "WEEKEND";
  ist_time: string;
  ist_date: string;
}

export interface IndexData {
  label: string;
  symbol: string;
  price: number;
  prev_close: number;
  change: number;
  change_pct: number;
  day_high: number;
  day_low: number;
}

export interface IndicesData {
  nifty50: IndexData;
  banknifty: IndexData;
  sensex: IndexData;
  niftymid50: IndexData;
  niftyit: IndexData;
  giftnifty?: IndexData;
  brentcrude?: IndexData;
  dowjones?: IndexData;
  status: MarketStatus;
}

export interface GlobalIndexData {
  symbol: string;
  label: string;
  price: number;
  change: number;
  change_pct: number;
  currency?: string;
  exchange?: string;
}

export interface StockQuote {
  ticker: string;
  price: number;
  prev_close: number;
  change: number;
  change_pct: number;
  day_high: number;
  day_low: number;
  volume: number;
}

export interface Mover {
  ticker: string;
  price: number;
  change: number;
  change_pct: number;
}

export interface MarketMovers {
  gainers: Mover[];
  losers: Mover[];
  breadth: { advances: number; declines: number; unchanged: number; total: number };
}

export interface SectorData {
  sector: string;
  symbol: string;
  price: number;
  change: number;
  change_pct: number;
}

export interface OHLCBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const REFETCH = {
  status:  5_000,
  indices: 15_000,
  movers:  30_000,
  sectors: 30_000,
  history: 5 * 60_000,
};

export const useMarketStatus = () =>
  useQuery({
    queryKey: ["market", "status"],
    queryFn: () => api.get<MarketStatus>("/market/status"),
    refetchInterval: REFETCH.status,
    staleTime: 3_000,
  });

export const useMarketIndices = () =>
  useQuery({
    queryKey: ["market", "indices"],
    queryFn: () => api.get<IndicesData>("/market/indices"),
    refetchInterval: REFETCH.indices,
    staleTime: 10_000,
  });

export const useGlobalIndices = () =>
  useQuery({
    queryKey: ["market", "global-indices"],
    queryFn: () => api.get<GlobalIndexData[]>("/market/global-indices").catch(() => [] as GlobalIndexData[]),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

export const useMarketMovers = (limit = 8) =>
  useQuery({
    queryKey: ["market", "movers", limit],
    queryFn: () => api.get<MarketMovers>(`/market/movers?limit=${limit}`),
    refetchInterval: REFETCH.movers,
    staleTime: 25_000,
  });

export const useMarketSectors = () =>
  useQuery({
    queryKey: ["market", "sectors"],
    queryFn: () => api.get<SectorData[]>("/market/sectors"),
    refetchInterval: REFETCH.sectors,
    staleTime: 25_000,
  });

export const useIndexHistory = (
  ticker: string,
  period = "1d",
  interval = "5m"
) =>
  useQuery({
    queryKey: ["market", "history", ticker, period, interval],
    queryFn: () =>
      api.get<OHLCBar[]>(
        `/market/history/${encodeURIComponent(ticker)}?period=${period}&interval=${interval}`
      ),
    refetchInterval: REFETCH.history,
    staleTime: 4 * 60_000,
    enabled: !!ticker,
  });

export const usePriceHistory = (ticker: string, enabled = true) =>
  useQuery({
    queryKey: ["market", "price-history", ticker],
    queryFn: () =>
      api.get<OHLCBar[]>(
        `/market/history/${encodeURIComponent(ticker)}?period=1mo&interval=1d`
      ),
    staleTime: 10 * 60_000,
    enabled: enabled && !!ticker,
  });

export const useStockQuote = (tickers: string) =>
  useQuery({
    queryKey: ["market", "quote", tickers],
    queryFn: () =>
      api.get<StockQuote[]>(`/market/quote?tickers=${encodeURIComponent(tickers)}`),
    enabled: !!tickers,
    staleTime: 10_000,
  });

export const useFiiDii = () =>
  useQuery({ queryKey: ["market", "fii-dii"], queryFn: () => api.get<FiiDiiRow[]>("/market/fii-dii"), staleTime: 5 * 60 * 1000 });

export const useFiiDiiToday = () =>
  useQuery({ queryKey: ["market", "fii-dii-today"], queryFn: () => api.get<FiiDiiRow>("/market/fii-dii/today"), staleTime: 60 * 1000 });

export const useFiiDiiSectors = () =>
  useQuery({ queryKey: ["market", "fii-dii-sectors"], queryFn: () => api.get<FiiDiiSector[]>("/market/fii-dii/sectors"), staleTime: 60 * 60 * 1000 });

export const useFilings = (limit = 15) =>
  useQuery({ queryKey: ["market", "filings", limit], queryFn: () => api.get<Filing[]>(`/market/filings?limit=${limit}`), staleTime: 2 * 60 * 1000, refetchInterval: 2 * 60 * 1000 });

export const useCorporateActions = () =>
  useQuery({ queryKey: ["market", "corporate-actions"], queryFn: () => api.get<CorporateAction[]>("/market/corporate-actions"), staleTime: 10 * 60 * 1000 });

export const useAdvancesDeclines = () =>
  useQuery({ queryKey: ["market", "advances-declines"], queryFn: () => api.get<AdvancesDeclines>("/market/advances-declines"), staleTime: 60 * 1000, refetchInterval: 60 * 1000 });

export const useResultsCalendar = () =>
  useQuery({ queryKey: ["market", "results-calendar"], queryFn: () => api.get<ResultsMeeting[]>("/market/results-calendar"), staleTime: 30 * 60 * 1000 });

// ── Screener ──────────────────────────────────────────────────────────────────
export interface ScreenerResult {
  symbol: string;
  ticker: string;
  ltp: number;
  change_pct: number;
  rsi: number;
  ema_10: number;
  ema_20: number;
  confidence: number;
  matched_conditions: string[];
  failed_conditions: string[];
  sl: number;
  sl_pct: number;
  tp1: number;
  tp2: number;
}

export interface ScreenerResponse {
  results: ScreenerResult[];
  total: number;
  strategy: string;
  is_scanning: boolean;
  last_scan: string | null;
  universe_size: number;
}

type ScreenerStrategy = "vcp" | "ipo_base" | "rocket_base" | "breakout" | "rsi_reversal" | "golden_cross" | "multibagger" | "custom";

export const useScreener = (
  strategy: ScreenerStrategy,
  minConfidence: number,
  minPrice: number,
  maxPrice: number,
  symbol: string,
  universe: "nifty500" | "full" = "nifty500",
) =>
  useQuery<ScreenerResponse>({
    queryKey: ["screener", strategy, minConfidence, minPrice, maxPrice, symbol, universe],
    queryFn: () => {
      const params = new URLSearchParams({
        strategy,
        min_confidence: String(minConfidence),
        min_price: String(minPrice),
        max_price: String(maxPrice),
        symbol,
        universe,
      });
      return api.get<ScreenerResponse>(`/screener/results?${params}`);
    },
    staleTime: 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

export const useTriggerScan = () => {
  const triggerScan = async (strategy: ScreenerStrategy, universe: "nifty500" | "full" = "nifty500") => {
    await api.post(`/screener/scan?strategy=${strategy}&universe=${universe}`);
  };
  return triggerScan;
};

// ── Quarterly Results ─────────────────────────────────────────────────────────
export type Rating = "Excellent" | "Great" | "Good" | "Ok" | "Weak";

export interface MetricValues {
  qoq: number | null;
  yoy: number | null;
  q1: number;
  q2: number;
  q3: number;
}

export interface ResultMetrics {
  sales: MetricValues;
  other_income: MetricValues;
  op: MetricValues;
  opm: MetricValues;
  pat: MetricValues;
  eps: MetricValues;
}

export interface QuarterlyResult {
  id: string;
  symbol: string;
  ticker?: string;
  company: string;
  exchange: string;
  sector: string;
  industry: string;
  quarter: string;
  report_date: string;
  report_time: string;
  rating: Rating;
  rating_note?: string;
  insight: string;
  metrics: ResultMetrics;
  revenue_trend: number[];
  pat_trend: number[];
  eps_trend: number[];
  quarter_labels: string[];
  cmp: number | null;
  market_cap: number;
  pe: number | null;
  currency_unit?: string;
  pdf_url?: string;
}

export const useQuarterlyResults = () =>
  useQuery<QuarterlyResult[]>({
    queryKey: ["market", "quarterly-results"],
    queryFn: () =>
      api.get<QuarterlyResult[]>("/market/quarterly-results").catch(() => [] as QuarterlyResult[]),
    staleTime: 5 * 60_000,
    refetchInterval: 10 * 60_000,
  });
