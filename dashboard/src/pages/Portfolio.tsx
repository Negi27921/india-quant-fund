import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  DollarSign, TrendingDown, Layers, Activity, TrendingUp,
  Plus, Trash2, LogOut, BarChart3,
  CalendarDays, BarChart2, Target, Flame,
  ChevronLeft, ChevronRight, Wifi, WifiOff, X,
} from "lucide-react";
import {
  AreaChart, Area, ResponsiveContainer, Tooltip as ReTip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, ReferenceLine,
} from "recharts";
import { format } from "date-fns";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { StatCard } from "@/components/ui/StatCard";
import { EquityChart } from "@/components/charts/EquityChart";
import { SectorPieChart } from "@/components/charts/SectorPieChart";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { SkeletonCard, SkeletonTable } from "@/components/ui/Skeleton";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { AddPositionModal } from "@/components/ui/AddPositionModal";
import { ExitPositionModal } from "@/components/ui/ExitPositionModal";
import { OrderStatusBadge, SideBadge } from "@/components/ui/Badge";
import {
  usePositions, useSectorExposure, useEquityCurve,
  useOrders, useDrawdownHistory,
} from "@/api/queries";
import {
  usePaperPositions, useDeletePaperPosition, useLivePositions, useDeleteLivePosition,
  usePaperTrades, useStrategyPnl,
  useJournalSummary, useJournalPnLCalendar, useJournalPositions,
  type PaperPosition,
} from "@/api/pnl-queries";
import { useEnvSummary, useAgentConfig } from "@/api/settings-queries";
import { api } from "@/api/client";
import { formatCurrency, formatPct, pctColor, formatDateTime } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import { useLiveStore } from "@/store/live";
import { STRATEGY_LABELS } from "@/lib/constants";

// ── Types ──────────────────────────────────────────────────────────────────────
type MainTab = "holdings" | "pnl" | "trades" | "live";
type HoldingsTabValue = "paper" | "live";

// ── Helpers ────────────────────────────────────────────────────────────────────
const numColor = (v: number) => (v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-3)");
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const DAYS_OPTIONS_EQUITY = [30, 90, 252, 756] as const;

function pnlCellBg(pct: number): string {
  if (pct === 0) return "rgba(255,255,255,0.03)";
  const t = Math.min(Math.abs(pct) / 3, 1);
  const a = 0.1 + t * 0.45;
  return pct > 0 ? `rgba(39,174,96,${a})` : `rgba(231,76,60,${a})`;
}

function monthStart(year: number, m: number) {
  return `${year}-${String(m).padStart(2, "0")}-01`;
}
function monthEnd(year: number, m: number) {
  return `${year}-${String(m).padStart(2, "0")}-${String(new Date(year, m, 0).getDate()).padStart(2, "0")}`;
}

// ── Shared sub-components ──────────────────────────────────────────────────────
function PnlChip({ v }: { v: number }) {
  const pos = v >= 0;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      fontFamily: "var(--font-mono)", fontSize: 11.5, fontWeight: 700,
      color: pos ? "var(--green)" : "var(--red)",
    }}>
      {pos ? <TrendingUp style={{ width: 10, height: 10 }} /> : <TrendingDown style={{ width: 10, height: 10 }} />}
      {pos ? "+" : ""}{v.toFixed(2)}%
    </span>
  );
}

function TabBtn({
  active, label, onClick,
}: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 20px", borderRadius: 8, fontSize: 11, fontWeight: 700,
        fontFamily: "var(--font-body)", letterSpacing: "0.1em", cursor: "pointer",
        transition: "all 150ms",
        background: active ? "rgba(39,174,96,0.08)" : "transparent",
        border: active ? "1px solid var(--accent-border)" : "1px solid transparent",
        color: active ? "var(--accent)" : "var(--text-3)",
      }}
    >
      {label}
    </button>
  );
}

// ── Capital stat cell ─────────────────────────────────────────────────────────
function CapStat({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "var(--font-body)", fontWeight: 700, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: color ?? "var(--text-1)", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>{sub}</div>}
    </div>
  );
}

