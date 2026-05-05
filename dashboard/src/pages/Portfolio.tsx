import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  DollarSign, TrendingDown, Layers, Activity,
  Plus, Trash2, LogOut, BarChart3, TrendingUp,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { StatCard } from "@/components/ui/StatCard";
import { EquityChart } from "@/components/charts/EquityChart";
import { SectorPieChart } from "@/components/charts/SectorPieChart";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { AddPositionModal } from "@/components/ui/AddPositionModal";
import { ExitPositionModal } from "@/components/ui/ExitPositionModal";
import {
  usePortfolioSummary,
  usePositions,
  useSectorExposure,
  useEquityCurve,
} from "@/api/queries";
import {
  usePaperPositions,
  useDeletePaperPosition,
  useLivePositions,
  useDeleteLivePosition,
  type PaperPosition,
} from "@/api/pnl-queries";
import { formatCurrency, formatPct, pctColor } from "@/lib/utils";
import { useUIStore } from "@/store/ui";

const DAYS_OPTIONS = [30, 90, 252, 756] as const;
type Tab = "paper" | "live";

function PnlChip({ v }: { v: number }) {
  const pos = v >= 0;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      fontFamily: "JetBrains Mono, monospace", fontSize: 11.5, fontWeight: 700,
      color: pos ? "var(--green)" : "var(--red)",
    }}>
      {pos ? <TrendingUp style={{ width: 10, height: 10 }} /> : <TrendingDown style={{ width: 10, height: 10 }} />}
      {pos ? "+" : ""}{v.toFixed(2)}%
    </span>
  );
}

function TabBtn({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 18px", borderRadius: 8, fontSize: 11, fontWeight: 700,
        fontFamily: "var(--font-body)", letterSpacing: "0.1em",
        cursor: "pointer", transition: "all 150ms",
        background: active ? "linear-gradient(135deg, var(--blue-dim), transparent)" : "transparent",
        border: active ? "1px solid var(--border-blue)" : "1px solid transparent",
        color: active ? "#5B7FFF" : "var(--text-3)",
      }}
    >
      {label}
    </button>
  );
}

