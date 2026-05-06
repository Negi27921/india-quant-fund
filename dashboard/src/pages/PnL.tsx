import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  ChevronLeft, ChevronRight, TrendingUp, TrendingDown,
  CalendarDays, BarChart2, Target, Flame,
} from "lucide-react";
import {
  AreaChart, Area, ResponsiveContainer, Tooltip as ReTip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, ReferenceLine,
} from "recharts";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { formatCurrency } from "@/lib/utils";
import { usePnLCalendar, usePnLStats, usePaperPositions } from "@/api/pnl-queries";

// ── Helpers ───────────────────────────────────────────────────────────────────
const numColor = (v: number) => (v > 0 ? "#00C853" : v < 0 ? "#FF3B3B" : "#888");
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function pnlCellBg(pct: number): string {
  if (pct === 0) return "#111";
  const t = Math.min(Math.abs(pct) / 3, 1);
  const a = 0.1 + t * 0.55;
  return pct > 0 ? `rgba(0,200,83,${a})` : `rgba(255,59,59,${a})`;
}

// ── Stat panel ────────────────────────────────────────────────────────────────
function StatPanel({ label, value, sub, color, icon: Icon, delay = 0 }: {
  label: string; value: string; sub?: string; color?: string; icon?: React.FC<{ style?: React.CSSProperties }>; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="panel p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="stat-label">{label}</span>
        {Icon && <Icon style={{ width: 13, height: 13, color: "#444" }} />}
      </div>
      <div className="font-mono font-bold" style={{ fontSize: "22px", color: color || "#E0E0E0", lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "10px", color: "#555", marginTop: 4 }}>{sub}</div>}
    </motion.div>
  );
}

