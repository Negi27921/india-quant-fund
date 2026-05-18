import { NavLink } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Terminal, ScanSearch, LayoutDashboard,
  Shield, BarChart3, Settings2, ChevronLeft, LogOut,
  Sun, Moon, BookOpen,
} from "lucide-react";
import { AUTH_KEY, LOCK_KEY, FAIL_KEY } from "@/pages/Login";
import { useUIStore } from "@/store/ui";
import { useLiveStore } from "@/store/live";
import { useTheme } from "@/hooks/useTheme";

const NAV = [
  { to: "/",           icon: Terminal,        label: "Terminal",   end: true },
  { to: "/screener",   icon: ScanSearch,      label: "Screener",   end: false },
  { to: "/portfolio",  icon: LayoutDashboard, label: "Portfolio",  end: false },
  { to: "/risk",       icon: Shield,          label: "Risk",       end: false },
  { to: "/strategies", icon: BarChart3,       label: "Strategies", end: false },
  { to: "/settings",   icon: Settings2,       label: "Settings",   end: false },
  { to: "/journal",    icon: BookOpen,        label: "Journal",    end: false },
];

const ease = "cubic-bezier(0.25, 0.46, 0.45, 0.94)";

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, paperMode, togglePaperMode } = useUIStore();
  const { connected } = useLiveStore();
  const { theme, toggle: toggleTheme } = useTheme();

  const W = sidebarCollapsed ? 60 : 220;
  const expanded = !sidebarCollapsed;

  return (
    <div
      className="sidebar-glass relative h-screen flex flex-col shrink-0 overflow-hidden"
      style={{ width: W, transition: `width 220ms ${ease}` }}
    >
      {/* ── Logo ── */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: expanded ? "16px 14px" : "16px 0",
        justifyContent: expanded ? "flex-start" : "center",
        borderBottom: "1px solid var(--sidebar-border)",
        flexShrink: 0, overflow: "hidden",
      }}>
        <img
          src="/favicon.svg"
          alt="One Piece"
          style={{ width: 32, height: 32, flexShrink: 0, borderRadius: 6 }}
        />
        <div style={{
          opacity: expanded ? 1 : 0,
          maxWidth: expanded ? 160 : 0,
          overflow: "hidden", whiteSpace: "nowrap",
          transition: `opacity 150ms ${ease}, max-width 200ms ${ease}`,
        }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: "var(--text-1)", letterSpacing: "0.04em", fontFamily: "var(--font-heading)", fontStyle: "italic" }}>
            One Piece
          </div>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.18em", color: "var(--accent)", marginTop: 1, fontFamily: "var(--font-body)", textTransform: "uppercase" }}>
            Quant Terminal
          </div>
        </div>
      </div>

      {/* ── Nav ── */}
      <nav style={{ flex: 1, padding: "8px 6px", overflowY: "auto", overflowX: "hidden" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} title={sidebarCollapsed ? item.label : undefined}>
              {({ isActive }) => (
                <div
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: expanded ? "9px 10px" : "9px 0",
                    justifyContent: expanded ? "flex-start" : "center",
                    borderRadius: 8, position: "relative",
                    background: isActive ? "var(--accent-dim)" : "transparent",
                    border: `1.5px solid ${isActive ? "var(--accent-border)" : "transparent"}`,
                    cursor: "pointer", transition: "all 150ms",
                  }}
                  onMouseEnter={e => {
                    if (!isActive) {
                      (e.currentTarget as HTMLDivElement).style.background = "var(--surface-2)";
                      (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
                    }
                  }}
                  onMouseLeave={e => {
                    if (!isActive) {
                      (e.currentTarget as HTMLDivElement).style.background = "transparent";
                      (e.currentTarget as HTMLDivElement).style.borderColor = "transparent";
                    }
                  }}
                >
                  {isActive && (
                    <motion.div
                      layoutId="nav-active-bar"
                      style={{
                        position: "absolute", left: 0, top: "15%", bottom: "15%",
                        width: 3, borderRadius: 2, background: "var(--accent)",
                      }}
                      transition={{ type: "spring", stiffness: 500, damping: 35 }}
                    />
                  )}
                  <item.icon style={{
                    width: 15, height: 15, flexShrink: 0,
                    color: isActive ? "var(--accent)" : "var(--text-3)",
                    transition: "color 150ms",
                  }} strokeWidth={isActive ? 2.5 : 1.75} />
                  <span style={{
                    fontSize: 12, fontWeight: isActive ? 700 : 500,
                    fontFamily: "var(--font-body)",
                    color: isActive ? "var(--accent)" : "var(--text-2)",
                    whiteSpace: "nowrap", overflow: "hidden",
                    maxWidth: expanded ? 140 : 0, opacity: expanded ? 1 : 0,
                    transition: `max-width 200ms ${ease}, opacity 150ms ${ease}, color 150ms`,
                  }}>
                    {item.label}
                  </span>
                </div>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* ── Footer ── */}
      <div style={{ borderTop: "1px solid var(--sidebar-border)", padding: "8px 6px 10px" }}>

        {/* Live / Paper toggle */}
        <div style={{
          display: "flex", borderRadius: 8, overflow: "hidden",
          border: "1px solid var(--border)", marginBottom: 6,
          opacity: expanded ? 1 : 0, maxHeight: expanded ? 36 : 0,
          transition: `opacity 150ms ${ease}, max-height 200ms ${ease}`,
        }}>
          {[
            { label: "LIVE",  val: false, color: "var(--green)",   bg: "var(--green-dim)" },
            { label: "PAPER", val: true,  color: "var(--amber)",   bg: "var(--amber-dim)" },
          ].map(m => (
            <button key={String(m.val)} onClick={() => paperMode !== m.val && togglePaperMode()} style={{
              flex: 1, padding: "6px 0",
              fontSize: 9, fontWeight: 800, letterSpacing: "0.1em",
              cursor: "pointer", border: "none",
              background: paperMode === m.val ? m.bg : "transparent",
              color: paperMode === m.val ? m.color : "var(--text-4)",
              transition: "all 150ms",
            }}>
              {m.label}
            </button>
          ))}
        </div>

        {sidebarCollapsed && (
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 6 }}>
            <button onClick={togglePaperMode} title={paperMode ? "Switch to Live" : "Switch to Paper"} style={{
              width: 32, height: 26, borderRadius: 6, border: "none",
              background: paperMode ? "var(--amber-dim)" : "var(--green-dim)",
              color: paperMode ? "var(--amber)" : "var(--green)",
              fontSize: 8, fontWeight: 800, cursor: "pointer",
            }}>
              {paperMode ? "P" : "L"}
            </button>
          </div>
        )}

        {/* Connection status */}
        <FooterBtn collapsed={sidebarCollapsed} title={connected ? "API connected" : "API offline"}
          icon={<div style={{
            width: 7, height: 7, borderRadius: "50%",
            background: connected ? "var(--green)" : "var(--red)",
            boxShadow: connected ? "0 0 6px var(--green)" : "0 0 6px var(--red)",
            animation: "pulse-dot 2s ease-in-out infinite",
          }} />}
          label={connected ? "CONNECTED" : "OFFLINE"}
          labelColor={connected ? "var(--green)" : "var(--red)"}
          monoLabel
        />

        {/* Theme toggle */}
        <FooterBtn collapsed={sidebarCollapsed}
          title={theme === "dark" ? "Light mode" : "Dark mode"}
          icon={theme === "dark"
            ? <Sun style={{ width: 13, height: 13 }} />
            : <Moon style={{ width: 13, height: 13 }} />}
          label={theme === "dark" ? "Light Mode" : "Dark Mode"}
          onClick={toggleTheme}
        />

        {/* Logout */}
        <FooterBtn collapsed={sidebarCollapsed} title="Lock terminal"
          icon={<LogOut style={{ width: 13, height: 13 }} />}
          label="Lock Terminal" hoverColor="var(--red)"
          onClick={() => {
            localStorage.removeItem(AUTH_KEY);
            localStorage.removeItem(LOCK_KEY);
            localStorage.removeItem(FAIL_KEY);
            window.location.reload();
          }}
        />

        {/* Collapse */}
        <FooterBtn collapsed={sidebarCollapsed} title={sidebarCollapsed ? "Expand" : "Collapse"}
          icon={<ChevronLeft style={{
            width: 13, height: 13,
            transform: sidebarCollapsed ? "rotate(180deg)" : "rotate(0deg)",
            transition: `transform 220ms ${ease}`,
          }} />}
          label="Collapse" onClick={toggleSidebar}
        />
      </div>
    </div>
  );
}