// ── HOLDINGS TAB ──────────────────────────────────────────────────────────────
function HoldingsTab({ equityCurveDays, setEquityCurveDays, openChart }: {
  equityCurveDays: number;
  setEquityCurveDays: (d: number) => void;
  openChart: (sym: string, name: string) => void;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [tab, setTab] = useState<HoldingsTabValue>("live");
  const [exitTarget, setExitTarget] = useState<PaperPosition | null>(null);
  const [exitOpen, setExitOpen] = useState(false);

  const { data: sectors } = useSectorExposure();
  const { data: equity, isLoading: equityLoading } = useEquityCurve(equityCurveDays);
  const { data: journalEquity = [] } = useJournalPnLCalendar(new Date().getFullYear());
  const { data: paperPositions, isLoading: paperLoading } = usePaperPositions();
  const { data: journalRaw, isLoading: journalLoading } = useJournalPositions();
  const { data: dhanRaw,    isLoading: dhanLoading    } = useLivePositions();
  const { data: journalSummary } = useJournalSummary();
  const { data: envSummary } = useEnvSummary();
  const { data: agentConfig } = useAgentConfig();
  const deletePaper = useDeletePaperPosition();
  const deleteLive  = useDeleteLivePosition();
  usePositions();

  // Merge journal + Dhan: Dhan data (actual broker) takes priority for matching tickers.
  // Journal entries fill gaps for trades not in Dhan, and enrich Dhan entries with notes/strategy.
  const livePositions = useMemo<PaperPosition[]>(() => {
    const journal = journalRaw ?? [];
    const dhan    = dhanRaw    ?? [];
    const merged  = new Map<string, PaperPosition>();
    for (const pos of dhan) {
      const key = pos.ticker.replace(".NS","").replace(".BO","").toUpperCase();
      merged.set(key, pos);
    }
    for (const pos of journal) {
      const key = pos.ticker.replace(".NS","").replace(".BO","").toUpperCase();
      if (!merged.has(key)) {
        merged.set(key, pos);
      } else {
        const existing = merged.get(key)!;
        merged.set(key, {
          ...existing,
          notes:    pos.notes    || existing.notes,
          strategy: pos.strategy || existing.strategy,
        });
      }
    }
    return Array.from(merged.values());
  }, [journalRaw, dhanRaw]);
  const liveLoading = journalLoading || dhanLoading;

  const activePositions: PaperPosition[] = tab === "paper" ? (paperPositions ?? []) : (livePositions ?? []);
  const activeLoading = tab === "paper" ? paperLoading : liveLoading;
  const totalCost  = activePositions.reduce((s, p) => s + p.quantity * p.avg_buy_price, 0);
  const totalValue = activePositions.reduce((s, p) => s + p.quantity * (p.current_price ?? p.avg_buy_price), 0);
  const unrealPnl  = totalValue - totalCost;
  const pnlColor   = unrealPnl >= 0 ? "var(--green)" : "var(--red)";

  // Paper portfolio capital calculations (from settings)
  const baseCapital   = envSummary?.initial_capital ?? 1_000_000;   // ₹10L default
  const tradeAmount   = agentConfig?.trade_amount    ?? 50_000;
  const freeCapital   = baseCapital - totalCost;
  const portfolioVal  = baseCapital + unrealPnl;
  const deployedPct   = baseCapital > 0 ? (totalCost / baseCapital) * 100 : 0;
  const portfolioPct  = baseCapital > 0 ? (unrealPnl / baseCapital) * 100 : 0;
  const portfolioColor = portfolioVal >= baseCapital ? "var(--green)" : "var(--red)";

  const fmtL = (v: number) => `₹${(v / 1e5).toFixed(2)}L`;

  return (
    <>
      <AddPositionModal open={addOpen} onClose={() => setAddOpen(false)} mode={tab} />
      <ExitPositionModal
        open={exitOpen} position={exitTarget} mode={tab}
        onClose={() => { setExitOpen(false); setExitTarget(null); }}
      />

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 card p-4">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)", letterSpacing: "0.08em", fontFamily: "var(--font-body)" }}>
              {tab === "live" ? "JOURNAL NAV CURVE" : "SCREENER EQUITY CURVE"}
            </span>
            {tab === "paper" && (
              <div style={{ display: "flex", gap: 4 }}>
                {DAYS_OPTIONS_EQUITY.map(d => (
                  <button key={d} onClick={() => setEquityCurveDays(d)} style={{
                    fontSize: 10, padding: "2px 8px", borderRadius: 6, cursor: "pointer",
                    background: equityCurveDays === d ? "rgba(39,174,96,0.1)" : "transparent",
                    border: equityCurveDays === d ? "1px solid rgba(39,174,96,0.25)" : "1px solid transparent",
                    color: equityCurveDays === d ? "var(--accent)" : "var(--text-3)",
                    fontFamily: "var(--font-body)", fontWeight: 600,
                  }}>
                    {d === 252 ? "1Y" : d === 756 ? "3Y" : d === 90 ? "3M" : "1M"}
                  </button>
                ))}
              </div>
            )}
          </div>
          {tab === "live" ? (
            journalEquity.length > 1 ? (
              <EquityChart data={journalEquity.map(d => ({ date: d.date, portfolio_value: d.portfolio_value, day_pnl_pct: d.pnl_pct, drawdown_pct: 0 }))} height={180} />
            ) : (
              <div style={{ height: 180, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}>
                <span style={{ fontSize: 13, color: "var(--text-3)" }}>No closed journal trades yet</span>
                <span style={{ fontSize: 11, color: "var(--text-4)" }}>Equity curve builds as you close trades in the Trading Journal</span>
              </div>
            )
          ) : (
            equityLoading
              ? <div style={{ height: 180, background: "rgba(39,174,96,0.03)", borderRadius: 8 }} />
              : <EquityChart data={equity ?? []} height={180} />
          )}
        </div>
        <div className="card p-4">
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)", letterSpacing: "0.08em", display: "block", marginBottom: 12, fontFamily: "var(--font-body)" }}>SECTOR EXPOSURE</span>
          <SectorPieChart data={sectors ?? []} />
        </div>
      </div>

      {/* Positions table */}
      <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>

        {/* ── Tab row + capital summary ── */}
        <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          {/* Tab switcher + count */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: tab === "paper" ? 14 : 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <TabBtn active={tab === "paper"} label="PAPER" onClick={() => setTab("paper")} />
              <TabBtn active={tab === "live"}  label="LIVE"  onClick={() => setTab("live")} />
              {activePositions.length > 0 && (
                <span style={{ fontSize: 10, color: "var(--text-3)", marginLeft: 4, fontFamily: "var(--font-mono)" }}>
                  {activePositions.length} pos
                </span>
              )}
            </div>
            <button
              onClick={() => setAddOpen(true)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "7px 14px", borderRadius: 8, fontSize: 11, fontWeight: 700,
                fontFamily: "var(--font-body)", cursor: "pointer",
                background: tab === "live"
                  ? "linear-gradient(135deg, rgba(39,174,96,0.2), rgba(39,174,96,0.05))"
                  : "rgba(39,174,96,0.08)",
                border: tab === "live" ? "1px solid rgba(39,174,96,0.4)" : "1px solid var(--accent-border)",
                color: tab === "live" ? "var(--green)" : "var(--accent)",
              }}
            >
              <Plus style={{ width: 12, height: 12 }} />
              Add Position
            </button>
          </div>

          {/* ── Paper portfolio capital banner ── */}
          {tab === "paper" && (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
              gap: 12,
              padding: "12px 14px",
              background: "rgba(39,174,96,0.03)",
              border: "1px solid rgba(39,174,96,0.12)",
              borderRadius: 10,
            }}>
              <CapStat
                label="Base Capital"
                value={fmtL(baseCapital)}
                sub="from Settings → Env"
              />
              <CapStat
                label="Deployed"
                value={fmtL(totalCost)}
                sub={`${deployedPct.toFixed(1)}% allocated`}
              />
              <CapStat
                label="Free Capital"
                value={fmtL(freeCapital)}
                color={freeCapital >= 0 ? "var(--green)" : "var(--red)"}
                sub="available to trade"
              />
              <CapStat
                label="Portfolio Value"
                value={fmtL(portfolioVal)}
                color={portfolioColor}
                sub={`${portfolioPct >= 0 ? "+" : ""}${portfolioPct.toFixed(2)}% from base`}
              />
              <CapStat
                label="Unrealised P&L"
                value={`${unrealPnl >= 0 ? "+" : ""}₹${Math.abs(unrealPnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                color={pnlColor}
                sub="open positions"
              />
              <CapStat
                label="Trade Size (cfg)"
                value={`₹${tradeAmount.toLocaleString("en-IN")}`}
                sub="from Settings → Agent"
              />
            </div>
          )}

          {/* ── Live Journal summary banner ── */}
          {tab === "live" && (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
              gap: 12, padding: "12px 14px", marginTop: 10,
              background: "rgba(39,174,96,0.03)",
              border: "1px solid rgba(39,174,96,0.12)",
              borderRadius: 10,
            }}>
              <CapStat label="Live NAV" value={journalSummary ? `₹${(journalSummary.nav / 1e5).toFixed(2)}L` : "—"} color="var(--green)" sub="from Journal" />
              <CapStat label="Invested" value={journalSummary ? `₹${(journalSummary.total_invested / 1e5).toFixed(2)}L` : "—"} sub="open cost basis" />
              <CapStat label="Realized P&L" value={journalSummary ? `${journalSummary.realized_pnl >= 0 ? "+" : ""}₹${Math.abs(journalSummary.realized_pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"} color={journalSummary ? (journalSummary.realized_pnl >= 0 ? "var(--green)" : "var(--red)") : undefined} sub="closed trades" />
              <CapStat label="Unrealized" value={journalSummary ? `${journalSummary.unrealized_pnl >= 0 ? "+" : ""}₹${Math.abs(journalSummary.unrealized_pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"} color={journalSummary ? (journalSummary.unrealized_pnl >= 0 ? "var(--green)" : "var(--red)") : undefined} sub="open positions" />
              <CapStat label="Drawdown" value={journalSummary ? `-${journalSummary.drawdown.toFixed(2)}%` : "—"} color="var(--red)" sub="from peak" />
              <CapStat label="Positions" value={journalSummary ? String(journalSummary.open_positions) : "—"} sub="open trades" />
            </div>
          )}
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                {["SYMBOL", "NAME", "SECTOR", "QTY", "POS SIZE", "AVG BUY", "CMP", "DAYS", "P&L", "RET%", "WT%", "ACTIONS"].map((h, i) => (
                  <th key={h} className={i >= 3 ? "tbl-th-r" : "tbl-th"} style={{ paddingLeft: i === 0 ? 20 : undefined }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <AnimatePresence>
                {activeLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="tbl-row">
                      {Array.from({ length: 12 }).map((_, j) => (
                        <td key={j} className="tbl-cell">
                          <div style={{ height: 11, borderRadius: 4, background: "rgba(39,174,96,0.1)", width: [80,130,70,40,80,70,70,40,70,60,50,80][j] }} />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : activePositions.length === 0 ? (
                  <tr>
                    <td colSpan={12} style={{ textAlign: "center", padding: "48px 20px" }}>
                      <div style={{ color: "var(--text-3)", fontSize: 13, marginBottom: 12 }}>
                        No {tab === "paper" ? "paper trading" : "live"} positions yet
                      </div>
                      <button
                        onClick={() => setAddOpen(true)}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 6,
                          padding: "8px 20px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                          fontFamily: "var(--font-body)", cursor: "pointer",
                          background: "var(--accent-dim)", border: "1px solid var(--accent-border)", color: "var(--accent)",
                        }}
                      >
                        <Plus style={{ width: 13, height: 13 }} /> Add your first {tab} position
                      </button>
                    </td>
                  </tr>
                ) : (
                  activePositions.map((pos, idx) => {
                    const pnlPos = (pos.unrealized_pnl ?? 0) >= 0;
                    const cmp = pos.current_price ?? pos.avg_buy_price;
                    const sym = pos.ticker.replace(".NS", "").replace(".BO", "");
                    return (
                      <motion.tr
                        key={pos.ticker} className="tbl-row"
                        initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 8 }} transition={{ delay: idx * 0.03 }}
                      >
                        <td className="tbl-cell" style={{ paddingLeft: 20 }}>
                          <span style={{ fontWeight: 700, color: "var(--accent)", fontSize: 12, fontFamily: "var(--font-mono)" }}>{sym}</span>
                        </td>
                        <td className="tbl-cell-muted" style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pos.name ?? "—"}</td>
                        <td className="tbl-cell">
                          {pos.sector ? (
                            <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 10, whiteSpace: "nowrap", background: "var(--amber-dim)", border: "1px solid var(--amber-border)", color: "var(--amber)", fontFamily: "var(--font-body)", fontWeight: 600 }}>{pos.sector}</span>
                          ) : "—"}
                        </td>
                        <td className="tbl-cell-r">{pos.quantity}</td>
                        <td className="tbl-cell-r" style={{ color: "var(--text-2)", fontWeight: 600 }}>
                          ₹{(pos.quantity * pos.avg_buy_price).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                        </td>
                        <td className="tbl-cell-r">₹{pos.avg_buy_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                        <td className="tbl-cell-r" style={{ color: "var(--text-1)", fontWeight: 600 }}>₹{cmp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                        <td className="tbl-cell-r" style={{ color: "var(--text-3)" }}>{pos.days_held ?? 0}d</td>
                        <td className="tbl-cell-r" style={{ color: pnlPos ? "var(--green)" : "var(--red)", fontWeight: 700 }}>
                          {pnlPos ? "+" : ""}₹{Math.abs(pos.unrealized_pnl ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                        </td>
                        <td className="tbl-cell-r"><PnlChip v={pos.pnl_pct ?? 0} /></td>
                        <td className="tbl-cell-r" style={{ color: "var(--text-3)" }}>{(pos.weight ?? 0).toFixed(1)}%</td>
                        <td className="tbl-cell row-actions" style={{ paddingRight: 16, textAlign: "right" }}>
                          <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            <button title="Open Chart" onClick={() => openChart(sym, pos.name ?? sym)}
                              style={{ padding: "4px 6px", borderRadius: 6, background: "var(--accent-dim)", border: "1px solid var(--accent-border)", color: "var(--accent)", cursor: "pointer" }}>
                              <BarChart3 style={{ width: 11, height: 11 }} />
                            </button>
                            <button title="Exit Position" onClick={() => { setExitTarget(pos); setExitOpen(true); }}
                              style={{ padding: "4px 6px", borderRadius: 6, background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.22)", color: "#FBBF24", cursor: "pointer" }}>
                              <LogOut style={{ width: 11, height: 11 }} />
                            </button>
                            <button title="Delete" onClick={() => tab === "paper" ? deletePaper.mutate(pos.ticker) : deleteLive.mutate(pos.ticker)}
                              style={{ padding: "4px 6px", borderRadius: 6, background: "rgba(231,76,60,0.08)", border: "1px solid rgba(231,76,60,0.18)", color: "var(--red)", cursor: "pointer" }}>
                              <Trash2 style={{ width: 11, height: 11 }} />
                            </button>
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })
                )}
              </AnimatePresence>
            </tbody>
          </table>
        </div>
      </motion.div>
    </>
  );
}

// ── P&L TAB ───────────────────────────────────────────────────────────────────
function CalendarHeatmap({ year, month, data, selectedDay, setSelectedDay }: {
  year: number;
  month: number;
  data: { date: string; pnl: number; pnl_pct: number }[];
  selectedDay: string | null;
  setSelectedDay: (d: string | null) => void;
}) {
  const dataMap = useMemo(() => {
    const m: Record<string, { pnl: number; pnl_pct: number }> = {};
    data.forEach(d => { m[d.date.slice(0, 10)] = d; });
    return m;
  }, [data]);

  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDay = new Date(year, month - 1, 1).getDay();
  const offset = firstDay === 0 ? 6 : firstDay - 1;
  const cells: { day: number | null; dateStr: string | null }[] = [];
  for (let i = 0; i < offset; i++) cells.push({ day: null, dateStr: null });
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, dateStr: `${year}-${String(month).padStart(2,"0")}-${String(d).padStart(2,"0")}` });
  }
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div>
      <div className="grid grid-cols-7 gap-1 mb-1">
        {["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d => (
          <div key={d} style={{ fontSize: 9, color: "var(--text-4)", textAlign: "center", letterSpacing: "0.06em" }}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, i) => {
          if (!cell.day || !cell.dateStr) return <div key={i} className="aspect-square" />;
          const entry = dataMap[cell.dateStr];
          const pct = entry?.pnl_pct ?? 0;
          const isToday = cell.dateStr === new Date().toISOString().slice(0, 10);
          const isSelected = cell.dateStr === selectedDay;
          return (
            <div
              key={cell.dateStr}
              className="aspect-square flex flex-col items-center justify-center relative"
              style={{
                background: entry ? pnlCellBg(pct) : "rgba(255,255,255,0.02)",
                border: isSelected
                  ? "2px solid var(--accent)"
                  : isToday
                    ? "1px solid rgba(251,191,36,0.6)"
                    : "1px solid rgba(255,255,255,0.04)",
                borderRadius: 3,
                transition: "all 80ms",
                transform: hovered === cell.dateStr ? "scale(1.12)" : "scale(1)",
                cursor: entry ? "pointer" : "default",
              }}
              onMouseEnter={() => setHovered(cell.dateStr)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => entry ? setSelectedDay(isSelected ? null : cell.dateStr) : null}
            >
              <span style={{ fontSize: 9, color: entry ? "var(--text-1)" : "var(--text-4)", fontFamily: "var(--font-mono)", lineHeight: 1 }}>{cell.day}</span>
              {entry && (
                <span style={{ fontSize: 8, color: numColor(pct), fontFamily: "var(--font-mono)", lineHeight: 1.2 }}>
                  {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
                </span>
              )}
              {hovered === cell.dateStr && entry && (
                <div style={{
                  position: "absolute", zIndex: 50, bottom: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)",
                  background: "var(--surface)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 4,
                  padding: "6px 10px", whiteSpace: "nowrap", boxShadow: "0 4px 20px rgba(0,0,0,0.6)", pointerEvents: "none",
                }}>
                  <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>{cell.dateStr}</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: numColor(pct) }}>
                    {pct > 0 ? "+" : ""}{pct.toFixed(2)}%
                  </div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-1)" }}>
                    {entry.pnl >= 0 ? "+" : ""}₹{Math.abs(entry.pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </div>
                  <div style={{ fontSize: 9, color: "var(--text-4)", marginTop: 2 }}>Click to view trades</div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PnLTab() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [rangeStart, setRangeStart] = useState(monthStart(now.getFullYear(), now.getMonth() + 1));
  const [rangeEnd,   setRangeEnd]   = useState(monthEnd(now.getFullYear(), now.getMonth() + 1));
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const { data: calData = [] } = useJournalPnLCalendar(year, month);
  const { data: allData = [] } = useJournalPnLCalendar(year);

  // Fetch all journal trades for the day-detail panel
  const { data: allJournalTrades = [] } = useQuery<any[]>({
    queryKey: ["journal-trades-all"],
    queryFn: () => api.get<any[]>("/journal/trades"),
    staleTime: 60_000,
  });

  // Stats computed from journal calendar — no paper_trades dependency
  const winDays  = allData.filter(d => d.pnl > 0).length;
  const lossDays = allData.filter(d => d.pnl < 0).length;
  const totalPnl = allData.reduce((s, d) => s + d.pnl, 0);
  const totalPnlPct = allData.reduce((s, d) => s + d.pnl_pct, 0);
  const winPcts  = allData.filter(d => d.pnl > 0).map(d => d.pnl_pct);
  const lossPcts = allData.filter(d => d.pnl < 0).map(d => d.pnl_pct);
  const bestDay  = winPcts.length  > 0 ? Math.max(...winPcts)  : 0;
  const worstDay = lossPcts.length > 0 ? Math.min(...lossPcts) : 0;
  const avgWin   = winPcts.length  > 0 ? winPcts.reduce((s, v) => s + v, 0) / winPcts.length  : 0;
  const avgLoss  = lossPcts.length > 0 ? lossPcts.reduce((s, v) => s + v, 0) / lossPcts.length : 0;

  const monthlyData = useMemo(() => {
    const byMonth: Record<string, { pnl: number; pnl_pct: number }> = {};
    allData.forEach(d => {
      const key = d.date.slice(0, 7);
      if (!byMonth[key]) byMonth[key] = { pnl: 0, pnl_pct: 0 };
      byMonth[key].pnl += d.pnl;
      byMonth[key].pnl_pct += d.pnl_pct;
    });
    return Object.entries(byMonth)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, v]) => ({ month: MONTHS[parseInt(key.slice(5)) - 1], ...v }));
  }, [allData]);

  const prevMonth = () => {
    const newYear  = month === 1  ? year - 1 : year;
    const newMonth = month === 1  ? 12       : month - 1;
    setYear(newYear); setMonth(newMonth);
    setRangeStart(monthStart(newYear, newMonth));
    setRangeEnd(monthEnd(newYear, newMonth));
  };
  const nextMonth = () => {
    const newYear  = month === 12 ? year + 1 : year;
    const newMonth = month === 12 ? 1        : month + 1;
    setYear(newYear); setMonth(newMonth);
    setRangeStart(monthStart(newYear, newMonth));
    setRangeEnd(monthEnd(newYear, newMonth));
  };

  const filteredCalData = calData.filter(d => {
    const date = d.date.slice(0, 10);
    return date >= rangeStart && date <= rangeEnd;
  });

  const monthPnL    = filteredCalData.reduce((s, d) => s + d.pnl, 0);
  const monthPnLPct = filteredCalData.reduce((s, d) => s + d.pnl_pct, 0);
  const monthWins   = filteredCalData.filter(d => d.pnl > 0).length;
  const monthLoss   = filteredCalData.filter(d => d.pnl < 0).length;

  const statPanels = [
    { label: "TOTAL P&L",  value: totalPnl !== 0 ? formatCurrency(totalPnl, true) : "—", sub: totalPnlPct !== 0 ? `${totalPnlPct >= 0 ? "+" : ""}${totalPnlPct.toFixed(2)}% overall` : "from journal trades", color: numColor(totalPnl), icon: TrendingUp },
    { label: "WIN DAYS",   value: allData.length > 0 ? String(winDays)  : "—", sub: allData.length > 0 ? `${lossDays} losing` : "no closed trades", color: "var(--green)", icon: Target },
    { label: "BEST DAY",   value: bestDay  !== 0 ? `+${bestDay.toFixed(2)}%`  : "—", color: "var(--green)", icon: Flame },
    { label: "WORST DAY",  value: worstDay !== 0 ? `${worstDay.toFixed(2)}%`  : "—", color: "var(--red)",   icon: TrendingDown },
    { label: "AVG WIN",    value: avgWin   !== 0 ? `+${avgWin.toFixed(2)}%`   : "—", color: "var(--green)" },
    { label: "AVG LOSS",   value: avgLoss  !== 0 ? `${avgLoss.toFixed(2)}%`   : "—", color: "var(--red)" },
  ];

  return (
    <div className="space-y-4">
      {/* Stat row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {statPanels.map((p, i) => (
          <motion.div key={p.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="card p-3">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "var(--font-body)", fontWeight: 700 }}>{p.label}</span>
              {p.icon && <p.icon style={{ width: 11, height: 11, color: "var(--text-4)" }} />}
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 18, color: p.color ?? "var(--text-1)", lineHeight: 1 }}>{p.value}</div>
            {p.sub && <div style={{ fontSize: 10, color: "var(--text-4)", marginTop: 4 }}>{p.sub}</div>}
          </motion.div>
        ))}
      </div>

      {/* Calendar + Monthly chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Calendar */}
        <div className="lg:col-span-2 card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <CalendarDays style={{ width: 12, height: 12, color: "var(--amber)" }} />
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-1)", fontFamily: "var(--font-body)" }}>P&L CALENDAR</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: numColor(monthPnL) }}>
                {monthPnL >= 0 ? "+" : ""}₹{Math.abs(monthPnL).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </span>
              <button onClick={prevMonth} style={{ padding: 4, borderRadius: 6, background: "transparent", border: "none", color: "var(--text-3)", cursor: "pointer" }}><ChevronLeft style={{ width: 12, height: 12 }} /></button>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-1)", minWidth: 64, textAlign: "center" }}>{MONTHS[month - 1]} {year}</span>
              <button onClick={nextMonth} style={{ padding: 4, borderRadius: 6, background: "transparent", border: "none", color: "var(--text-3)", cursor: "pointer" }}><ChevronRight style={{ width: 12, height: 12 }} /></button>
            </div>
          </div>

          {/* Month quick-select */}
          <div style={{ padding: "10px 16px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
              {MONTHS.map((label, idx) => {
                const m = idx + 1;
                const isActive = m === month;
                return (
                  <button key={label} onClick={() => { setMonth(m); setRangeStart(monthStart(year, m)); setRangeEnd(monthEnd(year, m)); }} style={{
                    fontSize: 9, fontFamily: "var(--font-mono)", padding: "3px 7px", borderRadius: 3, cursor: "pointer",
                    border: isActive ? "1px solid rgba(39,174,96,0.5)" : "1px solid rgba(39,174,96,0.12)",
                    background: isActive ? "rgba(39,174,96,0.12)" : "rgba(39,174,96,0.02)",
                    color: isActive ? "var(--accent)" : "var(--text-4)", transition: "all 80ms",
                  }}>{label}</button>
                );
              })}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, paddingBottom: 10 }}>
              {["FROM","TO"].map((label, i) => (
                <React.Fragment key={label}>
                  <span style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-mono)", letterSpacing: "0.06em" }}>{label}</span>
                  <input type="date" value={i === 0 ? rangeStart : rangeEnd}
                    onChange={e => i === 0 ? setRangeStart(e.target.value) : setRangeEnd(e.target.value)}
                    style={{ background: "rgba(39,174,96,0.03)", border: "1px solid var(--accent-border)", color: "var(--text-1)", fontFamily: "var(--font-mono)", borderRadius: 4, padding: "5px 8px", outline: "none", fontSize: 11 }}
                  />
                </React.Fragment>
              ))}
              <span style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-mono)", marginLeft: 4 }}>
                {filteredCalData.length} trading day{filteredCalData.length !== 1 ? "s" : ""}
              </span>
            </div>
          </div>

          <div style={{ padding: 16 }}>
            <CalendarHeatmap
              year={year}
              month={month}
              data={filteredCalData}
              selectedDay={selectedDay}
              setSelectedDay={setSelectedDay}
            />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              {[
                { label: "MONTH P&L", val: `${monthPnL >= 0 ? "+" : ""}${monthPnLPct.toFixed(2)}%`, color: numColor(monthPnL) },
                { label: "WIN DAYS",  val: String(monthWins), color: "var(--green)" },
                { label: "LOSS DAYS", val: String(monthLoss), color: "var(--red)" },
                { label: "WIN RATE",  val: `${monthWins + monthLoss ? ((monthWins / (monthWins + monthLoss)) * 100).toFixed(0) : "—"}%`, color: "var(--text-1)" },
              ].map(item => (
                <div key={item.label} style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "var(--font-body)", fontWeight: 700 }}>{item.label}</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 15, color: item.color, marginTop: 4 }}>{item.val}</div>
                </div>
              ))}
            </div>

            {/* ── Day trades panel ── */}
            {selectedDay && (() => {
              const dayTrades = allJournalTrades.filter((t: any) => {
                const exitDate = t.exit_date ?? t.exitDate ?? null;
                return exitDate && exitDate.slice(0, 10) === selectedDay;
              });
              return (
                <div style={{
                  marginTop: 16, padding: "12px 14px",
                  background: "var(--surface-2)", border: "1px solid var(--accent-border)",
                  borderRadius: 8,
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-body)", letterSpacing: "0.06em" }}>
                      Trades closed on {selectedDay}
                    </span>
                    <button
                      onClick={() => setSelectedDay(null)}
                      style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--text-3)", display: "flex", alignItems: "center" }}
                    >
                      <X style={{ width: 13, height: 13 }} />
                    </button>
                  </div>
                  {dayTrades.length === 0 ? (
                    <div style={{ fontSize: 12, color: "var(--text-4)", padding: "8px 0" }}>
                      No trades closed on this date
                    </div>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                        <thead>
                          <tr>
                            {["SYMBOL", "BUY ₹", "SELL ₹", "QTY", "P&L", "P&L%"].map((h, i) => (
                              <th key={h} style={{
                                padding: "5px 10px", textAlign: i >= 1 ? "right" : "left",
                                fontSize: 9, fontWeight: 700, letterSpacing: "0.08em",
                                color: "var(--text-3)", borderBottom: "1px solid rgba(255,255,255,0.06)",
                                fontFamily: "var(--font-body)", whiteSpace: "nowrap",
                              }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {dayTrades.map((t: any, i: number) => {
                            const symbol      = t.stockName ?? t.stock_name ?? t.ticker ?? "—";
                            const buyPrice    = t.buyPrice  ?? t.buy_price  ?? 0;
                            const sellPrice   = t.sellPrice ?? t.sell_price ?? 0;
                            const qty         = t.quantity  ?? t.qty        ?? 0;
                            const pnl         = t.brokerPl  ?? t.broker_pl  ?? ((sellPrice - buyPrice) * qty);
                            const pct         = buyPrice > 0 ? ((sellPrice - buyPrice) / buyPrice) * 100 : 0;
                            const pnlPos      = pnl >= 0;
                            return (
                              <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)" }}>
                                <td style={{ padding: "5px 10px", fontWeight: 700, color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                                  {symbol}
                                </td>
                                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--text-2)" }}>
                                  ₹{buyPrice.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </td>
                                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--text-2)" }}>
                                  {sellPrice ? `₹${sellPrice.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                                </td>
                                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", color: "var(--text-2)" }}>
                                  {qty.toLocaleString("en-IN")}
                                </td>
                                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 700, color: pnlPos ? "var(--green)" : "var(--red)" }}>
                                  {pnlPos ? "+" : ""}₹{Math.abs(pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                                </td>
                                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 700, color: pnlPos ? "var(--green)" : "var(--red)" }}>
                                  {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>

        {/* Monthly bar + equity curve */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card p-4">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <BarChart2 style={{ width: 11, height: 11, color: "var(--amber)" }} />
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-1)", fontFamily: "var(--font-body)" }}>MONTHLY P&L {year}</span>
            </div>
            {monthlyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={monthlyData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 9, fill: "var(--text-4)" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: "var(--text-4)" }} axisLine={false} tickLine={false} tickFormatter={v => `${v}%`} />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.08)" />
                  <ReTip contentStyle={{ background: "var(--surface)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 4, fontSize: 11, fontFamily: "var(--font-mono)" }}
                    formatter={(v: number) => [`${v.toFixed(2)}%`, "Monthly P&L"]} labelStyle={{ color: "var(--text-3)", fontSize: 10 }} />
                  <Bar dataKey="pnl_pct" radius={[2, 2, 0, 0]} maxBarSize={28}>
                    {monthlyData.map((d, i) => <Cell key={i} fill={d.pnl_pct >= 0 ? "var(--green)" : "var(--red)"} fillOpacity={0.8} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: 140, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontSize: 12, color: "var(--text-4)" }}>No journal trades closed yet</span>
              </div>
            )}
          </div>

          <div className="card p-4">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <TrendingUp style={{ width: 11, height: 11, color: "var(--amber)" }} />
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-1)", fontFamily: "var(--font-body)" }}>NAV CURVE {year}</span>
            </div>
            {allData.length > 1 ? (
              <ResponsiveContainer width="100%" height={110}>
                <AreaChart data={allData} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="navGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--green)" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="var(--green)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 9, fill: "var(--text-4)" }} axisLine={false} tickLine={false}
                    tickFormatter={v => v.slice(5)} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 9, fill: "var(--text-4)" }} axisLine={false} tickLine={false}
                    tickFormatter={v => `₹${(v / 1000).toFixed(0)}K`} width={44} />
                  <ReTip contentStyle={{ background: "var(--surface)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 4, fontSize: 11, fontFamily: "var(--font-mono)" }}
                    formatter={(v: number) => [`₹${v.toLocaleString("en-IN")}`, "Portfolio"]} labelStyle={{ color: "var(--text-3)", fontSize: 10 }} />
                  <Area type="monotone" dataKey="portfolio_value" stroke="var(--green)" strokeWidth={1.5} fill="url(#navGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : <div className="skeleton" style={{ height: 110 }} />}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── TRADES TAB ────────────────────────────────────────────────────────────────
type TradeSortKey = "ticker" | "strategy" | "entry_date" | "entry_price" | "pnl" | "pnl_pct" | "status";

function SortBtn({ col, current, dir, onSort }: { col: TradeSortKey; current: TradeSortKey; dir: "asc" | "desc"; onSort: (k: TradeSortKey) => void }) {
  const active = col === current;
  return (
    <button onClick={() => onSort(col)} style={{ display: "inline-flex", alignItems: "center", gap: 3, cursor: "pointer", background: "none", border: "none", color: active ? "var(--accent)" : "var(--text-4)", fontFamily: "var(--font-body)", fontSize: "inherit", fontWeight: "inherit", letterSpacing: "inherit", padding: 0 }}>
      {col === "ticker" ? "TICKER" : col === "strategy" ? "STRATEGY" : col === "entry_date" ? "ENTRY" : col === "entry_price" ? "ENTRY ₹" : col === "pnl" ? "P&L" : col === "pnl_pct" ? "RET%" : "STATUS"}
      <span style={{ fontSize: 8, lineHeight: 1 }}>{active ? (dir === "asc" ? "▲" : "▼") : "⇅"}</span>
    </button>
  );
}

function TradesTab() {
  const [statusFilter, setStatusFilter] = useState<"all" | "OPEN" | "CLOSED">("all");
  const [sortKey, setSortKey] = useState<TradeSortKey>("entry_date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const { data: trades, isLoading } = usePaperTrades(statusFilter);
  const { data: strategyStats }     = useStrategyPnl();

  const allTrades = trades ?? [];

  const totalPnl = allTrades.reduce((s, t) => s + (t.pnl ?? 0), 0);
  const closed   = allTrades.filter(t => t.status?.toUpperCase() === "CLOSED");
  const open     = allTrades.filter(t => t.status?.toUpperCase() === "OPEN");
  const wins     = closed.filter(t => (t.pnl ?? 0) > 0);
  const winRate  = closed.length > 0 ? ((wins.length / closed.length) * 100).toFixed(0) : "—";

  const handleSort = (key: TradeSortKey) => {
    if (key === sortKey) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  const filtered = [...allTrades]
    .filter(t => {
      const d = t.entry_date?.slice(0, 10) ?? "";
      if (fromDate && d < fromDate) return false;
      if (toDate && d > toDate) return false;
      return true;
    })
    .sort((a, b) => {
    let av: string | number = 0, bv: string | number = 0;
    if (sortKey === "ticker")       { av = a.ticker; bv = b.ticker; }
    else if (sortKey === "strategy") { av = a.strategy; bv = b.strategy; }
    else if (sortKey === "entry_date") { av = a.entry_date; bv = b.entry_date; }
    else if (sortKey === "entry_price") { av = a.entry_price ?? 0; bv = b.entry_price ?? 0; }
    else if (sortKey === "pnl")     { av = a.pnl ?? 0; bv = b.pnl ?? 0; }
    else if (sortKey === "pnl_pct") { av = a.pnl_pct ?? 0; bv = b.pnl_pct ?? 0; }
    else if (sortKey === "status")  { av = a.status ?? ""; bv = b.status ?? ""; }
    if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(String(bv)) : String(bv).localeCompare(av);
    return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
  });

  return (
    <div className="space-y-4">
      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Trades"  value={allTrades.length}          subValue={`${open.length} open`}       delay={0}    />
        <StatCard label="Closed Trades" value={closed.length}             subValue={`Win rate: ${winRate}%`}     delay={0.05} variant="default" />
        <StatCard label="Winners"       value={wins.length}               subValue={`Losers: ${closed.length - wins.length}`} delay={0.1} variant="success" />
        <StatCard label="Total P&L"     value={formatCurrency(totalPnl)}  subValue={totalPnl >= 0 ? "Net profit" : "Net loss"}
          delay={0.15} variant={totalPnl >= 0 ? "success" : "danger"} />
      </div>

      {/* Strategy P&L breakdown */}
      {(strategyStats ?? []).length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card p-5">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-1)", fontFamily: "var(--font-body)" }}>STRATEGY P&L BREAKDOWN</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10 }}>
            {(strategyStats ?? []).map(s => (
              <div key={s.strategy} style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 8, padding: "10px 12px" }}>
                <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-4)", fontFamily: "var(--font-body)", marginBottom: 6 }}>
                  {(STRATEGY_LABELS[s.strategy] ?? s.strategy).toUpperCase()}
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 700, color: s.total_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                  {s.total_pnl >= 0 ? "+" : ""}₹{Math.abs(s.total_pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                  <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>{s.closed_trades} closed</span>
                  <span style={{ fontSize: 10, color: s.win_rate >= 50 ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                    {s.win_rate}% WR
                  </span>
                </div>
                <div style={{ marginTop: 6, height: 3, borderRadius: 2, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${s.win_rate}%`, background: s.win_rate >= 50 ? "var(--green)" : "var(--red)", borderRadius: 2, transition: "width 600ms ease" }} />
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Paper trades table */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)", flexWrap: "wrap", gap: 8 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-1)", fontFamily: "var(--font-body)" }}>
              SCREENER AUTO-TRADES ({filtered.length})
            </span>
            <span style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
              Automated paper trades from the screener bot — not your journal trades
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {/* Date range filter */}
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              {(["From", "To"] as const).map((label, i) => (
                <input
                  key={label}
                  type="date"
                  value={i === 0 ? fromDate : toDate}
                  onChange={e => i === 0 ? setFromDate(e.target.value) : setToDate(e.target.value)}
                  title={label}
                  style={{
                    background: "rgba(39,174,96,0.04)", border: "1px solid var(--accent-border)",
                    color: "var(--text-1)", fontFamily: "var(--font-mono)",
                    borderRadius: 5, padding: "3px 7px", outline: "none", fontSize: 10,
                    colorScheme: "dark",
                  }}
                />
              ))}
              {(fromDate || toDate) && (
                <button onClick={() => { setFromDate(""); setToDate(""); }}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-4)", fontSize: 12, lineHeight: 1 }}>
                  ✕
                </button>
              )}
            </div>
            <div style={{ width: 1, height: 16, background: "rgba(255,255,255,0.08)" }} />
            {/* Status filters */}
            {(["all", "OPEN", "CLOSED"] as const).map(s => (
              <button key={s} onClick={() => setStatusFilter(s)} style={{
                fontSize: 10, padding: "3px 10px", borderRadius: 6, cursor: "pointer", transition: "all 120ms",
                background: statusFilter === s ? "rgba(39,174,96,0.08)" : "transparent",
                border: statusFilter === s ? "1px solid var(--accent-border)" : "1px solid transparent",
                color: statusFilter === s ? "var(--accent)" : "var(--text-3)", fontFamily: "var(--font-body)", fontWeight: 600,
              }}>{s === "all" ? "ALL" : s}</button>
            ))}
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                <th className="tbl-th" style={{ paddingLeft: 16 }}><SortBtn col="ticker"       current={sortKey} dir={sortDir} onSort={handleSort} /></th>
                <th className="tbl-th"><SortBtn col="strategy"    current={sortKey} dir={sortDir} onSort={handleSort} /></th>
                <th className="tbl-th"><SortBtn col="entry_date"  current={sortKey} dir={sortDir} onSort={handleSort} /></th>
                <th className="tbl-th-r"><SortBtn col="entry_price" current={sortKey} dir={sortDir} onSort={handleSort} /></th>
                <th className="tbl-th-r">TARGET ₹</th>
                <th className="tbl-th-r">SL ₹</th>
                <th className="tbl-th-r">EXIT ₹</th>
                <th className="tbl-th-r"><SortBtn col="pnl"       current={sortKey} dir={sortDir} onSort={handleSort} /></th>
                <th className="tbl-th-r"><SortBtn col="pnl_pct"   current={sortKey} dir={sortDir} onSort={handleSort} /></th>
                <th className="tbl-th"><SortBtn col="status"      current={sortKey} dir={sortDir} onSort={handleSort} /></th>
                <th className="tbl-th">NOTES</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? <SkeletonTable rows={8} /> : filtered.length === 0 ? (
                <tr><td colSpan={11} style={{ textAlign: "center", padding: "48px 20px", color: "var(--text-3)", fontSize: 13 }}>
                  No paper trades yet — screener will populate trades during market hours
                </td></tr>
              ) : filtered.map((t, i) => {
                const pnl = t.pnl ?? 0;
                const pct = t.pnl_pct ?? 0;
                const isOpen = t.status?.toUpperCase() === "OPEN";
                return (
                  <motion.tr key={`${t.ticker}-${t.entry_date}-${i}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.01 }} className="tbl-row">
                    <td className="tbl-cell" style={{ paddingLeft: 16, fontWeight: 700, color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                      {t.ticker}
                    </td>
                    <td className="tbl-cell">
                      <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-3)", fontFamily: "var(--font-body)", background: "rgba(255,255,255,0.04)", padding: "2px 6px", borderRadius: 4 }}>
                        {(STRATEGY_LABELS[t.strategy] ?? t.strategy).toUpperCase()}
                      </span>
                    </td>
                    <td className="tbl-cell" style={{ fontSize: 10, color: "var(--text-3)" }}>{t.entry_date?.slice(0,10)}</td>
                    <td className="tbl-cell-r">₹{t.entry_price?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                    <td className="tbl-cell-r" style={{ color: "var(--green)", fontSize: 11 }}>₹{t.target_price?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                    <td className="tbl-cell-r" style={{ color: "var(--red)", fontSize: 11 }}>₹{t.sl_price?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                    <td className="tbl-cell-r" style={{ color: "var(--text-2)" }}>{t.exit_price ? `₹${t.exit_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}</td>
                    <td className="tbl-cell-r" style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: isOpen ? "var(--text-3)" : pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                      {isOpen ? "OPEN" : `${pnl >= 0 ? "+" : ""}₹${Math.abs(pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                    </td>
                    <td className="tbl-cell-r" style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 11, color: isOpen ? "var(--text-3)" : pct >= 0 ? "var(--green)" : "var(--red)" }}>
                      {isOpen ? "—" : `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`}
                    </td>
                    <td className="tbl-cell">
                      <span style={{
                        fontSize: 9, fontWeight: 700, letterSpacing: "0.06em", padding: "2px 7px", borderRadius: 4,
                        fontFamily: "var(--font-body)",
                        background: isOpen ? "var(--amber-dim)" : pnl >= 0 ? "rgba(52,211,153,0.1)" : "rgba(248,113,113,0.1)",
                        color: isOpen ? "var(--amber)" : pnl >= 0 ? "var(--green)" : "var(--red)",
                        border: `1px solid ${isOpen ? "var(--amber-border)" : pnl >= 0 ? "rgba(52,211,153,0.2)" : "rgba(248,113,113,0.2)"}`,
                      }}>
                        {t.status?.toUpperCase()}
                      </span>
                    </td>
                    <td className="tbl-cell-muted" style={{ fontSize: 10, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.notes}</td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}

// ── LIVE TAB ──────────────────────────────────────────────────────────────────
function LiveTab() {
  const { data: live, connected, lastUpdate } = useLiveStore();
  const { data: ddHistory, isLoading: ddLoading } = useDrawdownHistory(90);
  const { data: orders, isLoading: ordersLoading } = useOrders("all", 20);

  const pnlPos = (live?.day_pnl_pct ?? 0) >= 0;

  return (
    <div className="space-y-4">
      {/* Connection status + big P&L */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="card p-6 flex flex-col items-center justify-center text-center" style={{ minHeight: 200 }}>
          {/* Pulse */}
          <div style={{ position: "relative", width: 40, height: 40, marginBottom: 12 }}>
            {connected && (
              <>
                <motion.div style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "rgba(39,174,96,0.15)" }}
                  animate={{ scale: [1, 2, 1], opacity: [0.5, 0, 0.5] }} transition={{ duration: 2, repeat: Infinity }} />
                <motion.div style={{ position: "absolute", inset: 4, borderRadius: "50%", background: "rgba(39,174,96,0.25)" }}
                  animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }} transition={{ duration: 2, repeat: Infinity, delay: 0.3 }} />
              </>
            )}
            <div style={{ position: "absolute", inset: 12, borderRadius: "50%", background: connected ? "var(--green)" : "var(--red)" }} />
          </div>

          <div style={{ fontSize: 12, fontWeight: 700, color: connected ? "var(--green)" : "var(--red)", marginBottom: 4, fontFamily: "var(--font-body)", letterSpacing: "0.1em" }}>
            {connected ? "LIVE FEED CONNECTED" : "RECONNECTING…"}
          </div>
          {lastUpdate && (
            <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-mono)" }}>
              Last update: {format(lastUpdate, "HH:mm:ss")}
            </div>
          )}
          {connected ? <Wifi style={{ width: 14, height: 14, color: "var(--green)", marginTop: 8 }} /> : <WifiOff style={{ width: 14, height: 14, color: "var(--red)", marginTop: 8 }} />}
        </motion.div>

        {/* Big day P&L */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
          className="card p-6 flex flex-col items-center justify-center text-center lg:col-span-2"
          style={{ background: pnlPos ? "rgba(39,174,96,0.03)" : "rgba(231,76,60,0.03)", border: pnlPos ? "1px solid rgba(39,174,96,0.12)" : "1px solid rgba(231,76,60,0.12)" }}>
          <div style={{ fontSize: 10, color: "var(--text-3)", letterSpacing: "0.12em", fontFamily: "var(--font-body)", marginBottom: 8 }}>TODAY'S P&L</div>
          <div style={{ fontSize: 52, fontWeight: 800, fontFamily: "var(--font-mono)", color: pnlPos ? "var(--green)" : "var(--red)", lineHeight: 1 }}>
            <AnimatedNumber value={live?.day_pnl_pct ?? 0} format={v => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`} />
          </div>
          <div style={{ fontSize: 16, fontFamily: "var(--font-mono)", color: pnlPos ? "var(--green)" : "var(--red)", marginTop: 8, opacity: 0.7 }}>
            {(live?.day_pnl ?? 0) >= 0 ? "+" : ""}₹{Math.abs(live?.day_pnl ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
          </div>
          <div style={{ display: "flex", gap: 32, marginTop: 20 }}>
            {[
              { label: "PORTFOLIO", val: formatCurrency(live?.portfolio_value ?? 0, true) },
              { label: "DRAWDOWN",  val: `${(live?.drawdown_pct ?? 0).toFixed(2)}%` },
              { label: "POSITIONS", val: String(live?.n_positions ?? 0) },
            ].map(item => (
              <div key={item.label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "var(--font-body)", fontWeight: 700 }}>{item.label}</div>
                <div style={{ fontSize: 14, fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-1)", marginTop: 2 }}>{item.val}</div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Drawdown chart */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-4">
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-1)", fontFamily: "var(--font-body)", marginBottom: 12 }}>DRAWDOWN (90d)</div>
        {ddLoading ? <div className="skeleton" style={{ height: 120 }} /> : <DrawdownChart data={ddHistory ?? []} height={120} />}
      </motion.div>

      {/* Recent orders */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="card">
        <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "var(--text-1)", fontFamily: "var(--font-body)" }}>RECENT ORDERS (20)</span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead>
              <tr>
                {["TICKER","SIDE","QTY","FILLED @","STATUS","STRATEGY","TIME"].map((h, i) => (
                  <th key={h} className={i >= 2 && i <= 3 ? "tbl-th-r" : "tbl-th"} style={{ paddingLeft: i === 0 ? 16 : undefined }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ordersLoading ? <SkeletonTable rows={5} /> : !orders?.length ? (
                <tr><td colSpan={7} style={{ textAlign: "center", padding: "32px 20px", color: "var(--text-3)", fontSize: 13 }}>No recent orders</td></tr>
              ) : (
                orders.slice(0, 20).map((o, i) => (
                  <motion.tr key={o.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }} className="tbl-row">
                    <td className="tbl-cell" style={{ paddingLeft: 16, fontWeight: 700, color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                      {o.ticker.replace(".NS","").replace(".BO","")}
                    </td>
                    <td className="tbl-cell"><SideBadge side={o.side} /></td>
                    <td className="tbl-cell-r">{o.quantity.toLocaleString("en-IN")}</td>
                    <td className="tbl-cell-r">{o.avg_fill_price ? `₹${o.avg_fill_price.toFixed(2)}` : "—"}</td>
                    <td className="tbl-cell"><OrderStatusBadge status={o.status} /></td>
                    <td className="tbl-cell-muted" style={{ fontSize: 10 }}>{STRATEGY_LABELS[o.strategy] ?? o.strategy}</td>
                    <td className="tbl-cell-r" style={{ fontSize: 10, color: "var(--text-3)" }}>{formatDateTime(o.created_at)}</td>
                  </motion.tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const MAIN_TABS: { key: MainTab; label: string }[] = [
  { key: "holdings", label: "HOLDINGS" },
  { key: "pnl",      label: "P&L" },
  { key: "trades",   label: "TRADES" },
  { key: "live",     label: "LIVE" },
];

const TAB_SUBTITLES: Record<MainTab, string> = {
  holdings: "Open positions & allocation",
  pnl:      "P&L calendar & performance stats",
  trades:   "Order history & execution analytics",
  live:     "Real-time feed & drawdown",
};

export function PortfolioPage() {
  const { equityCurveDays, setEquityCurveDays, openChart } = useUIStore();
  const [mainTab, setMainTab] = useState<MainTab>("holdings");

  const { data: summary, isLoading: summaryLoading } = useJournalSummary();

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Portfolio" subtitle={TAB_SUBTITLES[mainTab]} />

      <div className="flex-1 overflow-y-auto">
        {/* Main tab bar */}
        <div style={{
          display: "flex", alignItems: "center", gap: 2,
          padding: "8px 16px 0",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}>
          {MAIN_TABS.map(t => {
            const active = mainTab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setMainTab(t.key)}
                style={{
                  padding: "8px 20px", fontSize: 11, fontWeight: 700, fontFamily: "var(--font-body)",
                  letterSpacing: "0.1em", cursor: "pointer", border: "none", background: "transparent",
                  color: active ? "var(--accent)" : "var(--text-3)", transition: "all 150ms",
                  borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: -1,
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="p-4 space-y-4">
          {/* KPI row — always visible */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {summaryLoading ? (
              Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
            ) : (
              <>
                <StatCard label="Live NAV" icon={<DollarSign className="w-4 h-4" />} delay={0}
                  value={<AnimatedNumber value={summary?.nav ?? 0} format={v => formatCurrency(v, true)} />}
                  subValue={`Realized: ${formatCurrency(summary?.realized_pnl ?? 0, true)}`}
                />
                <StatCard label="Day P&L" icon={<Activity className="w-4 h-4" />} delay={0.05}
                  variant={(summary?.day_pnl_pct ?? 0) >= 0 ? "success" : (summary?.day_pnl_pct ?? 0) < -1 ? "danger" : "default"}
                  value={<span className={pctColor(summary?.day_pnl_pct ?? 0)}><AnimatedNumber value={summary?.day_pnl_pct ?? 0} format={v => formatPct(v)} /></span>}
                  subValue={formatCurrency(summary?.day_pnl ?? 0, true)}
                />
                <StatCard label="Drawdown" icon={<TrendingDown className="w-4 h-4" />} delay={0.1}
                  variant={(summary?.drawdown ?? 0) > 8 ? "danger" : (summary?.drawdown ?? 0) > 5 ? "warning" : "default"}
                  value={<span style={{ color: "var(--red)" }}><AnimatedNumber value={-(summary?.drawdown ?? 0)} format={v => formatPct(v)} /></span>}
                  subValue="from peak"
                />
                <StatCard label="Positions" icon={<Layers className="w-4 h-4" />} delay={0.15}
                  value={summary?.open_positions ?? 0}
                  subValue={`Invested: ${formatCurrency(summary?.total_invested ?? 0, true)}`}
                />
              </>
            )}
          </div>

          {/* Tab content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={mainTab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              {mainTab === "holdings" && (
                <HoldingsTab
                  equityCurveDays={equityCurveDays}
                  setEquityCurveDays={setEquityCurveDays}
                  openChart={openChart}
                />
              )}
              {mainTab === "pnl"      && <PnLTab />}
              {mainTab === "trades"   && <TradesTab />}
              {mainTab === "live"     && <LiveTab />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
