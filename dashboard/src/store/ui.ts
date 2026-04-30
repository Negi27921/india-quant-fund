import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIStore {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  equityCurveDays: number;
  setEquityCurveDays: (days: number) => void;
  activeOrderFilter: string;
  setActiveOrderFilter: (filter: string) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () =>
        set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      equityCurveDays: 252,
      setEquityCurveDays: (days) => set({ equityCurveDays: days }),
      activeOrderFilter: "all",
      setActiveOrderFilter: (filter) => set({ activeOrderFilter: filter }),
    }),
    { name: "iqf-ui" }
  )
);
