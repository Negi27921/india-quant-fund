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
