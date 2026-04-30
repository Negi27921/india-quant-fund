import { NavLink } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard,
  TrendingUp,
  ShoppingCart,
  Shield,
  BarChart3,
  Activity,
  ChevronLeft,
  Zap,
  Settings2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import { useLiveStore } from "@/store/live";
import { useSystemHealth } from "@/api/queries";

const NAV_ITEMS = [
  { to: "/", icon: LayoutDashboard, label: "Portfolio" },
  { to: "/live", icon: Activity, label: "Live PnL" },
  { to: "/trades", icon: ShoppingCart, label: "Trades" },
  { to: "/risk", icon: Shield, label: "Risk" },
  { to: "/strategies", icon: BarChart3, label: "Strategies" },
  { to: "/settings",   icon: Settings2, label: "Settings"   },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();
  const { connected } = useLiveStore();
  const { data: health } = useSystemHealth();

  return (
    <motion.aside
      initial={false}
      animate={{ width: sidebarCollapsed ? 64 : 220 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="relative h-screen bg-bg-surface border-r border-border flex flex-col shrink-0 overflow-hidden z-20"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 min-w-0">
        <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0">
          <TrendingUp className="w-4 h-4 text-primary" />
        </div>
        <AnimatePresence>
          {!sidebarCollapsed && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.15 }}
              className="min-w-0"
            >
              <p className="text-sm font-semibold text-text-primary truncate">IQF</p>
              <p className="text-[10px] text-text-muted truncate">India Quant Fund</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 space-y-0.5">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-2 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group",
                isActive
                  ? "bg-primary/10 text-primary border border-primary/15"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  className={cn(
                    "w-4 h-4 shrink-0",
                    isActive ? "text-primary" : "text-text-muted group-hover:text-text-secondary"
                  )}
                />
                <AnimatePresence>
                  {!sidebarCollapsed && (
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.1 }}
                      className="truncate"
                    >
                      {item.label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Status footer */}
      <div className="p-2 border-t border-border space-y-1">
        {/* WS status */}
        <div
          className={cn(
            "flex items-center gap-2 px-2 py-2 rounded-lg",
            sidebarCollapsed && "justify-center"
          )}
        >
          <div
            className={cn(
              "w-1.5 h-1.5 rounded-full shrink-0",
              connected ? "bg-success animate-pulse" : "bg-danger"
            )}
          />
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-xs text-text-muted"
              >
                {connected ? "Live" : "Reconnecting…"}
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Paper trading badge */}
        {health?.paper_trading && (
          <div
            className={cn(
              "flex items-center gap-2 px-2 py-1.5 rounded-lg bg-warning/10 border border-warning/20",
              sidebarCollapsed && "justify-center"
            )}
          >
            <Zap className="w-3 h-3 text-warning shrink-0" />
            <AnimatePresence>
              {!sidebarCollapsed && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="text-[10px] text-warning font-medium"
                >
                  PAPER MODE
                </motion.span>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Collapse toggle */}
        <button
          onClick={toggleSidebar}
          className={cn(
            "w-full flex items-center gap-2 px-2 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors",
            sidebarCollapsed && "justify-center"
          )}
        >
          <motion.div
            animate={{ rotate: sidebarCollapsed ? 180 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronLeft className="w-4 h-4" />
          </motion.div>
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-xs"
              >
                Collapse
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </motion.aside>
  );
}
