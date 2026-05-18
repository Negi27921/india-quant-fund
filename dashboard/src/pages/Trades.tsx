import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { ArrowUpDown, Filter, X as XIcon } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { SkeletonCard, SkeletonTable } from "@/components/ui/Skeleton";
import { OrderStatusBadge, SideBadge } from "@/components/ui/Badge";
import { StatCard } from "@/components/ui/StatCard";
import { SimpleBarChart } from "@/components/charts/BarChart";
import { useOrders, useFills, useTradeStats } from "@/api/queries";
import { formatDateTime } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { CHART_COLORS, STRATEGY_LABELS } from "@/lib/constants";

const STATUS_OPTIONS = ["all", "FILLED", "PENDING", "REJECTED", "CANCELLED"] as const;
const DAYS_OPTIONS = [7, 30, 90] as const;

export function TradesPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [days, setDays] = useState(30);
  const [sortKey, setSortKey] = useState<"created_at" | "ticker">("created_at");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const { data: orders, isLoading: ordersLoading } = useOrders(statusFilter, 500);
  const { data: stats, isLoading: statsLoading } = useTradeStats(days);
  const { data: fills } = useFills(days);

  const sorted = useMemo(() => {
    let rows = orders ? [...orders] : [];
    if (fromDate) rows = rows.filter(o => o.created_at.slice(0, 10) >= fromDate);
    if (toDate)   rows = rows.filter(o => o.created_at.slice(0, 10) <= toDate);
    return rows.sort((a, b) => {
      if (sortKey === "ticker") return a.ticker.localeCompare(b.ticker);
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [orders, fromDate, toDate, sortKey]);

  const strategyBreakdown = fills
    ? Object.entries(
        fills.reduce(
          (acc, o) => {
            acc[o.strategy] = (acc[o.strategy] ?? 0) + 1;
            return acc;
          },
          {} as Record<string, number>
        )
      ).map(([strategy, count]) => ({ strategy: STRATEGY_LABELS[strategy] ?? strategy, count }))
    : [];

  const fillRate = stats
    ? stats.total_orders > 0
      ? ((stats.filled / stats.total_orders) * 100).toFixed(1)
      : "0"
    : null;

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Trades" subtitle="Order history and execution analytics" />

      <div className="flex-1 p-6 space-y-6">
        {/* Stats */}
        <div className="flex items-center gap-3 mb-2">
          <span className="text-xs text-text-muted">Period:</span>
          {DAYS_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={cn(
                "text-xs px-3 py-1.5 rounded-md transition-colors",
                days === d
                  ? "bg-primary/10 text-primary border border-primary/20"
                  : "text-text-muted hover:text-text-primary bg-bg-elevated"
              )}
            >
              {d}d
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {statsLoading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
              <StatCard
                label="Total Orders"
                value={stats?.total_orders ?? 0}
                subValue={`Fill rate: ${fillRate}%`}
                delay={0}
              />
              <StatCard
                label="Filled"
                value={stats?.filled ?? 0}
                variant="success"
                delay={0.05}
              />
              <StatCard
                label="Rejected"
                value={stats?.rejected ?? 0}
                variant={stats?.rejected ? "danger" : "default"}
                delay={0.1}
              />
              <StatCard
                label="Buy / Sell"
                value={`${stats?.buys ?? 0} / ${stats?.sells ?? 0}`}
                delay={0.15}
              />
            </>
          )}
        </div>

        {/* Charts */}
        {strategyBreakdown.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card p-5"
          >
            <h3 className="text-sm font-semibold text-text-primary mb-4">
              Fills by Strategy ({days}d)
            </h3>
            <SimpleBarChart
              data={strategyBreakdown}
              dataKey="count"
              nameKey="strategy"
              height={160}
              colorFn={() => CHART_COLORS.primary}
              formatter={(v) => `${v} trades`}
            />
          </motion.div>
        )}

        {/* Orders table */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="card overflow-hidden"
        >
          <div className="px-5 py-4 border-b border-border flex items-center gap-3 flex-wrap">
            <h3 className="text-sm font-semibold" style={{ color: "var(--text-1)", flex: 1 }}>
              Order History
              <span style={{ marginLeft: 8, fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-mono)", fontWeight: 400 }}>
                {sorted.length} records
              </span>
            </h3>

            {/* Date range filter */}
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Filter style={{ width: 10, height: 10, color: "var(--text-4)" }} />
              <input
                type="date"
                value={fromDate}
                onChange={e => setFromDate(e.target.value)}
                style={{
                  background: "var(--surface-2)", border: "1px solid var(--border)",
                  borderRadius: 5, padding: "3px 8px", color: "var(--text-1)",
                  fontFamily: "var(--font-mono)", fontSize: 10, outline: "none",
                  colorScheme: "dark",
                }}
                title="From date"
              />
              <span style={{ fontSize: 10, color: "var(--text-4)" }}>→</span>
              <input
                type="date"
                value={toDate}
                onChange={e => setToDate(e.target.value)}
                style={{
                  background: "var(--surface-2)", border: "1px solid var(--border)",
                  borderRadius: 5, padding: "3px 8px", color: "var(--text-1)",
                  fontFamily: "var(--font-mono)", fontSize: 10, outline: "none",
                  colorScheme: "dark",
                }}
                title="To date"
              />
              {(fromDate || toDate) && (
                <button
                  onClick={() => { setFromDate(""); setToDate(""); }}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-4)", padding: 2 }}
                >
                  <XIcon style={{ width: 11, height: 11 }} />
                </button>
              )}
            </div>

            {/* Status filters */}
            <div className="flex items-center gap-1">
              {STATUS_OPTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  style={{
                    fontSize: 10, padding: "3px 8px", borderRadius: 5, cursor: "pointer",
                    fontFamily: "var(--font-body)", fontWeight: 600, border: "1px solid",
                    textTransform: "capitalize",
                    background: statusFilter === s ? "var(--accent-dim)" : "var(--surface-2)",
                    color: statusFilter === s ? "var(--accent)" : "var(--text-3)",
                    borderColor: statusFilter === s ? "var(--accent-border)" : "var(--border)",
                    transition: "all 120ms",
                  }}
                >
                  {s.toLowerCase()}
                </button>
              ))}
            </div>

            {/* Sort */}
            <button
              onClick={() => setSortKey((k) => (k === "created_at" ? "ticker" : "created_at"))}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                fontSize: 10, padding: "3px 9px", borderRadius: 5, cursor: "pointer",
                background: "var(--surface-2)", border: "1px solid var(--border)",
                color: "var(--text-3)", fontFamily: "var(--font-body)", fontWeight: 600,
              }}
            >
              <ArrowUpDown style={{ width: 10, height: 10 }} />
              {sortKey === "created_at" ? "Time" : "Ticker"}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-elevated/50">
                  <th className="table-header text-left">Ticker</th>
                  <th className="table-header text-left">Side</th>
                  <th className="table-header text-right">Qty</th>
                  <th className="table-header text-right">Limit</th>
                  <th className="table-header text-right">Filled @</th>
                  <th className="table-header text-left">Status</th>
                  <th className="table-header text-left">Strategy</th>
                  <th className="table-header text-right">Submitted</th>
                  <th className="table-header text-left">Note</th>
                </tr>
              </thead>
              <tbody>
                {ordersLoading ? (
                  <SkeletonTable rows={10} />
                ) : sorted.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-text-muted text-sm">
                      No orders found
                    </td>
                  </tr>
                ) : (
                  sorted.map((order, i) => (
                    <motion.tr
                      key={order.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.015 }}
                      className="table-row"
                    >
                      <td className="table-cell font-semibold">
                        {order.ticker.replace(".NS", "").replace(".BO", "")}
                      </td>
                      <td className="table-cell">
                        <SideBadge side={order.side} />
                      </td>
                      <td className="table-cell text-right">
                        {order.quantity.toLocaleString("en-IN")}
                      </td>
                      <td className="table-cell text-right">
                        {order.limit_price ? `₹${order.limit_price.toFixed(2)}` : "MKT"}
                      </td>
                      <td className="table-cell text-right">
                        {order.avg_fill_price
                          ? `₹${order.avg_fill_price.toFixed(2)}`
                          : "—"}
                      </td>
                      <td className="table-cell">
                        <OrderStatusBadge status={order.status} />
                      </td>
                      <td className="table-cell text-text-secondary text-xs">
                        {STRATEGY_LABELS[order.strategy] ?? order.strategy}
                      </td>
                      <td className="table-cell text-right text-text-muted text-xs">
                        {formatDateTime(order.created_at)}
                      </td>
                      <td className="table-cell text-text-muted text-xs max-w-xs truncate">
                        {order.rejection_reason ?? "—"}
                      </td>
                    </motion.tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
