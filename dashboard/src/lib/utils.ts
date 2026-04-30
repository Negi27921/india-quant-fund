import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, parseISO, isValid } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number, compact = false): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";

  if (compact) {
    if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)}Cr`;
    if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)}L`;
    if (abs >= 1e3) return `${sign}₹${(abs / 1e3).toFixed(1)}K`;
    return `${sign}₹${abs.toFixed(0)}`;
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPct(value: number, decimals = 2, showSign = true): string {
  const sign = value > 0 && showSign ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}

export function formatNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatDate(dateStr: string, fmt = "dd MMM yyyy"): string {
  try {
    const d = parseISO(dateStr);
    return isValid(d) ? format(d, fmt) : dateStr;
  } catch {
    return dateStr;
  }
}

export function formatDateTime(dateStr: string): string {
  return formatDate(dateStr, "dd MMM yyyy HH:mm");
}

export function pctColor(value: number): string {
  if (value > 0) return "text-success";
  if (value < 0) return "text-danger";
  return "text-text-secondary";
}

export function pctBg(value: number): string {
  if (value > 0) return "bg-success-dim text-success";
  if (value < 0) return "bg-danger-dim text-danger";
  return "bg-bg-overlay text-text-secondary";
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function interpolateColor(
  value: number,
  min: number,
  max: number
): string {
  const t = clamp((value - min) / (max - min), 0, 1);
  if (t < 0.5) {
    const r = Math.round(239 * (1 - t * 2) + 245 * t * 2);
    return `rgb(${r}, ${Math.round(68 + 90 * t * 2)}, ${Math.round(68)})`;
  }
  const t2 = (t - 0.5) * 2;
  return `rgb(${Math.round(16 * t2)}, ${Math.round(185 * t2 + 90 * (1 - t2))}, ${Math.round(129 * t2)})`;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
