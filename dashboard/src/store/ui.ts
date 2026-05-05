import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ChartTarget {
  symbol: string;
  name?: string;
}

interface UIStore {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  equityCurveDays: number;
  setEquityCurveDays: (days: number) => void;
  activeOrderFilter: string;
  setActiveOrderFilter: (filter: string) => void;
  paperMode: boolean;
  togglePaperMode: () => void;
  // Global chart drawer
  chartTarget: ChartTarget | null;
  openChart: (symbol: string, name?: string) => void;
  closeChart: () => void;
  // Global search
  searchOpen: boolean;
  openSearch: () => void;
  closeSearch: () => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      equityCurveDays: 252,
      setEquityCurveDays: (days) => set({ equityCurveDays: days }),
      activeOrderFilter: "all",
      setActiveOrderFilter: (filter) => set({ activeOrderFilter: filter }),
      paperMode: false,
      togglePaperMode: () => set((s) => ({ paperMode: !s.paperMode })),
      // Chart drawer — not persisted (transient)
      chartTarget: null,
      openChart: (symbol, name) => set({ chartTarget: { symbol, name } }),
      closeChart: () => set({ chartTarget: null }),
      // Search — not persisted (transient)
      searchOpen: false,
      openSearch: () => set({ searchOpen: true }),
      closeSearch: () => set({ searchOpen: false }),
    }),
    {
      name: "op-ui",
      // Only persist these fields
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        equityCurveDays: s.equityCurveDays,
        activeOrderFilter: s.activeOrderFilter,
        paperMode: s.paperMode,
      }),
    }
  )
);