function FooterBtn({ collapsed, icon, label, onClick, hoverColor, labelColor, title, monoLabel }: {
  collapsed: boolean; icon: React.ReactNode; label: string;
  onClick?: () => void; hoverColor?: string; labelColor?: string;
  title?: string; monoLabel?: boolean;
}) {
  return (
    <button onClick={onClick} title={title} style={{
      display: "flex", alignItems: "center",
      justifyContent: collapsed ? "center" : "flex-start",
      gap: 8, width: "100%", padding: "6px 6px",
      borderRadius: 8, border: "none", background: "transparent",
      color: "var(--text-3)", cursor: onClick ? "pointer" : "default",
      transition: "color 150ms",
    }}
      onMouseEnter={e => { if (hoverColor) (e.currentTarget as HTMLButtonElement).style.color = hoverColor; }}
      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-3)"; }}
    >
      {icon}
      <span style={{
        fontSize: monoLabel ? 9 : 11,
        fontFamily: monoLabel ? "var(--font-mono)" : "var(--font-body)",
        fontWeight: monoLabel ? 700 : 600,
        letterSpacing: monoLabel ? "0.1em" : "0",
        color: labelColor, whiteSpace: "nowrap", overflow: "hidden",
        maxWidth: collapsed ? 0 : 140, opacity: collapsed ? 0 : 1,
        transition: `max-width 200ms ${ease}, opacity 150ms ${ease}`,
        display: "inline-block",
      }}>
        {label}
      </span>
    </button>
  );
}
