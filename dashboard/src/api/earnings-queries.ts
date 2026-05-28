import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────────
export interface EarningsResult {
  id: string;
  ticker: string;
  company: string;
  sector: string;
  quarter: string;       // "Q4FY26"
  period_end: string | null;

  sales_cr: number | null;
  sales_prev_q_cr: number | null;
  sales_prev_y_cr: number | null;
  sales_qoq_pct: number | null;
  sales_yoy_pct: number | null;

  other_income_cr: number | null;

  op_cr: number | null;
  op_prev_q_cr: number | null;
  op_prev_y_cr: number | null;
  op_qoq_pct: number | null;
  op_yoy_pct: number | null;

  opm_pct: number | null;
  opm_prev_q_pct: number | null;
  opm_prev_y_pct: number | null;
  opm_qoq_bps: number | null;
  opm_yoy_bps: number | null;

  pat_cr: number | null;
  pat_prev_q_cr: number | null;
  pat_prev_y_cr: number | null;
  pat_qoq_pct: number | null;
  pat_yoy_pct: number | null;

  eps: number | null;
  eps_prev_q: number | null;
  eps_prev_y: number | null;
  eps_qoq_pct: number | null;
  eps_yoy_pct: number | null;

  cmp: number | null;
  pe_ratio: number | null;
  market_cap_cr: number | null;

  pulse_rating: "Great" | "Good" | "Mixed" | "Poor" | null;
  confidence_score: number | null;
  source: string | null;
  filed_at: string | null;
  created_at: string | null;
}

export interface EarningsStats {
  total: number;
  by_rating: Record<string, number>;
  by_quarter: Record<string, number>;
  latest_quarter: string | null;
  latest_filed: string | null;
}

// ── Hooks ─────────────────────────────────────────────────────────────────────
export function useLatestEarnings(params: {
  limit?: number;
  quarter?: string;
  rating?: string;
  sector?: string;
  search?: string;
} = {}) {
  const qs = new URLSearchParams();
  if (params.limit)   qs.set("limit",   String(params.limit));
  if (params.quarter) qs.set("quarter", params.quarter);
  if (params.rating)  qs.set("rating",  params.rating);
  if (params.sector)  qs.set("sector",  params.sector);
  if (params.search)  qs.set("search",  params.search);

  const query = qs.toString() ? `?${qs}` : "";

  return useQuery<EarningsResult[]>({
    queryKey: ["earnings", "latest", params],
    queryFn: () => api.get<EarningsResult[]>(`/earnings/latest${query}`),
    staleTime: 2 * 60_000,
    refetchInterval: 5 * 60_000,
  });
}

export function useTickerEarnings(ticker: string, limit = 8) {
  return useQuery<EarningsResult[]>({
    queryKey: ["earnings", "ticker", ticker, limit],
    queryFn: () => api.get<EarningsResult[]>(`/earnings/ticker/${ticker}?limit=${limit}`),
    staleTime: 5 * 60_000,
    enabled: !!ticker,
  });
}

export function useEarningsStats() {
  return useQuery<EarningsStats>({
    queryKey: ["earnings", "stats"],
    queryFn: () => api.get<EarningsStats>("/earnings/stats"),
    staleTime: 10 * 60_000,
  });
}

export function useEarningsQuarters() {
  return useQuery<string[]>({
    queryKey: ["earnings", "quarters"],
    queryFn: () => api.get<string[]>("/earnings/quarters"),
    staleTime: 10 * 60_000,
  });
}
