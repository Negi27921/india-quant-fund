import { useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle, XCircle, BarChart3 } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { Skeleton, SkeletonCard, SkeletonTable } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { SimpleBarChart } from "@/components/charts/BarChart";
import {
  useStrategyPerformance,
  useSignals,
  useStrategyAllocation,
} from "@/api/queries";
import { formatPct, formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import {
  STRATEGY_COLORS,
  STRATEGY_LABELS,
  CHART_COLORS,
} from "@/lib/constants";

const SIGNAL_DAYS = [1, 3, 5, 10] as const;

export function StrategiesPage() {
  const [signalDays, setSignalDays] = useState<number>(5);
  const { data: perf, isLoading: perfLoading } = useStrategyPerformance();
  const { data: signals, isLoading: sigLoading } = useSignals(signalDays);
  const { data: allocation, isLoading: allocLoading } = useStrategyAllocation();

  const allocationData = allocation?.map((a) => ({
    strategy: STRATEGY_LABELS[a.strategy] ?? a.strategy,
    weight: a.weight,
    key: a.strategy,
  }));

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Strategies" subtitle="Signal generation and strategy analytics" />

      <div className="flex-1 p-6 space-y-6">
        {/* Strategy allocation */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Allocation chart */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="card p-5"
          >
            <h3 className="text-sm font-semibold text-text-primary mb-1">
              Strategy Allocation
            </h3>
            <p className="text-xs text-text-muted mb-4">Dynamic Sharpe-weighted</p>
            {allocLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : (
              <>
                <SimpleBarChart
                  data={allocationData ?? []}
                  dataKey="weight"
                  nameKey="strategy"
                  height={160}
                  colorFn={(_val, index) => {
                    const key = allocationData?.[index ?? 0]?.key ?? "";
                    return STRATEGY_COLORS[key] ?? CHART_COLORS.primary;
                  }}
                  formatter={(v) => `${v.toFixed(1)}%`}
                  yTickFormatter={(v) => `${v}%`}
                />
                <div className="mt-3 space-y-1">
                  {allocation?.map((a) => (
                    <div key={a.strategy} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ background: STRATEGY_COLORS[a.strategy] ?? "#6B7280" }}
                        />
                        <span className="text-text-muted">
                          {STRATEGY_LABELS[a.strategy] ?? a.strategy}
                        </span>
                      </div>
                      <span className="font-mono text-text-primary">{a.weight.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </motion.div>

          {/* Performance cards */}
          <div className="lg:col-span-2">
            {perfLoading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {perf?.map((p, i) => (
                  <motion.div
                    key={p.strategy}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.07 }}
                    className="card p-5"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ background: STRATEGY_COLORS[p.strategy] ?? "#6B7280" }}
                        />
                        <span className="text-sm font-semibold text-text-primary">
                          {STRATEGY_LABELS[p.strategy] ?? p.strategy}
                        </span>
                      </div>
                      <Badge
                        variant={
                          p.sharpe_ratio >= 1
                            ? "success"
                            : p.sharpe_ratio >= 0.5
                            ? "warning"
                            : "danger"
                        }
                      >
                        SR {p.sharpe_ratio.toFixed(2)}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-[10px] text-text-muted uppercase tracking-wider">Return</p>
                        <p className={cn("text-base font-mono font-semibold", p.total_return >= 0 ? "text-success" : "text-danger")}>
                          {formatPct(p.total_return)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-text-muted uppercase tracking-wider">Max DD</p>
                        <p className="text-base font-mono font-semibold text-danger">
                          {formatPct(-p.max_drawdown, 2, false)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-text-muted uppercase tracking-wider">Win Rate</p>
                        <p className="text-base font-mono font-semibold text-text-primary">
                          {(p.win_rate * 100).toFixed(0)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-text-muted uppercase tracking-wider">Trades</p>
                        <p className="text-base font-mono font-semibold text-text-primary">
                          {p.num_trades}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Signals table */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card overflow-hidden"
        >
          <div className="px-5 py-4 border-b border-border flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-text-muted" />
              <h3 className="text-sm font-semibold text-text-primary">Signal Log</h3>
            </div>
            <div className="flex-1" />
            <div className="flex items-center gap-1">
              {SIGNAL_DAYS.map((d) => (
                <button
                  key={d}
                  onClick={() => setSignalDays(d)}
                  className={cn(
                    "text-xs px-2.5 py-1 rounded-md transition-colors",
                    signalDays === d
                      ? "bg-primary/10 text-primary border border-primary/20"
                      : "text-text-muted hover:text-text-primary bg-bg-elevated"
                  )}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-elevated/50">
                  <th className="table-header text-left">Date</th>
                  <th className="table-header text-left">Ticker</th>
                  <th className="table-header text-left">Strategy</th>
                  <th className="table-header text-right">Signal</th>
                  <th className="table-header text-center">Approved</th>
                  <th className="table-header text-left">Rejection Reason</th>
                </tr>
              </thead>
              <tbody>
                {sigLoading ? (
                  <SkeletonTable rows={8} />
                ) : signals?.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-text-muted text-sm">
                      No signals in the past {signalDays} days
                    </td>
                  </tr>
                ) : (
                  signals?.map((sig, i) => (
                    <motion.tr
                      key={`${sig.date}-${sig.ticker}-${sig.strategy}`}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.01 }}
                      className="table-row"
                    >
                      <td className="table-cell text-text-muted text-xs">
                        {formatDate(sig.date)}
                      </td>
                      <td className="table-cell font-semibold">
                        {sig.ticker.replace(".NS", "").replace(".BO", "")}
                      </td>
                      <td className="table-cell">
                        <div className="flex items-center gap-1.5">
                          <div
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: STRATEGY_COLORS[sig.strategy] ?? "#6B7280" }}
                          />
                          <span className="text-text-secondary text-xs">
                            {STRATEGY_LABELS[sig.strategy] ?? sig.strategy}
                          </span>
                        </div>
                      </td>
                      <td className="table-cell text-right">
                        <SignalBar value={sig.signal} />
                      </td>
                      <td className="table-cell text-center">
                        {sig.approved ? (
                          <CheckCircle className="w-4 h-4 text-success mx-auto" />
                        ) : (
                          <XCircle className="w-4 h-4 text-danger mx-auto" />
                        )}
                      </td>
                      <td className="table-cell text-text-muted text-xs max-w-xs truncate">
                        {sig.rejection_reason ?? "—"}
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

function SignalBar({ value }: { value: number }) {
  const pct = Math.abs(value) * 100;
  const color = value >= 0 ? CHART_COLORS.success : CHART_COLORS.danger;
  return (
    <div className="flex items-center justify-end gap-2">
      <span className="font-mono text-xs text-text-primary">{value.toFixed(2)}</span>
      <div className="w-16 h-1.5 rounded-full bg-bg-overlay overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4 }}
        />
      </div>
    </div>
  );
}
