// In dev: Vite proxies /api → localhost:8000
// In prod: set VITE_API_URL=https://your-backend.com in Vercel env vars
export const API_BASE = (import.meta.env.VITE_API_URL ?? "") + "/api";

const wsBase = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/^http/, "ws")
  : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
export const WS_URL = `${wsBase}/ws`;

export const CHART_COLORS = {
  primary: "#FA5D29",
  success: "#27AE60",
  danger: "#E74C3C",
  warning: "#F39C12",
  purple: "#F39C12",
  cyan: "#F39C12",
  grid: "#E5E7EB",
  text: "#9CA3AF",
};

export const SECTOR_COLORS: Record<string, string> = {
  "Information Technology": "#FA5D29",
  "Financial Services": "#27AE60",
  "Healthcare": "#F39C12",
  "Consumer Goods": "#F59E0B",
  "Energy": "#E74C3C",
  "Industrials": "#FA5D29",
  "Materials": "#F97316",
  "Real Estate": "#F39C12",
  "Utilities": "#27AE60",
  "Communication Services": "#14B8A6",
  "Consumer Staples": "#84CC16",
  "Other": "#6B7280",
};

export const STRATEGY_COLORS: Record<string, string> = {
  vcp:          "#27AE60",
  ipo_base:     "#F39C12",
  rocket_base:  "#FA5D29",
  breakout:     "#E74C3C",
  rsi_reversal: "#FFF083",
  golden_cross: "#27AE60",
  multibagger:  "#FA5D29",
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
