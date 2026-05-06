import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export interface FiiDiiRow {
  date: string;
  fii_buy: number; fii_sell: number; fii_net: number;
  dii_buy: number; dii_sell: number; dii_net: number;
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
  status: MarketStatus;
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

export const useScreener = (
  strategy: "vcp" | "ipo_base" | "rocket_base",
  minConfidence: number,
  minPrice: number,
  maxPrice: number,
  symbol: string,
) =>
  useQuery<ScreenerResponse>({
    queryKey: ["screener", strategy, minConfidence, minPrice, maxPrice, symbol],
    queryFn: () => {
      const params = new URLSearchParams({
        strategy,
        min_confidence: String(minConfidence),
        min_price: String(minPrice),
        max_price: String(maxPrice),
        symbol,
      });
      return api.get<ScreenerResponse>(`/screener/results?${params}`);
    },
    staleTime: 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

export const useTriggerScan = () => {
  const triggerScan = async (strategy: "vcp" | "ipo_base" | "rocket_base") => {
    await api.post(`/screener/scan?strategy=${strategy}`);
  };
  return triggerScan;
};
