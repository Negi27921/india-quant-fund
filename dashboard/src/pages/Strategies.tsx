import { useState } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp, TrendingDown, Zap, Activity, Target,
  Filter, ExternalLink, CheckCircle, XCircle,
} from "lucide-react";
import { Tooltip } from "@/components/ui/Tooltip";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { Skeleton, SkeletonCard, SkeletonTable } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import {
  useStrategyPerformance,
  useSignals,
  useStrategyAllocation,
} from "@/api/queries";
import { formatPct, formatDate } from "@/lib/utils";
import { STRATEGY_COLORS, STRATEGY_LABELS } from "@/lib/constants";
import { NSE_STOCKS } from "@/lib/nse-stocks";
import { useUIStore } from "@/store/ui";

const SIGNAL_DAYS = [1, 3, 5, 10] as const;

const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  vcp:          "Volatility contraction into tight base — Minervini SEPA",
  ipo_base:     "First consolidation after IPO listing pop",
  rocket_base:  "Post-explosive-move base after 60%+ rocket move",
  breakout:     "52-week high breakout with volume surge confirmation",
  rsi_reversal: "Oversold bounce with positive divergence signal",
  golden_cross: "EMA20 crosses above EMA50, fresh cross ≤10 bars",
  multibagger:  "Reverse-engineered from 16 FY2026 multi-baggers",
};

const STRATEGY_STOCK_MAP: Record<string, string[]> = {
  vcp:          ["IT", "Defence", "Industrials", "Healthcare", "Finance"],
  ipo_base:     ["IT", "Finance", "Consumer", "Healthcare"],
  rocket_base:  ["Defence", "Energy", "Industrials", "Metals"],
  breakout:     ["IT", "Banking", "Finance", "Auto", "Energy"],
  rsi_reversal: ["FMCG", "Healthcare", "Materials", "Consumer"],
  golden_cross: ["IT", "Finance", "Banking", "Auto"],
  multibagger:  ["Defence", "Power", "Railways", "IT", "Finance"],
};

// Example signals shown in the empty state
const EXAMPLE_SIGNALS = [
  { date: "2026-05-02", ticker: "RVNL",     strategy: "vcp",          signal: 1,  approved: true,  rejection_reason: undefined },
  { date: "2026-05-02", ticker: "INFY",     strategy: "breakout",     signal: 1,  approved: false, rejection_reason: "Kill switch active" },
  { date: "2026-05-01", ticker: "HDFCBANK", strategy: "golden_cross", signal: 1,  approved: true,  rejection_reason: undefined },
];

