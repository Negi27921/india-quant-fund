import { Outlet } from "react-router-dom";
import { useEffect } from "react";
import { motion } from "framer-motion";
import { Sidebar } from "./Sidebar";
import { useLiveStore } from "@/store/live";
import { useUIStore } from "@/store/ui";
import { ChartDrawer } from "@/components/charts/ChartDrawer";
import { GlobalSearch } from "@/components/ui/GlobalSearch";
import { MatrixRain } from "@/components/ui/MatrixRain";
import { ChatBot } from "@/components/ui/ChatBot";
import { useTheme } from "@/hooks/useTheme";

const pageVariants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit:    { opacity: 0, y: -6 },
};

export function Layout() {
  useTheme(); // applies data-theme to documentElement, initialises theme from localStorage
  const { connect } = useLiveStore();
  const { chartTarget, openChart, closeChart, searchOpen, openSearch, closeSearch } = useUIStore();

  useEffect(() => {
    const cleanup = connect();
    return cleanup;
  }, [connect]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        openSearch();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [openSearch]);

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: "var(--bg)", position: "relative" }}
    >
      {/* Matrix rain — behind everything */}
      <MatrixRain />

      {/* Sidebar sits above rain */}
      <div style={{ position: "relative", zIndex: 10 }}>
        <Sidebar />
      </div>

      {/* Main content area */}
      <div
        className="flex-1 flex flex-col min-w-0 overflow-hidden"
        style={{ position: "relative", zIndex: 5 }}
      >
        <motion.main
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={{ duration: 0.18, ease: "easeOut" }}
          className="flex-1 overflow-y-auto"
        >
          <Outlet />
        </motion.main>
      </div>

      {/* Global overlays */}
      <ChartDrawer
        symbol={chartTarget?.symbol ?? null}
        name={chartTarget?.name}
        onClose={closeChart}
      />
      <GlobalSearch
        open={searchOpen}
        onClose={closeSearch}
        onSelect={(symbol, name) => {
          closeSearch();
          openChart(symbol, name);
        }}
      />
      <ChatBot />
    </div>
  );
}
