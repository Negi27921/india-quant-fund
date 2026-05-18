// In dev: Vite proxies /api → localhost:8000
// In prod: set VITE_API_URL=https://your-backend.com in Vercel env vars
export const API_BASE = (import.meta.env.VITE_API_URL ?? "") + "/api";

const wsBase = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/^http/, "ws")
  : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
export const WS_URL = `${wsBase}/ws`;

export const CHART_COLORS = {
  primary: "var(--accent)",
  success: "#27AE60",
  danger:  "#E74C3C",
  warning: "#F59E0B",
  purple:  "#8B5CF6",
  cyan:    "#06B6D4",
  grid:    "rgba(33,34,38,0.08)",
  text:    "#9E9EA6",
};

export const SECTOR_COLORS: Record<string, string> = {
  "Information Technology": "var(--accent)",
  "Financial Services":     "#27AE60",
  "Healthcare":             "#F59E0B",
  "Consumer Goods":         "#8B5CF6",
  "Energy":                 "#E74C3C",
  "Industrials":            "#06B6D4",
  "Materials":              "#F97316",
  "Real Estate":            "#10B981",
  "Utilities":              "#6366F1",
  "Communication Services": "#14B8A6",
  "Consumer Staples":       "#84CC16",
  "Other":                  "#6B7280",
};

export const STRATEGY_COLORS: Record<string, string> = {
  vcp:          "#27AE60",
  ipo_base:     "#F59E0B",
  rocket_base:  "var(--accent)",
  breakout:     "#E74C3C",
  rsi_reversal: "#8B5CF6",
  golden_cross: "#06B6D4",
  multibagger:  "#F97316",
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
  realtime:  5_000,
  fast:     15_000,
  normal:   30_000,
  slow:     60_000,
  verySllow: 5 * 60_000,
};
