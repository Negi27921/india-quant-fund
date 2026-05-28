import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface DayPnL {
  date: string;
  pnl: number;
  pnl_pct: number;
  portfolio_value: number;
}

export interface PnLStats {
  total_pnl: number;
  total_pnl_pct: number;
  win_days: number;
  loss_days: number;
  best_day: number;
  worst_day: number;
  avg_win: number;
  avg_loss: number;
  streak: number;
  monthly: { month: string; pnl: number; pnl_pct: number }[];
}

export interface PaperPosition {
  ticker: string;
  name: string;
  quantity: number;
  avg_buy_price: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_pct: number;
  weight: number;
  sector: string;
  strategy: string;
  buy_date: string;
  days_held: number;
  notes: string;
}

export interface AddPositionPayload {
  ticker: string;
  quantity: number;
  avg_buy_price: number;
  buy_date: string;
  name?: string;
  sector?: string;
  notes?: string;
}

export const usePnLCalendar = (year: number, month?: number) =>
  useQuery({
    queryKey: ["pnl", "calendar", year, month],
    queryFn: () => {
      const params = new URLSearchParams({ year: String(year) });
      if (month) params.set("month", String(month));
      return api.get<DayPnL[]>(`/portfolio/pnl-calendar?${params}`);
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

export const usePnLStats = () =>
  useQuery({
    queryKey: ["pnl", "stats"],
    queryFn: () => api.get<PnLStats>("/portfolio/pnl-stats"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

export const usePaperPositions = () =>
  useQuery({
    queryKey: ["pnl", "paper-positions"],
    queryFn: () => api.get<PaperPosition[]>("/portfolio/paper-positions"),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

export const useAddPaperPosition = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AddPositionPayload) =>
      api.post<{ status: string; ticker: string }>("/portfolio/paper-positions", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pnl", "paper-positions"] });
      qc.invalidateQueries({ queryKey: ["portfolio", "positions"] });
    },
  });
};

export const useDeletePaperPosition = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) =>
      api.delete<{ status: string }>(`/portfolio/paper-positions/${encodeURIComponent(ticker)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pnl", "paper-positions"] });
      qc.invalidateQueries({ queryKey: ["portfolio", "positions"] });
    },
  });
};

export const useLivePositions = () =>
  useQuery({
    queryKey: ["portfolio", "live-positions"],
    queryFn: () => api.get<PaperPosition[]>("/portfolio/live-positions"),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });

export const useAddLivePosition = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: AddPositionPayload) => api.post("/portfolio/live-positions", p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio", "live-positions"] }),
  });
};

export const useExitPosition = (mode: "paper" | "live") => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ticker, quantity }: { ticker: string; quantity?: number }) =>
      api.put(`/portfolio/${mode}-positions/${encodeURIComponent(ticker)}/exit`, { quantity }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio", mode === "paper" ? "paper-positions" : "live-positions"] });
    },
  });
};

export const useDeleteLivePosition = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticker: string) => api.delete(`/portfolio/live-positions/${encodeURIComponent(ticker)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio", "live-positions"] }),
  });
};

export const useCheckPaperTradeExits = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ exits: unknown[]; checked: number; closed: number }>("/portfolio/paper-trades/check-exits"),
    onSuccess: (data) => {
      if (data.closed > 0) {
        qc.invalidateQueries({ queryKey: ["portfolio", "paper-trades"] });
        qc.invalidateQueries({ queryKey: ["portfolio", "strategy-pnl"] });
      }
    },
  });
};

export interface PaperTrade {
  id?: number;
  strategy: string;
  ticker: string;
  entry_date: string;
  entry_price: number;
  target_price: number;
  sl_price: number;
  shares: number;
  confidence: number;
  hold_days: number | null;
  exit_date: string | null;
  exit_price: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  status: string;
  notes: string;
}

export interface StrategyPnl {
  strategy: string;
  total_trades: number;
  closed_trades: number;
  open_trades: number;
  wins: number;
  losses: number;
  total_pnl: number;
  avg_pnl_pct: number;
  win_rate: number;
}

export const usePaperTrades = (status = "all") =>
  useQuery({
    queryKey: ["portfolio", "paper-trades", status],
    queryFn: () => api.get<PaperTrade[]>(`/portfolio/paper-trades?status=${status}&limit=200`),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

export const useStrategyPnl = () =>
  useQuery({
    queryKey: ["portfolio", "strategy-pnl"],
    queryFn: () => api.get<StrategyPnl[]>("/portfolio/strategy-pnl"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

// ── Journal = Live Portfolio hooks ─────────────────────────────────────────────

export interface JournalSummary {
  nav: number;
  total_invested: number;
  realized_pnl: number;
  unrealized_pnl: number;
  day_pnl: number;
  day_pnl_pct: number;
  drawdown: number;
  open_positions: number;
  total_trades: number;
}

export const useJournalSummary = () =>
  useQuery({
    queryKey: ["journal", "summary"],
    queryFn: () => api.get<JournalSummary>("/journal/summary"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

export const useJournalPnLCalendar = (year?: number, month?: number) =>
  useQuery({
    queryKey: ["journal", "pnl-calendar", year, month],
    queryFn: () => {
      const params = new URLSearchParams();
      if (year) params.set("year", String(year));
      if (month) params.set("month", String(month));
      return api.get<DayPnL[]>(`/journal/pnl-calendar?${params}`);
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

export const useJournalPositions = () =>
  useQuery({
    queryKey: ["journal", "positions"],
    queryFn: () => api.get<PaperPosition[]>("/journal/positions"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
