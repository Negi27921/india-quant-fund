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
  vcp:          "#00ff87",
  ipo_base:     "#00c8ff",
  rocket_base:  "#f97316",
  breakout:     "#a855f7",
  rsi_reversal: "#fbbf24",
  golden_cross: "#06d6a0",
  multibagger:  "#ff4757",
};

export const STRATEGY_LABELS: Record<string, string> = {
  vcp:          "VCP",
  ipo_base:     "IPO Base",
  rocket_base:  "Rocket Base",
  breakout:     "Breakout",
  rsi_reversal: "RSI Reversal",
  golden_cross: "Golden Cross",
  multibagger:  "Multibagger",
};

export const REFETCH_INTERVALS = {
  realtime: 5_000,
  fast: 15_000,
  normal: 30_000,
  slow: 60_000,
  verySllow: 5 * 60_000,
};
