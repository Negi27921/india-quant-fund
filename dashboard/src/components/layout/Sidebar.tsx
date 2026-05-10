import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Terminal, ScanSearch, LayoutDashboard,
  Shield, BarChart3, Settings2, ChevronLeft,
  Sun, Moon, LogOut,
} from "lucide-react";
import { AUTH_KEY, LOCK_KEY, FAIL_KEY } from "@/pages/Login";
import { useUIStore } from "@/store/ui";
import { useLiveStore } from "@/store/live";
import { useTheme } from "@/hooks/useTheme";

/* Streamlined nav — 6 items, no redundant pages */
const NAV = [
  { to: "/",           icon: Terminal,        label: "Terminal",   end: true },
  { to: "/screener",   icon: ScanSearch,      label: "Screener",   end: false },
  { to: "/portfolio",  icon: LayoutDashboard, label: "Portfolio",  end: false },
  { to: "/risk",       icon: Shield,          label: "Risk",       end: false },
  { to: "/strategies", icon: BarChart3,       label: "Strategies", end: false },
  { to: "/settings",   icon: Settings2,       label: "Settings",   end: false },
];

function Logo() {
  return (
    <img
      src="/favicon.svg"
      width={36}
      height={44}
      alt="One Piece Quant"
      style={{ display: "block", flexShrink: 0, objectFit: "contain" }}
    />
  );
}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, paperMode, togglePaperMode } = useUIStore();
  const { connected } = useLiveStore();
  const { theme, toggle } = useTheme();

  const W   = sidebarCollapsed ? 60 : 220;
  const expanded = !sidebarCollapsed;

  /* CSS easing — no spring overshoot */
  const ease = "cubic-bezier(0.25, 0.46, 0.45, 0.94)";

  return (
    <div
      className="sidebar-glass relative h-screen flex flex-col shrink-0 overflow-hidden"
      style={{
        width: W,
        transition: `width 220ms ${ease}`,
      }}
    >
      {/* Ambient top glow */}
      <div
        aria-hidden
        style={{
          position: "absolute", top: 0, left: 0, right: 0, height: 120,
          background: "radial-gradient(ellipse at 50% -10%, rgba(0,255,135,0.12) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      {/* ── Logo row ─────────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: expanded ? "14px 12px 14px 14px" : "14px 0",
          justifyContent: expanded ? "flex-start" : "center",
          borderBottom: "1px solid var(--sidebar-border)",
          flexShrink: 0,
          overflow: "hidden",
        }}
      >
        <div style={{ filter: "drop-shadow(0 0 12px rgba(0,255,135,0.4))", flexShrink: 0 }}>
          <Logo />
        </div>

        {/* Title — CSS transition, no mount/unmount */}
        <div
          style={{
            opacity: expanded ? 1 : 0,
            maxWidth: expanded ? 160 : 0,
            overflow: "hidden",
            whiteSpace: "nowrap",
            transition: `opacity 150ms ${ease}, max-width 200ms ${ease}`,
          }}
        >
          <div style={{
            fontSize: 11, fontWeight: 800, letterSpacing: "0.2em",
            color: "var(--text-1)", lineHeight: 1.2,
          }}>
            ONE PIECE
          </div>
          <div style={{
            fontSize: 9, fontWeight: 700, letterSpacing: "0.14em",
            color: "var(--blue)", marginTop: 2,
          }}>
            QUANT TERMINAL
          </div>
        </div>
      </div>

      {/* ── Nav ──────────────────────────────────────────────────────── */}
      <nav style={{ flex: 1, padding: "6px 6px", overflowY: "auto", overflowX: "hidden" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={sidebarCollapsed ? item.label : undefined}
            >
              {({ isActive }) => (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: expanded ? "9px 10px" : "9px 0",
                    justifyContent: expanded ? "flex-start" : "center",
                    borderRadius: 8,
                    position: "relative",
                    background: isActive ? "rgba(0,255,135,0.08)" : "transparent",
                    border: `1px solid ${isActive ? "rgba(0,255,135,0.2)" : "transparent"}`,
                    cursor: "pointer",
                    transition: "all 150ms",
                    overflow: "hidden",
                  }}
                  onMouseEnter={e => {
                    if (!isActive) {
                      (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.04)";
                      (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.06)";
                    }
                  }}
                  onMouseLeave={e => {
                    if (!isActive) {
                      (e.currentTarget as HTMLDivElement).style.background = "transparent";
                      (e.currentTarget as HTMLDivElement).style.borderColor = "transparent";
                    }
                  }}
                >
                  {/* Active left bar */}
                  {isActive && (
                    <motion.div
                      layoutId="nav-active-bar"
                      style={{
                        position: "absolute", left: 0, top: "15%", bottom: "15%",
                        width: 2, borderRadius: 2,
                        background: "var(--blue)",
                        boxShadow: "0 0 8px var(--blue)",
                      }}
                      transition={{ type: "spring", stiffness: 500, damping: 35 }}
                    />
                  )}

                  <item.icon
                    style={{
                      width: 15, height: 15, flexShrink: 0,
                      color: isActive ? "var(--blue)" : "var(--text-3)",
                      filter: isActive ? "drop-shadow(0 0 6px rgba(0,255,135,0.5))" : "none",
                      transition: "color 150ms, filter 150ms",
                    }}
                    strokeWidth={isActive ? 2.5 : 1.75}
                  />

                  {/* Label — CSS max-width trick, no AnimatePresence */}
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: isActive ? 700 : 500,
                      fontFamily: "var(--font-body)",
                      letterSpacing: isActive ? "0.05em" : "0",
                      color: isActive ? "var(--blue)" : "var(--text-3)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      maxWidth: expanded ? 140 : 0,
                      opacity: expanded ? 1 : 0,
                      transition: `max-width 200ms ${ease}, opacity 150ms ${ease}, color 150ms`,
                    }}
                  >
                    {item.label}
                  </span>
                </div>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <div style={{ borderTop: "1px solid var(--sidebar-border)", padding: "8px 6px 6px" }}>

        {/* Paper / Live mode */}
        <div
          style={{
            display: "flex",
            borderRadius: 8,
            overflow: "hidden",
            border: "1px solid var(--border)",
            marginBottom: 6,
            opacity: expanded ? 1 : 0,
            maxHeight: expanded ? 40 : 0,
            transition: `opacity 150ms ${ease}, max-height 200ms ${ease}`,
          }}
        >
          {[
            { label: "LIVE",  val: false, color: "var(--green)", bg: "rgba(52,211,153,0.1)" },
            { label: "PAPER", val: true,  color: "var(--amber)", bg: "rgba(251,191,36,0.1)" },
          ].map(m => (
            <button
              key={String(m.val)}
              onClick={() => paperMode !== m.val && togglePaperMode()}
              style={{
                flex: 1, padding: "7px 0",
                fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
                cursor: "pointer", border: "none",
                background: paperMode === m.val ? m.bg : "transparent",
                color: paperMode === m.val ? m.color : "var(--text-4)",
                transition: "all 150ms",
              }}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* Paper mode compact icon when collapsed */}
        {sidebarCollapsed && (
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 6 }}>
            <button
              onClick={togglePaperMode}
              title={paperMode ? "Switch to Live" : "Switch to Paper"}
              style={{
                width: 32, height: 26, borderRadius: 6, border: "none",
                background: paperMode ? "rgba(251,191,36,0.12)" : "rgba(52,211,153,0.12)",
                color: paperMode ? "var(--amber)" : "var(--green)",
                fontSize: 8, fontWeight: 800, cursor: "pointer",
              }}
            >
              {paperMode ? "P" : "L"}
            </button>
          </div>
        )}

        {/* Connection status */}
        <SidebarFooterBtn
          collapsed={sidebarCollapsed}
          icon={
            <div style={{
              width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
              background: connected ? "var(--green)" : "var(--red)",
              boxShadow: connected ? "0 0 6px var(--green)" : "0 0 6px var(--red)",
              animation: connected ? "pulse-glow 2s ease-in-out infinite" : "none",
            }} />
          }
          label={connected ? "CONNECTED" : "OFFLINE"}
          color={connected ? "var(--green)" : "var(--red)"}
          labelColor={connected ? "var(--green)" : "var(--red)"}
          title={connected ? "API connected" : "API offline"}
          monoLabel
        />

        {/* Theme toggle */}
        <SidebarFooterBtn
          collapsed={sidebarCollapsed}
          icon={theme === "dark"
            ? <Sun style={{ width: 13, height: 13 }} />
            : <Moon style={{ width: 13, height: 13 }} />}
          label={theme === "dark" ? "Light Mode" : "Dark Mode"}
          onClick={toggle}
          title={theme === "dark" ? "Switch to light" : "Switch to dark"}
        />

        {/* Logout */}
        <SidebarFooterBtn
          collapsed={sidebarCollapsed}
          icon={<LogOut style={{ width: 13, height: 13 }} />}
          label="Lock Terminal"
          onClick={() => {
            localStorage.removeItem(AUTH_KEY);
            localStorage.removeItem(LOCK_KEY);
            localStorage.removeItem(FAIL_KEY);
            window.location.reload();
          }}
          hoverColor="var(--red)"
          title="Lock terminal"
        />

        {/* Collapse toggle */}
        <SidebarFooterBtn
          collapsed={sidebarCollapsed}
          icon={
            <ChevronLeft
              style={{
                width: 13, height: 13,
                transform: sidebarCollapsed ? "rotate(180deg)" : "rotate(0deg)",
                transition: `transform 220ms ${ease}`,
              }}
            />
          }
          label="Collapse"
          onClick={toggleSidebar}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        />
      </div>
    </div>
  );
}

