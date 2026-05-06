import { NavLink } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  LineChart, LayoutDashboard, Activity, History,
  Shield, BarChart3, Settings2, ChevronLeft,
  CalendarDays, Sun, Moon, ScanSearch, LogOut,
} from "lucide-react";
import { AUTH_KEY } from "@/pages/Login";
import { useUIStore } from "@/store/ui";
import { useLiveStore } from "@/store/live";
import { useTheme } from "@/hooks/useTheme";

const NAV = [
  { to: "/",           icon: LineChart,       label: "Market",     end: true },
  { to: "/screener",   icon: ScanSearch,      label: "Screener",   end: false },
  { to: "/portfolio",  icon: LayoutDashboard, label: "Portfolio",  end: false },
  { to: "/pnl",        icon: CalendarDays,    label: "P&L",        end: false },
  { to: "/live",       icon: Activity,        label: "Live Feed",  end: false },
  { to: "/trades",     icon: History,         label: "Trades",     end: false },
  { to: "/risk",       icon: Shield,          label: "Risk",       end: false },
  { to: "/strategies", icon: BarChart3,       label: "Strategies", end: false },
  { to: "/settings",   icon: Settings2,       label: "Settings",   end: false },
];

/* ─── Logo SVG — theme-aware ─────────────────────────────────────────────── */
function Logo({ size = 38, theme = "dark" }: { size?: number; theme?: string }) {
  const isDark = theme !== "light";
  const g1a = isDark ? "#7B9FFF" : "#8FA87E";
  const g1b = isDark ? "#5B7FFF" : "#5D7550";
  const g1c = isDark ? "#8B5CF6" : "#946E12";
  const bgA = isDark ? "#09090F" : "#FAF9F5";
  const bgAOp = isDark ? "0.95" : "1";
  const bgB = isDark ? "#161625" : "#F0EEE6";
  const bgBOp = isDark ? "0.9" : "1";
  const id = isDark ? "dark" : "light";

  return (
    <svg width={size} height={size} viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`logo-g1-${id}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%"   stopColor={g1a} />
          <stop offset="50%"  stopColor={g1b} />
          <stop offset="100%" stopColor={g1c} />
        </linearGradient>
        <linearGradient id={`logo-g2-${id}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%"   stopColor={bgA} stopOpacity={bgAOp} />
          <stop offset="100%" stopColor={bgB} stopOpacity={bgBOp} />
        </linearGradient>
        <filter id={`logo-glow-${id}`}>
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <path d="M18 2 L34 18 L18 34 L2 18 Z" fill={`url(#logo-g2-${id})`} stroke={`url(#logo-g1-${id})`} strokeWidth="1.4"/>
      <path d="M18 8 L28 18 L18 28 L8 18 Z" fill="none" stroke={`url(#logo-g1-${id})`} strokeWidth="0.6" strokeOpacity="0.4"/>
      <text x="18" y="22" textAnchor="middle"
        fontFamily="Inter, sans-serif" fontWeight="800" fontSize="11"
        fill={`url(#logo-g1-${id})`} letterSpacing="-0.5"
        filter={`url(#logo-glow-${id})`}
      >OP</text>
    </svg>
  );
}

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, paperMode, togglePaperMode } = useUIStore();
  const { connected } = useLiveStore();
  const { theme, toggle } = useTheme();
  const W = sidebarCollapsed ? 56 : 210;

  return (
    <motion.aside
      initial={false}
      animate={{ width: W }}
      transition={{ type: "spring", stiffness: 380, damping: 36 }}
      className="sidebar-glass relative h-screen flex flex-col shrink-0 overflow-hidden"
    >
      {/* Top ambient glow */}
      <div className="absolute top-0 left-0 right-0 h-40 pointer-events-none" style={{
        background: "radial-gradient(ellipse at 50% -20%, var(--blue-glow) 0%, transparent 70%)",
      }} />

      {/* Logo */}
      <div className="flex items-center gap-3 px-3 py-4 shrink-0 relative" style={{ borderBottom: "1px solid var(--sidebar-border)" }}>
        <div style={{ filter: "drop-shadow(0 0 14px var(--blue-glow))", flexShrink: 0 }}>
          <Logo size={38} theme={theme} />
        </div>
        <AnimatePresence>
          {!sidebarCollapsed && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.15 }}
            >
              <div style={{ fontSize: 11, fontWeight: 800, color: "var(--text-1)", letterSpacing: "0.18em", fontFamily: "var(--font-body)", lineHeight: 1.2 }}>
                ONE PIECE
              </div>
              <div style={{
                fontSize: theme === "light" ? 10 : 9,
                color: "var(--blue)",
                letterSpacing: theme === "light" ? "0.04em" : "0.14em",
                marginTop: 2,
                fontFamily: theme === "light" ? "var(--font-heading)" : "var(--font-body)",
                fontWeight: theme === "light" ? 400 : 600,
                fontStyle: theme === "light" ? "italic" : "normal",
              }}>
                {theme === "light" ? "Quant Terminal" : "QUANT TERMINAL"}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        <div style={{ padding: "4px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: sidebarCollapsed ? "10px 0" : "9px 12px",
                justifyContent: sidebarCollapsed ? "center" : "flex-start",
                borderRadius: 10,
                textDecoration: "none",
                position: "relative",
                background: isActive ? "var(--blue-dim)" : "transparent",
                border: isActive ? "1px solid var(--border-blue)" : "1px solid transparent",
                color: isActive ? "var(--blue)" : "var(--text-3)",
                transition: "all 150ms",
              })}
              onMouseEnter={e => {
                const el = e.currentTarget;
                const isActive = el.getAttribute("aria-current") === "page";
                if (!isActive) {
                  el.style.background = "var(--card-hover)";
                  el.style.color = "var(--text-2)";
                }
              }}
              onMouseLeave={e => {
                const el = e.currentTarget;
                const isActive = el.getAttribute("aria-current") === "page";
                if (!isActive) {
                  el.style.background = "transparent";
                  el.style.color = "var(--text-3)";
                }
              }}
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <div style={{
                      position: "absolute", left: 0, top: "20%", bottom: "20%",
                      width: 2, borderRadius: 2,
                      background: "var(--blue)",
                    }} />
                  )}
                  <item.icon
                    style={{
                      width: 15, height: 15, flexShrink: 0,
                      color: isActive ? "var(--blue)" : "currentColor",
                    }}
                    strokeWidth={isActive ? 2.5 : 2}
                  />
                  <AnimatePresence>
                    {!sidebarCollapsed && (
                      <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.1 }}
                        style={{
                          fontSize: 13,
                          fontWeight: isActive ? 600 : 500,
                          fontFamily: "Inter, sans-serif",
                          letterSpacing: "-0.01em",
                          color: isActive ? "var(--blue)" : "currentColor",
                        }}
                      >
                        {item.label}
                      </motion.span>
                    )}
                  </AnimatePresence>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div style={{ borderTop: "1px solid var(--sidebar-border)", padding: "8px 8px 4px" }}>
        {/* Paper/Live mode */}
        {!sidebarCollapsed ? (
          <div style={{
            display: "flex", borderRadius: 8, overflow: "hidden",
            border: "1px solid var(--border)", marginBottom: 6,
          }}>
            {[{ label: "● LIVE", val: false, colorVar: "var(--green)", dimVar: "rgba(6,214,160,0.1)" }, { label: "◎ PAPER", val: true, colorVar: "var(--amber)", dimVar: "rgba(255,176,23,0.1)" }].map(m => (
              <button
                key={String(m.val)}
                onClick={() => paperMode !== m.val && togglePaperMode()}
                style={{
                  flex: 1, padding: "6px 0", fontSize: 9, fontWeight: 700,
                  fontFamily: "Inter, sans-serif", letterSpacing: "0.08em",
                  cursor: "pointer", border: "none",
                  background: paperMode === m.val ? m.dimVar : "transparent",
                  color: paperMode === m.val ? m.colorVar : "var(--text-4)",
                  transition: "all 150ms",
                }}
              >
                {m.label}
              </button>
            ))}
          </div>
        ) : (
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 6 }}>
            <button
              onClick={togglePaperMode}
              style={{
                width: 32, height: 28, borderRadius: 8, border: "none",
                background: paperMode ? "var(--amber-dim)" : "var(--green-dim)",
                color: paperMode ? "var(--amber)" : "var(--green)",
                fontSize: 8, fontWeight: 800, cursor: "pointer",
              }}
            >{paperMode ? "P" : "L"}</button>
          </div>
        )}

        {/* Status */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 6px" }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
            background: connected ? "var(--green)" : "var(--red)",
            boxShadow: connected ? "0 0 6px var(--green)" : "0 0 6px var(--red)",
          }} />
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", fontFamily: "Inter, sans-serif",
                  color: connected ? "var(--green)" : "var(--red)" }}>
                {connected ? "CONNECTED" : "OFFLINE"}
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Theme toggle */}
        <button
          onClick={toggle}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          style={{
            display: "flex", alignItems: "center", justifyContent: sidebarCollapsed ? "center" : "flex-start",
            gap: 8, width: "100%", padding: "6px 6px", borderRadius: 8, border: "none",
            background: "transparent", color: "var(--text-3)", cursor: "pointer", transition: "color 150ms",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--blue)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
        >
          {theme === "dark"
            ? <Sun style={{ width: 13, height: 13 }} />
            : <Moon style={{ width: 13, height: 13 }} />}
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                style={{ fontSize: 11, fontFamily: "Inter, sans-serif", fontWeight: 500 }}
              >
                {theme === "dark" ? "Light Mode" : "Dark Mode"}
              </motion.span>
            )}
          </AnimatePresence>
        </button>

        {/* Logout */}
        <button
          onClick={() => { localStorage.removeItem(AUTH_KEY); window.location.reload(); }}
          title="Lock terminal"
          style={{
            display: "flex", alignItems: "center", justifyContent: sidebarCollapsed ? "center" : "flex-start",
            gap: 8, width: "100%", padding: "6px 6px", borderRadius: 8, border: "none",
            background: "transparent", color: "var(--text-4)", cursor: "pointer", transition: "color 150ms",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--red)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--text-4)")}
        >
          <LogOut style={{ width: 13, height: 13 }} />
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 500 }}>
                Lock Terminal
              </motion.span>
            )}
          </AnimatePresence>
        </button>

        {/* Collapse */}
        <button
          onClick={toggleSidebar}
          style={{
            display: "flex", alignItems: "center", justifyContent: sidebarCollapsed ? "center" : "flex-start",
            gap: 8, width: "100%", padding: "6px 6px",
            borderRadius: 8, border: "none", background: "transparent",
            color: "var(--text-4)", cursor: "pointer", transition: "color 150ms",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--text-3)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--text-4)")}
        >
          <motion.div animate={{ rotate: sidebarCollapsed ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronLeft style={{ width: 13, height: 13 }} />
          </motion.div>
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                style={{ fontSize: 11, fontFamily: "Inter, sans-serif", fontWeight: 500 }}>
                Collapse
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </motion.aside>
  );
}
