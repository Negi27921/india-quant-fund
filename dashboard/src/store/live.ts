import { create } from "zustand";
import type { LiveData } from "@/api/types";
import { API_BASE } from "@/lib/constants";

interface LiveStore {
  data: LiveData | null;
  connected: boolean;
  lastUpdate: Date | null;
  connect: () => () => void;
}

// Vercel serverless doesn't support WebSockets — use HTTP polling instead
export const useLiveStore = create<LiveStore>((set) => ({
  data: null,
  connected: false,
  lastUpdate: null,

  connect: () => {
    let timer: ReturnType<typeof setInterval>;
    let unmounted = false;

    const fetchLive = async () => {
      try {
        const res = await fetch(`${API_BASE}/portfolio/summary`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const summary = await res.json();
        const live: LiveData = {
          portfolio_value:     summary.portfolio_value ?? 0,
          day_pnl:             summary.day_pnl ?? 0,
          day_pnl_pct:         summary.day_pnl_pct ?? 0,
          drawdown_pct:        summary.drawdown_pct ?? 0,
          n_positions:         summary.n_positions ?? 0,
          kill_switch_active:  summary.kill_switch_active ?? false,
          timestamp:           new Date().toISOString(),
        };
        if (!unmounted) set({ data: live, connected: true, lastUpdate: new Date() });
      } catch {
        if (!unmounted) set({ connected: false });
      }
    };

    fetchLive();
    timer = setInterval(fetchLive, 15_000);

    return () => {
      unmounted = true;
      clearInterval(timer);
    };
  },
}));