/* ── Reusable footer button ──────────────────────────────────────────────── */
function SidebarFooterBtn({
  collapsed, icon, label, onClick, hoverColor, color, labelColor, title, monoLabel,
}: {
  collapsed: boolean;
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  hoverColor?: string;
  color?: string;
  labelColor?: string;
  title?: string;
  monoLabel?: boolean;
}) {
  const ease = "cubic-bezier(0.25, 0.46, 0.45, 0.94)";
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: collapsed ? "center" : "flex-start",
        gap: 8,
        width: "100%",
        padding: "6px 6px",
        borderRadius: 8,
        border: "none",
        background: "transparent",
        color: color ?? "var(--text-3)",
        cursor: onClick ? "pointer" : "default",
        transition: "color 150ms",
        overflow: "hidden",
      }}
      onMouseEnter={e => {
        if (hoverColor) (e.currentTarget as HTMLButtonElement).style.color = hoverColor;
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLButtonElement).style.color = color ?? "var(--text-3)";
      }}
    >
      {icon}
      <span
        style={{
          fontSize: monoLabel ? 9 : 11,
          fontFamily: monoLabel ? "var(--font-mono)" : "var(--font-body)",
          fontWeight: monoLabel ? 700 : 500,
          letterSpacing: monoLabel ? "0.1em" : "0",
          color: labelColor,
          whiteSpace: "nowrap",
          overflow: "hidden",
          maxWidth: collapsed ? 0 : 140,
          opacity: collapsed ? 0 : 1,
          transition: `max-width 200ms ${ease}, opacity 150ms ${ease}`,
          display: "inline-block",
        }}
      >
        {label}
      </span>
    </button>
  );
}