// ── Strategy Allocation horizontal bar chart ───────────────────────────────────
function AllocationBars({
  allocation,
  perf,
  loading,
  selectedStrategy,
  onSelect,
}: {
  allocation: { strategy: string; weight: number }[] | undefined;
  perf: { strategy: string; sharpe_ratio: number }[] | undefined;
  loading: boolean;
  selectedStrategy: string | null;
  onSelect: (s: string | null) => void;
}) {
  if (loading) return <Skeleton className="h-56 w-full" />;
  if (!allocation || allocation.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 gap-2">
        <Activity style={{ width: 20, height: 20, color: "var(--border-2)" }} />
        <p style={{ fontSize: "11px", color: "var(--text-3)" }}>No allocation data yet</p>
      </div>
    );
  }

  const maxWeight = Math.max(...allocation.map((a) => a.weight), 1);

  return (
    <div className="space-y-2.5">
      {allocation.map((a) => {
        const color = STRATEGY_COLORS[a.strategy] ?? "var(--accent)";
        const isSelected = selectedStrategy === a.strategy;
        const sharpe = perf?.find((p) => p.strategy === a.strategy)?.sharpe_ratio;
        // Bar fill: weight as % of maxWeight, capped at 80% of container width visually
        const barPct = Math.min((a.weight / maxWeight) * 80, 80);

        return (
          <button
            key={a.strategy}
            onClick={() => onSelect(isSelected ? null : a.strategy)}
            className="w-full text-left rounded-lg px-3 py-2.5 transition-all"
            style={{
              background: isSelected ? `${color}12` : "var(--surface-2)",
              border: `1px solid ${isSelected ? color + "40" : "var(--border)"}`,
            }}
          >
            {/* Top row: label + weight */}
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: color }}
                />
                <span
                  className="font-semibold uppercase tracking-wide"
                  style={{ fontSize: "10px", color: isSelected ? color : "var(--text-2)", letterSpacing: "0.08em" }}
                >
                  {STRATEGY_LABELS[a.strategy] ?? a.strategy}
                </span>
                <span
                  className="truncate"
                  style={{ fontSize: "9px", color: "var(--text-3)", maxWidth: 140 }}
                >
                  {STRATEGY_DESCRIPTIONS[a.strategy]}
                </span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {sharpe !== undefined && (
                  <Tooltip content="Sharpe Ratio — risk-adjusted return. >1 = good, >2 = excellent. Measures return per unit of volatility.">
                    <span
                      style={{
                        fontSize: "9px",
                        color: sharpe >= 1 ? "var(--green)" : sharpe >= 0.5 ? "var(--amber)" : "var(--red)",
                        fontFamily: "JetBrains Mono",
                      }}
                    >
                      SR {sharpe.toFixed(2)}
                    </span>
                  </Tooltip>
                )}
                <span
                  className="font-mono font-bold"
                  style={{ fontSize: "11px", color: "var(--text-1)" }}
                >
                  {a.weight.toFixed(1)}%
                </span>
              </div>
            </div>
            {/* Bar */}
            <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--surface-3)" }}>
              <motion.div
                className="h-full rounded-full"
                style={{ background: color, boxShadow: isSelected ? `0 0 6px ${color}80` : "none" }}
                initial={{ width: 0 }}
                animate={{ width: `${barPct}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ── Signal badge (BUY / SELL) ──────────────────────────────────────────────────
function SignalBadge({ value }: { value: number }) {
  const isBuy = value >= 0;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-mono font-bold"
      style={{
        fontSize: "10px",
        background: isBuy ? "var(--green-dim)" : "var(--red-dim)",
        color: isBuy ? "var(--green)" : "var(--red)",
        border: `1px solid ${isBuy ? "var(--green-border)" : "var(--red-border)"}`,
      }}
    >
      {isBuy
        ? <TrendingUp style={{ width: 8, height: 8 }} />
        : <TrendingDown style={{ width: 8, height: 8 }} />}
      {isBuy ? "BUY" : "SELL"}
    </span>
  );
}

// ── Empty signals state with example rows ─────────────────────────────────────
function SignalsEmptyState() {
  return (
    <div>
      {/* Explanation card */}
      <div
        className="mx-4 mt-4 mb-3 rounded-xl p-4 flex gap-3 items-start"
        style={{ background: "var(--accent-dim)", border: "1px solid var(--accent-border)" }}
      >
        <Zap style={{ width: 16, height: 16, color: "var(--accent)", marginTop: 1, flexShrink: 0 }} />
        <div>
          <p style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.6 }}>
            Signal engine generates live <span style={{ color: "var(--green)" }}>BUY</span> /{" "}
            <span style={{ color: "var(--red)" }}>SELL</span> signals during market hours.
            Strategies scan Nifty 500 constituents every 15 minutes for qualifying setups.
          </p>
          <p style={{ fontSize: "10px", color: "var(--text-3)", marginTop: 6 }}>
            No signals have been generated in this lookback window. Signals appear here as soon as the engine runs.
          </p>
        </div>
      </div>

      {/* Example rows (grayed out) */}
      <div className="px-4 pb-4">
        <p
          className="mb-2"
          style={{ fontSize: "9px", color: "var(--text-3)", letterSpacing: "0.1em" }}
        >
          EXAMPLE — what signals look like:
        </p>
        <div className="overflow-x-auto">
          <table className="tbl" style={{ opacity: 0.45 }}>
            <thead>
              <tr>
                <th className="tbl-th">Date</th>
                <th className="tbl-th">Ticker</th>
                <th className="tbl-th">Strategy</th>
                <th className="tbl-th-r">Signal</th>
                <th className="tbl-th" style={{ textAlign: "center" }}>Approved</th>
                <th className="tbl-th">Rejection Reason</th>
              </tr>
            </thead>
            <tbody>
              {EXAMPLE_SIGNALS.map((sig, i) => (
                <tr key={i} className="tbl-row">
                  <td className="tbl-cell-muted" style={{ fontSize: "10px" }}>{sig.date}</td>
                  <td className="tbl-cell">
                    <span className="font-mono font-semibold" style={{ color: "var(--accent)", fontSize: "11px" }}>
                      {sig.ticker}
                    </span>
                    <span
                      className="ml-1.5 px-1 py-0.5 rounded"
                      style={{ fontSize: "8px", background: "rgba(106,98,86,0.1)", color: "var(--accent)", letterSpacing: "0.06em" }}
                    >
                      EXAMPLE
                    </span>
                  </td>
                  <td className="tbl-cell">
                    <div className="flex items-center gap-1.5">
                      <div
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ background: STRATEGY_COLORS[sig.strategy] ?? "#6B7280" }}
                      />
                      <span style={{ fontSize: "11px", color: "var(--text-2)" }}>
                        {STRATEGY_LABELS[sig.strategy] ?? sig.strategy}
                      </span>
                    </div>
                  </td>
                  <td className="tbl-cell-r">
                    <SignalBadge value={sig.signal} />
                  </td>
                  <td className="tbl-cell" style={{ textAlign: "center" }}>
                    {sig.approved
                      ? <CheckCircle style={{ width: 14, height: 14, color: "var(--green)", margin: "0 auto" }} />
                      : <XCircle    style={{ width: 14, height: 14, color: "var(--red)", margin: "0 auto" }} />}
                  </td>
                  <td className="tbl-cell-muted" style={{ fontSize: "10px" }}>
                    {sig.rejection_reason ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export function StrategiesPage() {
  const [signalDays, setSignalDays]           = useState<number>(5);
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null);
  const [sectorFilter, setSectorFilter]       = useState<string>("ALL");
  const [stockSearch, setStockSearch]         = useState("");
  // Signal log filters
  const [sigFromDate, setSigFromDate]         = useState("");
  const [sigToDate, setSigToDate]             = useState("");
  const [sigStratFilter, setSigStratFilter]   = useState<string | null>(null);
  const [sigTickerSearch, setSigTickerSearch] = useState("");

  const { openChart } = useUIStore();

  const { data: perf,       isLoading: perfLoading  } = useStrategyPerformance();
  const { data: signals,    isLoading: sigLoading   } = useSignals(signalDays);
  const { data: allocation, isLoading: allocLoading } = useStrategyAllocation();

  // Sector list for filter bar
  const allSectors = ["ALL", ...Array.from(new Set(NSE_STOCKS.map((s) => s.sector))).sort()];

  // Stock filtering
  const stratSectors = selectedStrategy ? STRATEGY_STOCK_MAP[selectedStrategy] : null;
  const filteredStocks = NSE_STOCKS.filter((s) => {
    const sectorMatch  = sectorFilter === "ALL" || s.sector === sectorFilter;
    const stratMatch   = !stratSectors || stratSectors.includes(s.sector);
    const searchMatch  = !stockSearch || s.symbol.includes(stockSearch.toUpperCase()) || s.name.toUpperCase().includes(stockSearch.toUpperCase());
    return sectorMatch && stratMatch && searchMatch;
  });

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Strategies" subtitle="Signal generation and strategy analytics" />

      <div className="flex-1 p-4 space-y-4 overflow-y-auto">

        {/* ── Strategy Allocation + Performance cards ─────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* Allocation horizontal bar chart */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-0.5 h-4 rounded-full" style={{ background: "var(--accent)" }} />
              <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", margin: 0 }}>Strategy Allocation</h3>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 16, paddingLeft: 12 }}>Dynamic Sharpe-weighted capital split</p>
            <AllocationBars
              allocation={allocation}
              perf={perf}
              loading={allocLoading}
              selectedStrategy={selectedStrategy}
              onSelect={setSelectedStrategy}
            />
          </motion.div>

          {/* Performance cards */}
          <div className="lg:col-span-2">
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <div style={{ width: 2, height: 16, borderRadius: 9999, background: "var(--accent)", flexShrink: 0 }} />
              <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", margin: 0 }}>Strategy Performance</h3>
              <span style={{ fontSize: 10, color: "var(--text-3)" }}>· click to filter stock universe</span>
            </div>
            {perfLoading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {perf?.map((p, i) => {
                  const color     = STRATEGY_COLORS[p.strategy] ?? "var(--accent)";
                  const isSelected = selectedStrategy === p.strategy;
                  return (
                    <motion.div
                      key={p.strategy}
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.07 }}
                      className="card p-5 cursor-pointer transition-all"
                      style={{
                        borderLeft: `2px solid ${color}`,
                        background: isSelected ? `${color}08` : undefined,
                        boxShadow: isSelected ? `0 0 0 1px ${color}30` : undefined,
                      }}
                      onClick={() => setSelectedStrategy((prev) => prev === p.strategy ? null : p.strategy)}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <div className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
                          <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)" }}>
                            {STRATEGY_LABELS[p.strategy] ?? p.strategy}
                          </span>
                        </div>
                        <Tooltip content="Sharpe Ratio — risk-adjusted return. >1 = good, >2 = excellent. Measures return per unit of volatility.">
                          <Badge variant={p.sharpe_ratio >= 1 ? "success" : p.sharpe_ratio >= 0.5 ? "warning" : "danger"}>
                            SR {p.sharpe_ratio.toFixed(2)}
                          </Badge>
                        </Tooltip>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <p style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Return</p>
                          <p style={{ fontSize: 16, fontFamily: "var(--font-mono)", fontWeight: 600, color: p.total_return >= 0 ? "var(--green)" : "var(--red)" }}>
                            {formatPct(p.total_return)}
                          </p>
                        </div>
                        <div>
                          <p style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Max DD</p>
                          <p style={{ fontSize: 16, fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--red)" }}>{formatPct(-p.max_drawdown, 2, false)}</p>
                        </div>
                        <div>
                          <p style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Win Rate</p>
                          <p style={{ fontSize: 16, fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-1)" }}>{(p.win_rate * 100).toFixed(0)}%</p>
                        </div>
                        <div>
                          <p style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Trades</p>
                          <p style={{ fontSize: 16, fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-1)" }}>{p.num_trades}</p>
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* ── Stock Universe ─────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="card overflow-hidden"
        >
          {/* Header */}
          <div className="panel-header gap-3 flex-wrap" style={{ paddingLeft: 16 }}>
            <div className="w-0.5 h-4 rounded-full shrink-0" style={{ background: "var(--accent)" }} />
            <Target style={{ width: 12, height: 12, color: "var(--text-2)" }} />
            <span className="panel-title">STOCK UNIVERSE</span>
            {selectedStrategy && (
              <span style={{ fontSize: "10px", color: "var(--accent)" }}>
                — {STRATEGY_LABELS[selectedStrategy] ?? selectedStrategy}
              </span>
            )}
            <div className="flex-1" />
            {/* Strategy pills */}
            <div className="flex items-center gap-1 flex-wrap">
              <button
                onClick={() => setSelectedStrategy(null)}
                className="px-2 py-0.5 rounded-full transition-all"
                style={{
                  fontSize: "9px", fontWeight: 700, letterSpacing: "0.08em",
                  background: !selectedStrategy ? "var(--accent)" : "var(--surface-2)",
                  color: !selectedStrategy ? "var(--bg)" : "var(--text-3)",
                  border: `1px solid ${!selectedStrategy ? "var(--accent)" : "var(--border)"}`,
                }}
              >
                ALL STRATS
              </button>
              {Object.entries(STRATEGY_LABELS).map(([key, label]) => {
                const c = STRATEGY_COLORS[key] ?? "var(--accent)";
                return (
                  <button
                    key={key}
                    onClick={() => setSelectedStrategy((prev) => prev === key ? null : key)}
                    className="px-2 py-0.5 rounded-full transition-all"
                    style={{
                      fontSize: "9px", fontWeight: 700, letterSpacing: "0.08em",
                      background: selectedStrategy === key ? c : "var(--surface-2)",
                      color: selectedStrategy === key ? "#fff" : "var(--text-3)",
                      border: `1px solid ${selectedStrategy === key ? c : "var(--border)"}`,
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Sector + search filter bar */}
          <div
            className="px-4 py-2 flex items-center gap-1.5 flex-wrap"
            style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
          >
            <Filter style={{ width: 9, height: 9, color: "var(--text-3)", marginRight: 2 }} />
            <span style={{ fontSize: "9px", color: "var(--text-3)", letterSpacing: "0.1em", marginRight: 4 }}>SECTOR:</span>
            {allSectors.slice(0, 16).map((s) => (
              <button
                key={s}
                onClick={() => setSectorFilter(s)}
                className="px-2 py-0.5 rounded transition-all"
                style={{
                  fontSize: "9px", fontWeight: 600,
                  background: sectorFilter === s ? "var(--accent-dim)" : "transparent",
                  color: sectorFilter === s ? "var(--accent)" : "var(--text-3)",
                  border: `1px solid ${sectorFilter === s ? "var(--accent-border)" : "transparent"}`,
                  borderRadius: 4,
                }}
              >
                {s}
              </button>
            ))}
            <div className="flex-1" />
            {/* Search input */}
            <input
              value={stockSearch}
              onChange={(e) => setStockSearch(e.target.value)}
              placeholder="Search symbol..."
              className="input"
              style={{ width: 130, height: 22, fontSize: "9px", padding: "0 8px" }}
            />
            <span style={{ fontSize: "9px", color: "var(--text-3)", marginLeft: 6 }}>{filteredStocks.length} stocks</span>
          </div>

          {/* Stock grid */}
          <div className="p-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 max-h-96 overflow-y-auto">
            {filteredStocks.slice(0, 150).map((stock, i) => (
              <motion.div
                key={stock.symbol}
                initial={{ opacity: 0, scale: 0.92 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: Math.min(i * 0.006, 0.25) }}
                className="relative group rounded-lg px-2.5 py-2 cursor-pointer transition-all"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
                onClick={() => openChart(stock.symbol, stock.name)}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background    = "var(--card-hover)";
                  e.currentTarget.style.borderColor   = "var(--accent-border)";
                  e.currentTarget.style.transform     = "scale(1.02)";
                  e.currentTarget.style.boxShadow     = "var(--shadow-sm)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background    = "var(--surface-2)";
                  e.currentTarget.style.borderColor   = "var(--border)";
                  e.currentTarget.style.transform     = "scale(1)";
                  e.currentTarget.style.boxShadow     = "none";
                }}
                title={`Open ${stock.name} chart`}
              >
                {/* Main content */}
                <div className="flex items-center justify-between">
                  <span
                    className="font-mono font-bold"
                    style={{ fontSize: "10px", color: "var(--accent)" }}
                  >
                    {stock.symbol}
                  </span>
                  {/* ExternalLink opens TradingView — separate from main click */}
                  <a
                    href={`https://www.tradingview.com/chart/?symbol=NSE%3A${stock.symbol}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                    title={`Open ${stock.symbol} on TradingView`}
                  >
                    <ExternalLink style={{ width: 8, height: 8, color: "var(--accent)" }} />
                  </a>
                </div>
                <div
                  className="truncate mt-0.5"
                  style={{ fontSize: "8.5px", color: "var(--text-3)" }}
                >
                  {stock.name}
                </div>
                <div
                  className="mt-1 inline-block px-1 rounded"
                  style={{
                    fontSize: "7.5px", color: "var(--text-3)", letterSpacing: "0.06em",
                    background: "var(--surface-3)", border: "1px solid var(--border)",
                  }}
                >
                  {stock.sector}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* ── Signal Log ─────────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="card overflow-hidden"
        >
          <div className="panel-header gap-3 flex-wrap" style={{ paddingLeft: 16 }}>
            <div className="w-0.5 h-4 rounded-full shrink-0" style={{ background: "var(--accent)" }} />
            <Zap style={{ width: 12, height: 12, color: "var(--text-2)" }} />
            <span className="panel-title">SIGNAL LOG</span>
            <div className="flex-1" />
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              {SIGNAL_DAYS.map((d) => (
                <button
                  key={d}
                  onClick={() => setSignalDays(d)}
                  style={{
                    fontSize: 11, padding: "4px 10px", borderRadius: 6, cursor: "pointer",
                    background: signalDays === d ? "var(--accent-dim)" : "var(--surface-2)",
                    color: signalDays === d ? "var(--accent)" : "var(--text-3)",
                    border: `1px solid ${signalDays === d ? "var(--accent-border)" : "var(--border)"}`,
                    fontFamily: "var(--font-mono)", fontWeight: 600,
                    transition: "all 120ms",
                  }}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {/* Signal log filter bar */}
          <div style={{
            display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap",
            padding: "7px 14px", borderBottom: "1px solid var(--border)",
            background: "var(--surface-2)",
          }}>
            <Filter style={{ width: 9, height: 9, color: "var(--text-3)", flexShrink: 0 }} />
            {/* Date range */}
            <input
              type="date" value={sigFromDate}
              onChange={e => setSigFromDate(e.target.value)}
              title="From date"
              style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "2px 6px", color: "var(--text-1)",
                fontFamily: "var(--font-mono)", fontSize: 9, outline: "none",
              }}
            />
            <span style={{ fontSize: 9, color: "var(--text-4)" }}>→</span>
            <input
              type="date" value={sigToDate}
              onChange={e => setSigToDate(e.target.value)}
              title="To date"
              style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "2px 6px", color: "var(--text-1)",
                fontFamily: "var(--font-mono)", fontSize: 9, outline: "none",
              }}
            />
            {(sigFromDate || sigToDate) && (
              <button onClick={() => { setSigFromDate(""); setSigToDate(""); }}
                style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-4)", fontSize: 9, padding: 0 }}>
                ✕
              </button>
            )}
            <div style={{ width: 1, height: 14, background: "var(--border-2)", flexShrink: 0 }} />
            {/* Strategy filter pills */}
            <button
              onClick={() => setSigStratFilter(null)}
              style={{
                fontSize: "9px", fontWeight: 700, padding: "2px 7px", borderRadius: 9999, border: "1px solid",
                cursor: "pointer",
                background: !sigStratFilter ? "var(--accent)" : "transparent",
                color: !sigStratFilter ? "var(--bg)" : "var(--text-3)",
                borderColor: !sigStratFilter ? "var(--accent)" : "var(--border)",
              }}
            >
              ALL
            </button>
            {Object.entries(STRATEGY_LABELS).map(([key, label]) => {
              const c = STRATEGY_COLORS[key] ?? "var(--accent)";
              return (
                <button
                  key={key}
                  onClick={() => setSigStratFilter(prev => prev === key ? null : key)}
                  style={{
                    fontSize: "9px", fontWeight: 700, padding: "2px 7px", borderRadius: 9999, border: "1px solid",
                    cursor: "pointer",
                    background: sigStratFilter === key ? c : "transparent",
                    color: sigStratFilter === key ? "#fff" : "var(--text-3)",
                    borderColor: sigStratFilter === key ? c : "var(--border)",
                  }}
                >
                  {label}
                </button>
              );
            })}
            <div style={{ flex: 1 }} />
            {/* Ticker search */}
            <input
              value={sigTickerSearch}
              onChange={e => setSigTickerSearch(e.target.value)}
              placeholder="Search ticker..."
              style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "2px 8px", color: "var(--text-1)",
                fontFamily: "var(--font-mono)", fontSize: 9, outline: "none", width: 110,
              }}
            />
          </div>

          {sigLoading ? (
            <div className="p-4"><SkeletonTable rows={6} /></div>
          ) : !signals || signals.length === 0 ? (
            <SignalsEmptyState />
          ) : (() => {
            const filtered = signals.filter(sig => {
              if (sigStratFilter && sig.strategy !== sigStratFilter) return false;
              if (sigFromDate && sig.date < sigFromDate) return false;
              if (sigToDate && sig.date > sigToDate) return false;
              if (sigTickerSearch) {
                const q = sigTickerSearch.toUpperCase();
                if (!sig.ticker.toUpperCase().includes(q)) return false;
              }
              return true;
            });
            return (
              <div className="overflow-x-auto">
                {filtered.length === 0 ? (
                  <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--text-3)", fontSize: 12 }}>
                    No signals match the current filters
                  </div>
                ) : (
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th className="tbl-th">Date</th>
                        <th className="tbl-th">Ticker</th>
                        <th className="tbl-th">Strategy</th>
                        <th className="tbl-th-r">Signal</th>
                        <th className="tbl-th" style={{ textAlign: "center" }}>Approved</th>
                        <th className="tbl-th">Rejection Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((sig, i) => (
                        <motion.tr
                          key={`${sig.date}-${sig.ticker}-${sig.strategy}`}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.01 }}
                          className="tbl-row"
                        >
                          <td className="tbl-cell-muted" style={{ fontSize: "10px" }}>{formatDate(sig.date)}</td>
                          <td className="tbl-cell">
                            <button
                              className="font-mono font-semibold hover:underline"
                              style={{ color: "var(--accent)", fontSize: "11px" }}
                              onClick={() => openChart(
                                sig.ticker.replace(".NS", "").replace(".BO", ""),
                                sig.ticker.replace(".NS", "").replace(".BO", ""),
                              )}
                            >
                              {sig.ticker.replace(".NS", "").replace(".BO", "")}
                            </button>
                          </td>
                          <td className="tbl-cell">
                            <div className="flex items-center gap-1.5">
                              <div
                                className="w-1.5 h-1.5 rounded-full"
                                style={{ background: STRATEGY_COLORS[sig.strategy] ?? "#6B7280" }}
                              />
                              <span style={{ fontSize: "11px", color: "var(--text-2)" }}>
                                {STRATEGY_LABELS[sig.strategy] ?? sig.strategy}
                              </span>
                            </div>
                          </td>
                          <td className="tbl-cell-r">
                            <SignalBadge value={sig.signal} />
                          </td>
                          <td className="tbl-cell" style={{ textAlign: "center" }}>
                            {sig.approved
                              ? <CheckCircle style={{ width: 14, height: 14, color: "var(--green)", margin: "0 auto" }} />
                              : <XCircle    style={{ width: 14, height: 14, color: "var(--red)", margin: "0 auto" }} />}
                          </td>
                          <td
                            className="tbl-cell-muted"
                            style={{ fontSize: "10px", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                          >
                            {sig.rejection_reason ?? "—"}
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })()}
        </motion.div>

      </div>
    </div>
  );
}
