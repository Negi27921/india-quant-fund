// In dev: Vite proxies /api → localhost:8000
// In prod: set VITE_API_URL=https://your-backend.com in Vercel env vars
export const API_BASE = (import.meta.env.VITE_API_URL ?? "") + "/api";

const wsBase = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/^http/, "ws")
  : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
export const WS_URL = `${wsBase}/ws`;

export const CHART_COLORS = {
  primary: "#3B82F6",
  success: "#10B981",
  danger: "#EF4444",
  warning: "#F59E0B",
  purple: "#8B5CF6",
  cyan: "#06B6D4",
  grid: "#1E2028",
  text: "#4B5066",
};

export const SECTOR_COLORS: Record<string, string> = {
  "Information Technology": "#3B82F6",
  "Financial Services": "#10B981",
  "Healthcare": "#8B5CF6",
  "Consumer Goods": "#F59E0B",
  "Energy": "#EF4444",
  "Industrials": "#06B6D4",
  "Materials": "#F97316",
  "Real Estate": "#EC4899",
  "Utilities": "#6366F1",
  "Communication Services": "#14B8A6",
  "Consumer Staples": "#84CC16",
  "Other": "#6B7280",
};

export const STRATEGY_COLORS: Record<string, string> = {
  momentum_st: "#3B82F6",
  momentum_mt: "#8B5CF6",
  mean_reversion: "#10B981",
  factor: "#F59E0B",
  event: "#EF4444",
};

export const STRATEGY_LABELS: Record<string, string> = {
  momentum_st: "ST Momentum",
  momentum_mt: "MT Momentum",
  mean_reversion: "Mean Rev",
  factor: "Factor",
  event: "Event",
};

export const REFETCH_INTERVALS = {
  realtime: 5_000,
  fast: 15_000,
  normal: 30_000,
  slow: 60_000,
  verySllow: 5 * 60_000,
};