export function PortfolioPage() {
  const { equityCurveDays, setEquityCurveDays, openChart } = useUIStore();
  const [addOpen, setAddOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("paper");
  const [exitTarget, setExitTarget] = useState<PaperPosition | null>(null);
  const [exitOpen, setExitOpen] = useState(false);

  const { data: summary, isLoading: summaryLoading } = usePortfolioSummary();
  const { data: sectors } = useSectorExposure();
  const { data: equity, isLoading: equityLoading } = useEquityCurve(equityCurveDays);
  const { data: paperPositions, isLoading: paperLoading } = usePaperPositions();
  const { data: livePositions, isLoading: liveLoading } = useLivePositions();
  const deletePaper = useDeletePaperPosition();
  const deleteLive = useDeleteLivePosition();

  // Suppress unused warning – positions used by summary KPIs
  usePositions();

  const activePositions: PaperPosition[] = tab === "paper" ? (paperPositions ?? []) : (livePositions ?? []);
  const activeLoading = tab === "paper" ? paperLoading : liveLoading;

  const totalCost  = activePositions.reduce((s, p) => s + p.quantity * p.avg_buy_price, 0);
  const totalValue = activePositions.reduce((s, p) => s + p.quantity * (p.current_price ?? p.avg_buy_price), 0);
  const unrealPnl  = totalValue - totalCost;
  const unrealPct  = totalCost > 0 ? (unrealPnl / totalCost) * 100 : 0;
  const pnlColor   = unrealPnl >= 0 ? "var(--green)" : "var(--red)";

  const handleDelete = (ticker: string) => {
    if (tab === "paper") deletePaper.mutate(ticker);
    else deleteLive.mutate(ticker);
  };

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Portfolio" subtitle={tab === "paper" ? "Paper Trading" : "Live Positions"} />

      <AddPositionModal open={addOpen} onClose={() => setAddOpen(false)} mode={tab} />
      <ExitPositionModal
        open={exitOpen}
        position={exitTarget}
        mode={tab}
        onClose={() => { setExitOpen(false); setExitTarget(null); }}
      />

      <div className="flex-1 p-4 space-y-4 overflow-y-auto">

        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {summaryLoading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
              <StatCard label="Portfolio Value" icon={<DollarSign className="w-4 h-4" />} delay={0}
                value={<AnimatedNumber value={summary?.portfolio_value ?? 0} format={v => formatCurrency(v, true)} />}
                subValue={`Cash: ${formatCurrency(summary?.cash ?? 0, true)}`}
              />
              <StatCard label="Day P&L" icon={<Activity className="w-4 h-4" />} delay={0.05}
                variant={(summary?.day_pnl_pct ?? 0) >= 0 ? "success" : (summary?.day_pnl_pct ?? 0) < -1 ? "danger" : "default"}
                value={<span className={pctColor(summary?.day_pnl_pct ?? 0)}><AnimatedNumber value={summary?.day_pnl_pct ?? 0} format={v => formatPct(v)} /></span>}
                subValue={formatCurrency(summary?.day_pnl ?? 0, true)}
              />
              <StatCard label="Drawdown" icon={<TrendingDown className="w-4 h-4" />} delay={0.1}
                variant={(summary?.drawdown_pct ?? 0) > 8 ? "danger" : (summary?.drawdown_pct ?? 0) > 5 ? "warning" : "default"}
                value={<span style={{ color: "var(--red)" }}><AnimatedNumber value={-(summary?.drawdown_pct ?? 0)} format={v => formatPct(v)} /></span>}
                subValue="from peak"
              />
              <StatCard label="Positions" icon={<Layers className="w-4 h-4" />} delay={0.15}
                value={summary?.n_positions ?? 0}
                subValue={`Invested: ${formatCurrency(summary?.invested ?? 0, true)}`}
              />
            </>
          )}
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 card p-4">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)", letterSpacing: "0.08em", fontFamily: "var(--font-body)" }}>EQUITY CURVE</span>
              <div style={{ display: "flex", gap: 4 }}>
                {DAYS_OPTIONS.map(d => (
                  <button key={d} onClick={() => setEquityCurveDays(d)} style={{
                    fontSize: 10, padding: "2px 8px", borderRadius: 6, cursor: "pointer",
                    background: equityCurveDays === d ? "var(--blue-dim)" : "transparent",
                    border: equityCurveDays === d ? "1px solid var(--border-blue)" : "1px solid transparent",
                    color: equityCurveDays === d ? "#5B7FFF" : "var(--text-3)",
                    fontFamily: "var(--font-body)", fontWeight: 600,
                  }}>
                    {d === 252 ? "1Y" : d === 756 ? "3Y" : d === 90 ? "3M" : "1M"}
                  </button>
                ))}
              </div>
            </div>
            {equityLoading
              ? <div style={{ height: 180, background: "var(--blue-dim)", borderRadius: 8 }} />
              : <EquityChart data={equity ?? []} height={180} />
            }
          </div>
          <div className="card p-4">
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)", letterSpacing: "0.08em", display: "block", marginBottom: 12, fontFamily: "var(--font-body)" }}>SECTOR EXPOSURE</span>
            <SectorPieChart data={sectors ?? []} />
          </div>
        </div>

        {/* Positions table */}
        <motion.div className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)", flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <TabBtn active={tab === "paper"} label="PAPER" onClick={() => setTab("paper")} />
              <TabBtn active={tab === "live"}  label="LIVE"  onClick={() => setTab("live")} />
              {activePositions.length > 0 && (
                <span style={{ fontSize: 10, color: "var(--text-3)", marginLeft: 6, fontFamily: "JetBrains Mono, monospace" }}>
                  {activePositions.length} pos
                </span>
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              {/* Inline P&L summary */}
              {activePositions.length > 0 && (
                <>
                  <div>
                    <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "var(--font-body)" }}>INVESTED</div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: "var(--text-1)" }}>
                      ₹{(totalCost / 1e5).toFixed(2)}L
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "var(--font-body)" }}>UNREALISED P&L</div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: pnlColor, fontWeight: 700 }}>
                      {unrealPnl >= 0 ? "+" : ""}₹{Math.abs(unrealPnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "var(--font-body)" }}>RETURN</div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: pnlColor, fontWeight: 700 }}>
                      {unrealPct >= 0 ? "+" : ""}{unrealPct.toFixed(2)}%
                    </div>
                  </div>
                </>
              )}
              <button
                onClick={() => setAddOpen(true)}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "7px 14px", borderRadius: 8, fontSize: 11, fontWeight: 700,
                  fontFamily: "var(--font-body)", cursor: "pointer",
                  background: tab === "live"
                    ? "linear-gradient(135deg, rgba(6,214,160,0.2), rgba(6,214,160,0.05))"
                    : "linear-gradient(135deg, var(--blue-dim), transparent)",
                  border: tab === "live" ? "1px solid rgba(6,214,160,0.4)" : "1px solid var(--border-blue)",
                  color: tab === "live" ? "var(--green)" : "var(--blue)",
                }}
              >
                <Plus style={{ width: 12, height: 12 }} />
                Add Position
              </button>
            </div>
          </div>

          {/* Table */}
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  {["SYMBOL", "NAME", "SECTOR", "QTY", "AVG BUY", "CMP", "DAYS", "P&L", "RET%", "WT%", "ACTIONS"].map((h, i) => (
                    <th key={h} className={i >= 3 ? "tbl-th-r" : "tbl-th"} style={{ paddingLeft: i === 0 ? 20 : undefined }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {activeLoading ? (
                    Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i} className="tbl-row">
                        {Array.from({ length: 11 }).map((_, j) => (
                          <td key={j} className="tbl-cell">
                            <div style={{ height: 11, borderRadius: 4, background: "rgba(91,127,255,0.5)", width: [80, 130, 70, 40, 70, 70, 40, 70, 60, 50, 80][j] }} />
                          </td>
                        ))}
                      </tr>
                    ))
                  ) : activePositions.length === 0 ? (
                    <tr>
                      <td colSpan={11} style={{ textAlign: "center", padding: "48px 20px" }}>
                        <div style={{ color: "var(--text-3)", fontSize: 13, marginBottom: 12 }}>
                          No {tab === "paper" ? "paper trading" : "live"} positions yet
                        </div>
                        <button
                          onClick={() => setAddOpen(true)}
                          style={{
                            display: "inline-flex", alignItems: "center", gap: 6,
                            padding: "8px 20px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                            fontFamily: "var(--font-body)", cursor: "pointer",
                            background: "rgba(91,127,255,0.08)", border: "1px solid rgba(91,127,255,0.3)", color: "var(--blue)",
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
                          key={pos.ticker}
                          className="tbl-row"
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: 8 }}
                          transition={{ delay: idx * 0.03 }}
                        >
                          <td className="tbl-cell" style={{ paddingLeft: 20 }}>
                            <span style={{ fontWeight: 700, color: "var(--blue)", fontSize: 12, fontFamily: "JetBrains Mono, monospace" }}>
                              {sym}
                            </span>
                          </td>
                          <td className="tbl-cell-muted" style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {pos.name ?? "—"}
                          </td>
                          <td className="tbl-cell" style={{ textAlign: "left" }}>
                            {pos.sector ? (
                              <span style={{
                                fontSize: 9, padding: "2px 7px", borderRadius: 10, whiteSpace: "nowrap",
                                background: "rgba(129,140,248,0.1)", border: "1px solid rgba(129,140,248,0.22)",
                                color: "#818CF8", fontFamily: "var(--font-body)", fontWeight: 600,
                              }}>{pos.sector}</span>
                            ) : "—"}
                          </td>
                          <td className="tbl-cell-r">{pos.quantity}</td>
                          <td className="tbl-cell-r">₹{pos.avg_buy_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                          <td className="tbl-cell-r" style={{ color: "var(--text-1)", fontWeight: 600 }}>
                            ₹{cmp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                          <td className="tbl-cell-r" style={{ color: "#A0A0BC" }}>{pos.days_held ?? 0}d</td>
                          <td className="tbl-cell-r" style={{ color: pnlPos ? "var(--green)" : "var(--red)", fontWeight: 700 }}>
                            {pnlPos ? "+" : ""}₹{Math.abs(pos.unrealized_pnl ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                          </td>
                          <td className="tbl-cell-r">
                            <PnlChip v={pos.pnl_pct ?? 0} />
                          </td>
                          <td className="tbl-cell-r" style={{ color: "#A0A0BC" }}>
                            {(pos.weight ?? 0).toFixed(1)}%
                          </td>
                          <td className="tbl-cell row-actions" style={{ paddingRight: 16, textAlign: "right" }}>
                            <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                              <button
                                title="Open Chart"
                                onClick={() => openChart(sym, pos.name ?? sym)}
                                style={{ padding: "4px 6px", borderRadius: 6, background: "rgba(91,127,255,0.1)", border: "1px solid var(--blue-dim)", color: "var(--blue)", cursor: "pointer" }}
                              >
                                <BarChart3 style={{ width: 11, height: 11 }} />
                              </button>
                              <button
                                title="Exit Position"
                                onClick={() => { setExitTarget(pos); setExitOpen(true); }}
                                style={{ padding: "4px 6px", borderRadius: 6, background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.25)", color: "#FBBF24", cursor: "pointer" }}
                              >
                                <LogOut style={{ width: 11, height: 11 }} />
                              </button>
                              <button
                                title="Delete Position"
                                onClick={() => handleDelete(pos.ticker)}
                                style={{ padding: "4px 6px", borderRadius: 6, background: "rgba(255,71,87,0.1)", border: "1px solid rgba(255,71,87,0.2)", color: "var(--red)", cursor: "pointer" }}
                              >
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

      </div>
    </div>
  );
}