// ── Calendar heatmap ──────────────────────────────────────────────────────────
function CalendarHeatmap({ year, month, data }: {
  year: number; month: number; data: { date: string; pnl: number; pnl_pct: number }[];
}) {
  const dataMap = useMemo(() => {
    const m: Record<string, { pnl: number; pnl_pct: number }> = {};
    data.forEach((d) => { m[d.date.slice(0, 10)] = d; });
    return m;
  }, [data]);

  const daysInMonth = new Date(year, month, 0).getDate();
  const firstDay = new Date(year, month - 1, 1).getDay(); // 0=Sun
  // Offset to make Monday = 0
  const offset = firstDay === 0 ? 6 : firstDay - 1;

  const cells: { day: number | null; dateStr: string | null }[] = [];
  for (let i = 0; i < offset; i++) cells.push({ day: null, dateStr: null });
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, dateStr });
  }

  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div>
      {/* Weekday labels */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map((d) => (
          <div key={d} style={{ fontSize: "9px", color: "#444", textAlign: "center", letterSpacing: "0.06em" }}>{d}</div>
        ))}
      </div>
      {/* Cells */}
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, i) => {
          if (!cell.day || !cell.dateStr) {
            return <div key={i} className="aspect-square" />;
          }
          const entry = dataMap[cell.dateStr];
          const pct = entry?.pnl_pct ?? 0;
          const isToday = cell.dateStr === new Date().toISOString().slice(0, 10);
          const isHovered = hovered === cell.dateStr;

          return (
            <div
              key={cell.dateStr}
              className="aspect-square flex flex-col items-center justify-center cursor-default relative"
              style={{
                background: entry ? pnlCellBg(pct) : "#0A0A0A",
                border: isToday ? "1px solid #E8930A" : "1px solid #111",
                borderRadius: "2px",
                transition: "all 80ms",
                transform: isHovered ? "scale(1.15)" : "scale(1)",
              }}
              onMouseEnter={() => setHovered(cell.dateStr)}
              onMouseLeave={() => setHovered(null)}
            >
              <span style={{ fontSize: "9px", color: entry ? "#E0E0E0" : "#333", fontFamily: "JetBrains Mono", lineHeight: 1 }}>
                {cell.day}
              </span>
              {entry && (
                <span style={{ fontSize: "8px", color: numColor(pct), fontFamily: "JetBrains Mono", lineHeight: 1.2 }}>
                  {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
                </span>
              )}

              {/* Tooltip */}
              {isHovered && entry && (
                <div
                  className="absolute z-50 pointer-events-none"
                  style={{
                    bottom: "calc(100% + 6px)",
                    left: "50%",
                    transform: "translateX(-50%)",
                    background: "#0A0A0A",
                    border: "1px solid #2A2A2A",
                    borderRadius: "3px",
                    padding: "6px 10px",
                    whiteSpace: "nowrap",
                    boxShadow: "0 4px 16px rgba(0,0,0,0.8)",
                  }}
                >
                  <div style={{ fontSize: "10px", color: "#888", marginBottom: 2 }}>{cell.dateStr}</div>
                  <div className="font-mono font-bold" style={{ fontSize: "13px", color: numColor(pct) }}>
                    {pct > 0 ? "+" : ""}{pct.toFixed(2)}%
                  </div>
                  <div className="font-mono" style={{ fontSize: "11px", color: "#E0E0E0" }}>
                    {entry.pnl >= 0 ? "+" : ""}₹{Math.abs(entry.pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Monthly bar chart ─────────────────────────────────────────────────────────
function MonthlyChart({ data }: { data: { month: string; pnl: number; pnl_pct: number }[] }) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer width="100%" height={140}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <CartesianGrid stroke="#111" vertical={false} />
        <XAxis dataKey="month" tick={{ fontSize: 9, fill: "#555" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 9, fill: "#555" }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
        <ReferenceLine y={0} stroke="#2A2A2A" />
        <ReTip
          contentStyle={{ background: "#080808", border: "1px solid #1C1C1C", borderRadius: 2, fontSize: 11, fontFamily: "JetBrains Mono" }}
          formatter={(v: number) => [`${v.toFixed(2)}%`, "Monthly P&L"]}
          labelStyle={{ color: "#888", fontSize: 10 }}
        />
        <Bar dataKey="pnl_pct" radius={[2, 2, 0, 0]} maxBarSize={32}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.pnl_pct >= 0 ? "#00C853" : "#FF3B3B"} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Equity curve ──────────────────────────────────────────────────────────────
function EquityCurve({ data }: { data: { date: string; portfolio_value: number }[] }) {
  if (data.length < 2) return null;
  const first = data[0].portfolio_value;
  const last  = data[data.length - 1].portfolio_value;
  const up = last >= first;
  const color = up ? "#00C853" : "#FF3B3B";

  return (
    <ResponsiveContainer width="100%" height={120}>
      <AreaChart data={data} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="navGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={color} stopOpacity={0.25} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#111" vertical={false} />
        <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#555" }} axisLine={false} tickLine={false}
          tickFormatter={(v) => v.slice(5)} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 9, fill: "#555" }} axisLine={false} tickLine={false}
          tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`} width={48} />
        <ReTip
          contentStyle={{ background: "#080808", border: "1px solid #1C1C1C", borderRadius: 2, fontSize: 11, fontFamily: "JetBrains Mono" }}
          formatter={(v: number) => [`₹${v.toLocaleString("en-IN")}`, "Portfolio"]}
          labelStyle={{ color: "#888", fontSize: 10 }}
        />
        <Area type="monotone" dataKey="portfolio_value" stroke={color} strokeWidth={1.5}
          fill="url(#navGrad)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Positions table ───────────────────────────────────────────────────────────
function PositionsTable() {
  const { data: positions, isLoading } = usePaperPositions();

  if (isLoading) return (
    <div className="space-y-1.5 p-3">
      {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-9 w-full" />)}
    </div>
  );

  if (!positions?.length) return (
    <div className="py-8 text-center" style={{ color: "#444", fontSize: "11px" }}>
      No open positions
    </div>
  );

  return (
    <div className="overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            {["TICKER","SECTOR","QTY","AVG COST","CMP","UNRLZD P&L","% CHG","WT%","STRATEGY"].map((h, i) => (
              <th key={h} className={i >= 4 ? "tbl-th-r" : "tbl-th"}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p, i) => (
            <motion.tr
              key={p.ticker}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.03 }}
              className="tbl-row"
            >
              <td className="tbl-cell font-bold" style={{ color: "#E0E0E0" }}>
                {p.ticker.replace(".NS", "").replace(".BO", "")}
              </td>
              <td className="tbl-cell" style={{ color: "#888", fontSize: "10px" }}>{p.sector || "—"}</td>
              <td className="tbl-cell-r">{p.quantity.toLocaleString("en-IN")}</td>
              <td className="tbl-cell-r">₹{p.avg_buy_price.toFixed(2)}</td>
              <td className="tbl-cell-r">₹{p.current_price.toFixed(2)}</td>
              <td className="tbl-cell-r">
                <span style={{ color: numColor(p.unrealized_pnl) }}>
                  {p.unrealized_pnl >= 0 ? "+" : ""}₹{Math.abs(p.unrealized_pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
              </td>
              <td className="tbl-cell-r">
                <span className="font-bold" style={{ color: numColor(p.pnl_pct) }}>
                  {p.pnl_pct >= 0 ? "+" : ""}{p.pnl_pct.toFixed(2)}%
                </span>
              </td>
              <td className="tbl-cell-r">{p.weight.toFixed(1)}%</td>
              <td className="tbl-cell" style={{ color: "#888", fontSize: "10px" }}>{p.strategy || "—"}</td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Date range helpers ────────────────────────────────────────────────────────
function monthStart(year: number, m: number): string {
  return `${year}-${String(m).padStart(2, "0")}-01`;
}

function monthEnd(year: number, m: number): string {
  const last = new Date(year, m, 0).getDate();
  return `${year}-${String(m).padStart(2, "0")}-${String(last).padStart(2, "0")}`;
}

const DATE_INPUT_STYLE: React.CSSProperties = {
  background: "rgba(0,255,65,0.04)",
  border: "1px solid rgba(0,255,65,0.3)",
  color: "var(--text-1)",
  fontFamily: "var(--font-mono)",
  borderRadius: 4,
  padding: "6px 10px",
  outline: "none",
  fontSize: 11,
  cursor: "pointer",
};

// ── Page ───────────────────────────────────────────────────────────────────────
export function PnLPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  // Date range filter — default to current month
  const [rangeStart, setRangeStart] = useState<string>(monthStart(now.getFullYear(), now.getMonth() + 1));
  const [rangeEnd, setRangeEnd]     = useState<string>(monthEnd(now.getFullYear(), now.getMonth() + 1));

  const { data: calData = [] } = usePnLCalendar(year, month);
  const { data: stats }        = usePnLStats();
  const { data: allData = [] } = usePnLCalendar(year);

  const monthLabel = `${MONTHS[month - 1]} ${year}`;

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear((y) => y - 1); }
    else setMonth((m) => m - 1);
  };
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear((y) => y + 1); }
    else setMonth((m) => m + 1);
  };

  // Apply date range filter to calendar data
  const filteredCalData = calData.filter((d) => {
    const date = d.date.slice(0, 10);
    return date >= rangeStart && date <= rangeEnd;
  });

  // Quick-select a month
  const selectQuickMonth = (m: number) => {
    setMonth(m);
    setRangeStart(monthStart(year, m));
    setRangeEnd(monthEnd(year, m));
  };

  // P&L stats computed from filtered range
  const monthPnL = filteredCalData.reduce((s, d) => s + d.pnl, 0);
  const monthPnLPct = filteredCalData.length > 0
    ? filteredCalData.reduce((s, d) => s + d.pnl_pct, 0)
    : 0;
  const monthWins  = filteredCalData.filter((d) => d.pnl > 0).length;
  const monthLoss  = filteredCalData.filter((d) => d.pnl < 0).length;

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="P&L" subtitle="Paper trading performance and calendar" />

      <div className="flex-1 p-4 space-y-4 overflow-y-auto">

        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatPanel
            label="TOTAL P&L"
            value={formatCurrency(stats?.total_pnl ?? 0, true)}
            sub={`${(stats?.total_pnl_pct ?? 0) > 0 ? "+" : ""}${(stats?.total_pnl_pct ?? 0).toFixed(2)}% overall`}
            color={numColor(stats?.total_pnl ?? 0)}
            icon={TrendingUp}
            delay={0}
          />
          <StatPanel
            label="WIN DAYS"
            value={String(stats?.win_days ?? 0)}
            sub={`${stats?.loss_days ?? 0} losing days`}
            color="#00C853"
            icon={Target}
            delay={0.04}
          />
          <StatPanel
            label="BEST DAY"
            value={`+${(stats?.best_day ?? 0).toFixed(2)}%`}
            color="#00C853"
            icon={Flame}
            delay={0.08}
          />
          <StatPanel
            label="WORST DAY"
            value={`${(stats?.worst_day ?? 0).toFixed(2)}%`}
            color="#FF3B3B"
            icon={TrendingDown}
            delay={0.12}
          />
          <StatPanel
            label="AVG WIN"
            value={`+${(stats?.avg_win ?? 0).toFixed(2)}%`}
            color="#00C853"
            delay={0.16}
          />
          <StatPanel
            label="AVG LOSS"
            value={`${(stats?.avg_loss ?? 0).toFixed(2)}%`}
            color="#FF3B3B"
            delay={0.2}
          />
        </div>

        {/* Calendar + Monthly chart */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">

          {/* Calendar */}
          <div className="lg:col-span-2 panel">
            <div className="panel-header justify-between">
              <div className="flex items-center gap-2">
                <CalendarDays style={{ width: 11, height: 11, color: "#E8930A" }} />
                <span className="panel-title">P&L CALENDAR</span>
              </div>
              <div className="flex items-center gap-2">
                {/* Month summary */}
                <span className="font-mono font-semibold" style={{ fontSize: "11px", color: numColor(monthPnL) }}>
                  {monthPnL >= 0 ? "+" : ""}₹{Math.abs(monthPnL).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
                <span style={{ color: "#1C1C1C" }}>│</span>
                {/* Nav */}
                <button onClick={prevMonth} className="btn-ghost p-1">
                  <ChevronLeft style={{ width: 12, height: 12 }} />
                </button>
                <span className="font-mono font-semibold" style={{ fontSize: "11px", color: "#E0E0E0", minWidth: 64, textAlign: "center" }}>
                  {monthLabel}
                </span>
                <button onClick={nextMonth} className="btn-ghost p-1">
                  <ChevronRight style={{ width: 12, height: 12 }} />
                </button>
              </div>
            </div>

            {/* Date range filter */}
            <div style={{ padding: "10px 16px 0", borderBottom: "1px solid #111" }}>
              {/* Month quick-select buttons */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
                {MONTHS.map((label, idx) => {
                  const m = idx + 1;
                  const isActive = m === month;
                  return (
                    <button
                      key={label}
                      onClick={() => selectQuickMonth(m)}
                      style={{
                        fontSize: 9,
                        fontFamily: "var(--font-mono)",
                        padding: "3px 7px",
                        borderRadius: 3,
                        border: isActive ? "1px solid rgba(0,255,65,0.6)" : "1px solid rgba(0,255,65,0.2)",
                        background: isActive ? "rgba(0,255,65,0.15)" : "rgba(0,255,65,0.03)",
                        color: isActive ? "#00FF41" : "#555",
                        cursor: "pointer",
                        transition: "all 80ms",
                        letterSpacing: "0.04em",
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              {/* Date range inputs */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, paddingBottom: 10 }}>
                <span style={{ fontSize: 9, color: "#555", fontFamily: "var(--font-mono)", letterSpacing: "0.06em" }}>FROM</span>
                <input
                  type="date"
                  value={rangeStart}
                  onChange={(e) => setRangeStart(e.target.value)}
                  style={DATE_INPUT_STYLE}
                />
                <span style={{ fontSize: 9, color: "#555", fontFamily: "var(--font-mono)", letterSpacing: "0.06em" }}>TO</span>
                <input
                  type="date"
                  value={rangeEnd}
                  onChange={(e) => setRangeEnd(e.target.value)}
                  style={DATE_INPUT_STYLE}
                />
                <span style={{ fontSize: 9, color: "#444", fontFamily: "var(--font-mono)", marginLeft: 4 }}>
                  {filteredCalData.length} trading day{filteredCalData.length !== 1 ? "s" : ""}
                </span>
              </div>
            </div>

            <div className="p-4">
              <CalendarHeatmap year={year} month={month} data={filteredCalData} />
              {/* Month stats below calendar */}
              <div className="flex items-center justify-between mt-4 pt-3" style={{ borderTop: "1px solid #111" }}>
                {[
                  { label: "MONTH P&L", val: `${monthPnL >= 0 ? "+" : ""}${monthPnLPct.toFixed(2)}%`, color: numColor(monthPnL) },
                  { label: "WIN DAYS", val: String(monthWins), color: "#00C853" },
                  { label: "LOSS DAYS", val: String(monthLoss), color: "#FF3B3B" },
                  { label: "WIN RATE", val: `${monthWins + monthLoss ? ((monthWins / (monthWins + monthLoss)) * 100).toFixed(0) : "—"}%`, color: "#E0E0E0" },
                ].map((item) => (
                  <div key={item.label} className="text-center">
                    <div className="stat-label">{item.label}</div>
                    <div className="font-mono font-bold" style={{ fontSize: "14px", color: item.color, marginTop: 2 }}>{item.val}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Monthly P&L bar + equity curve */}
          <div className="space-y-3">
            <div className="panel">
              <div className="panel-header">
                <BarChart2 style={{ width: 11, height: 11, color: "#E8930A" }} />
                <span className="panel-title">MONTHLY P&L {year}</span>
              </div>
              <div className="p-3">
                {stats?.monthly ? (
                  <MonthlyChart data={stats.monthly} />
                ) : (
                  <div className="skeleton h-36 w-full" />
                )}
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <TrendingUp style={{ width: 11, height: 11, color: "#E8930A" }} />
                <span className="panel-title">NAV CURVE {year}</span>
              </div>
              <div className="p-3">
                {allData.length > 1 ? (
                  <EquityCurve data={allData} />
                ) : (
                  <div className="skeleton h-28 w-full" />
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Open positions */}
        <div className="panel">
          <div className="panel-header">
            <Target style={{ width: 11, height: 11, color: "#E8930A" }} />
            <span className="panel-title">OPEN POSITIONS</span>
            <span style={{ fontSize: "9px", color: "#555", marginLeft: 4 }}>PAPER TRADING</span>
          </div>
          <PositionsTable />
        </div>

      </div>
    </div>
  );
}
