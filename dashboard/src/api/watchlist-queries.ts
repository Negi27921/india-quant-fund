import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Watchlist {
  id: string;
  name: string;
  description: string;
  type: "manual" | "auto_results" | "quarterly_results" | "universe";
  color: string;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  id: string;
  watchlist_id: string;
  symbol: string;
  ticker: string | null;
  company: string;
  sector: string;
  industry: string;
  added_at: string;
  added_reason: string;
  result_date: string | null;
  result_high: number | null;
  result_volume_avg: number | null;
  result_rating: string | null;
  breakout_alerted: boolean;
  breakout_date: string | null;
  notes: string;
}

export interface AnalyseResponse {
  symbol: string;
  response: string;
  provider: string;
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const wlKeys = {
  lists: ["watchlists"] as const,
  items: (id: string) => ["watchlists", id, "items"] as const,
};

// ── Queries ───────────────────────────────────────────────────────────────────

export function useWatchlists() {
  return useQuery<Watchlist[]>({
    queryKey: wlKeys.lists,
    queryFn: () => api.get<Watchlist[]>("/watchlists"),
    staleTime: 30_000,
  });
}

export function useWatchlistItems(watchlistId: string | null) {
  return useQuery<WatchlistItem[]>({
    queryKey: wlKeys.items(watchlistId ?? ""),
    queryFn: () => api.get<WatchlistItem[]>(`/watchlists/${watchlistId}/items`),
    enabled: !!watchlistId,
    staleTime: 30_000,
  });
}

// ── Mutations ─────────────────────────────────────────────────────────────────

export function useCreateWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string; color?: string }) =>
      api.post<Watchlist>("/watchlists", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: wlKeys.lists }),
  });
}

export function useDeleteWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ ok: boolean }>(`/watchlists/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: wlKeys.lists }),
  });
}

export function useAddWatchlistItem(watchlistId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { symbol: string; ticker?: string; company?: string; sector?: string; industry?: string; notes?: string }) =>
      api.post<WatchlistItem>(`/watchlists/${watchlistId}/items`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: wlKeys.items(watchlistId) }),
  });
}

export function useRemoveWatchlistItem(watchlistId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) =>
      api.delete<{ ok: boolean }>(`/watchlists/${watchlistId}/items/${symbol}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: wlKeys.items(watchlistId) }),
  });
}

export function useAnalyseStock() {
  return useMutation({
    mutationFn: (body: { symbol: string; question: string; history?: { role: string; content: string }[] }) =>
      api.post<AnalyseResponse>("/watchlists/analyse", body),
  });
}

export interface UniverseStock {
  symbol: string;
  company: string;
  sector: string;
  industry: string;
}

export function useUniverseSearch(q: string) {
  return useQuery<UniverseStock[]>({
    queryKey: ["universe", "search", q],
    queryFn: () => api.get<UniverseStock[]>(`/watchlists/universe/search?q=${encodeURIComponent(q)}&limit=50`),
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });
}
