import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  PortfolioSummary,
  Position,
  SectorExposure,
  EquityPoint,
  Order,
  TradeStats,
  RiskMetrics,
  RiskLimits,
  DrawdownPoint,
  StrategyPerformance,
  Signal,
  StrategyAllocation,
  SystemHealth,
  KillSwitchStatus,
  AuditEntry,
} from "./types";
import { REFETCH_INTERVALS } from "@/lib/constants";

// Portfolio
export const usePortfolioSummary = () =>
  useQuery({
    queryKey: ["portfolio", "summary"],
    queryFn: () => api.get<PortfolioSummary>("/portfolio/summary"),
    refetchInterval: REFETCH_INTERVALS.fast,
  });

export const usePositions = () =>
  useQuery({
    queryKey: ["portfolio", "positions"],
    queryFn: () => api.get<Position[]>("/portfolio/positions"),
    refetchInterval: REFETCH_INTERVALS.normal,
  });

export const useEquityCurve = (days = 252) =>
  useQuery({
    queryKey: ["portfolio", "equity-curve", days],
    queryFn: () => api.get<EquityPoint[]>(`/portfolio/equity-curve?days=${days}`),
    refetchInterval: REFETCH_INTERVALS.slow,
  });

export const useSectorExposure = () =>
  useQuery({
    queryKey: ["portfolio", "sector-exposure"],
    queryFn: () => api.get<SectorExposure[]>("/portfolio/sector-exposure"),
    refetchInterval: REFETCH_INTERVALS.slow,
  });

// Trades
export const useOrders = (status = "all", limit = 50) =>
  useQuery({
    queryKey: ["trades", "orders", status, limit],
    queryFn: () => api.get<Order[]>(`/trades/orders?status=${status}&limit=${limit}`),
    refetchInterval: REFETCH_INTERVALS.fast,
  });

export const useFills = (days = 30) =>
  useQuery({
    queryKey: ["trades", "fills", days],
    queryFn: () => api.get<Order[]>(`/trades/fills?days=${days}`),
    refetchInterval: REFETCH_INTERVALS.normal,
  });

export const useTradeStats = (days = 30) =>
  useQuery({
    queryKey: ["trades", "stats", days],
    queryFn: () => api.get<TradeStats>(`/trades/stats?days=${days}`),
    refetchInterval: REFETCH_INTERVALS.slow,
  });

// Risk
export const useRiskMetrics = () =>
  useQuery({
    queryKey: ["risk", "metrics"],
    queryFn: () => api.get<RiskMetrics>("/risk/metrics"),
    refetchInterval: REFETCH_INTERVALS.fast,
  });

export const useRiskLimits = () =>
  useQuery({
    queryKey: ["risk", "limits"],
    queryFn: () => api.get<RiskLimits>("/risk/limits"),
    staleTime: 5 * 60_000,
  });

export const useDrawdownHistory = (days = 90) =>
  useQuery({
    queryKey: ["risk", "drawdown-history", days],
    queryFn: () => api.get<DrawdownPoint[]>(`/risk/drawdown-history?days=${days}`),
    refetchInterval: REFETCH_INTERVALS.slow,
  });

// Strategies
export const useStrategyPerformance = () =>
  useQuery({
    queryKey: ["strategies", "performance"],
    queryFn: () => api.get<StrategyPerformance[]>("/strategies/performance"),
    refetchInterval: REFETCH_INTERVALS.verySllow,
  });

export const useSignals = (days = 5) =>
  useQuery({
    queryKey: ["strategies", "signals", days],
    queryFn: () => api.get<Signal[]>(`/strategies/signals?days=${days}`),
    refetchInterval: REFETCH_INTERVALS.normal,
  });

export const useStrategyAllocation = () =>
  useQuery({
    queryKey: ["strategies", "allocation"],
    queryFn: () => api.get<StrategyAllocation[]>("/strategies/allocation"),
    refetchInterval: REFETCH_INTERVALS.slow,
  });

// System
export const useSystemHealth = () =>
  useQuery({
    queryKey: ["system", "health"],
    queryFn: () => api.get<SystemHealth>("/system/health"),
    refetchInterval: REFETCH_INTERVALS.fast,
  });

export const useKillSwitchStatus = () =>
  useQuery({
    queryKey: ["system", "kill-switch"],
    queryFn: () => api.get<KillSwitchStatus>("/system/kill-switch/status"),
    refetchInterval: REFETCH_INTERVALS.fast,
  });

export const useAuditLog = (limit = 50) =>
  useQuery({
    queryKey: ["system", "audit-log", limit],
    queryFn: () => api.get<AuditEntry[]>(`/system/audit-log?limit=${limit}`),
    refetchInterval: REFETCH_INTERVALS.normal,
  });

export const useResetKillSwitch = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) =>
      api.post<{ status: string; reason: string }>(
        `/system/kill-switch/reset?reason=${encodeURIComponent(reason)}`
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["system", "kill-switch"] });
      qc.invalidateQueries({ queryKey: ["risk", "metrics"] });
    },
  });
};
