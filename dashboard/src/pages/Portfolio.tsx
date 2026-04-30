import { motion } from "framer-motion";
import {
  DollarSign,
  TrendingDown,
  Layers,
  Activity,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { StatCard } from "@/components/ui/StatCard";
import { EquityChart } from "@/components/charts/EquityChart";
import { SectorPieChart } from "@/components/charts/SectorPieChart";
import { Skeleton, SkeletonCard, SkeletonTable } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import {
  usePortfolioSummary,
  usePositions,
  useSectorExposure,
  useEquityCurve,
} from "@/api/queries";
import {
  formatCurrency,
  formatPct,
  pctColor,
  pctBg,
} from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui";

const DAYS_OPTIONS = [30, 90, 252, 756] as const;

export function PortfolioPage() {
  const { equityCurveDays, setEquityCurveDays } = useUIStore();
  const { data: summary, isLoading: summaryLoading } = usePortfolioSummary();
  const { data: positions, isLoading: posLoading } = usePositions();
  const { data: sectors, isLoading: secLoading } = useSectorExposure();
  const { data: equity, isLoading: equityLoading } = useEquityCurve(equityCurveDays);

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Portfolio" subtitle="Live positions and performance" />

      <div className="flex-1 p-6 space-y-6">
        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {summaryLoading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
              <StatCard
                label="Portfolio Value"
                icon={<DollarSign className="w-4 h-4" />}
                delay={0}
                value={
                  <AnimatedNumber
                    value={summary?.portfolio_value ?? 0}
                    format={(v) => formatCurrency(v, true)}
                  />
                }
                subValue={`Cash: ${formatCurrency(summary?.cash ?? 0, true)}`}
              />
              <StatCard
                label="Day P&L"
                icon={<Activity className="w-4 h-4" />}
                delay={0.05}
                variant={
                  (summary?.day_pnl_pct ?? 0) >= 0
                    ? "success"
                    : (summary?.day_pnl_pct ?? 0) < -1
                    ? "danger"
                    : "default"
                }
                value={
                  <span className={pctColor(summary?.day_pnl_pct ?? 0)}>
                    <AnimatedNumber
                      value={summary?.day_pnl_pct ?? 0}
                      format={(v) => formatPct(v)}
                    />
                  </span>
                }
                subValue={formatCurrency(summary?.day_pnl ?? 0, true)}
              />
              <StatCard
                label="Drawdown"
                icon={<TrendingDown className="w-4 h-4" />}
                delay={0.1}
                variant={
                  (summary?.drawdown_pct ?? 0) > 8
                    ? "danger"
                    : (summary?.drawdown_pct ?? 0) > 5
                    ? "warning"
                    : "default"
                }
                value={
                  <span className="text-danger">
                    <AnimatedNumber
                      value={-(summary?.drawdown_pct ?? 0)}
                      format={(v) => formatPct(v)}
                    />
                  </span>
                }
                subValue="from peak"
              />
              <StatCard
                label="Positions"
                icon={<Layers className="w-4 h-4" />}
                delay={0.15}
                value={summary?.n_positions ?? 0}
                subValue={`Invested: ${formatCurrency(summary?.invested ?? 0, true)}`}
              />
            </>
          )}
        </div>

        {/* Equity curve + sector */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Equity curve */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.2 }}
            className="lg:col-span-2 card p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-semibold text-text-primary">
                  Equity Curve
                </h2>
                <p className="text-xs text-text-muted">vs Nifty 50 benchmark</p>
              </div>
              <div className="flex items-center gap-1">
                {DAYS_OPTIONS.map((d) => (
                  <button
                    key={d}
                    onClick={() => setEquityCurveDays(d)}
                    className={cn(
                      "text-xs px-2 py-1 rounded-md transition-colors",
                      equityCurveDays === d
                        ? "bg-primary/10 text-primary"
                        : "text-text-muted hover:text-text-primary hover:bg-bg-elevated"
                    )}
                  >
                    {d === 30 ? "1M" : d === 90 ? "3M" : d === 252 ? "1Y" : "3Y"}
                  </button>
                ))}
              </div>
            </div>
            {equityLoading ? (
              <Skeleton className="h-72 w-full" />
            ) : (
              <EquityChart data={equity ?? []} height={280} />
            )}
          </motion.div>

          {/* Sector allocation */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.25 }}
            className="card p-5"
          >
            <h2 className="text-sm font-semibold text-text-primary mb-1">
              Sector Exposure
            </h2>
            <p className="text-xs text-text-muted mb-4">Current allocation</p>
            {secLoading ? (
              <Skeleton className="h-56 w-full rounded-lg" />
            ) : (
              <SectorPieChart data={sectors ?? []} height={220} />
            )}
          </motion.div>
        </div>

        {/* Positions table */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.3 }}
          className="card overflow-hidden"
        >
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">
              Open Positions
            </h2>
            <Badge variant="neutral">{positions?.length ?? 0} positions</Badge>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-elevated/50">
                  <th className="table-header text-left">Ticker</th>
                  <th className="table-header text-right">Qty</th>
                  <th className="table-header text-right">Avg Price</th>
                  <th className="table-header text-right">CMP</th>
                  <th className="table-header text-right">Unrealized P&L</th>
                  <th className="table-header text-right">P&L %</th>
                  <th className="table-header text-right">Weight</th>
                  <th className="table-header text-left">Strategy</th>
                  <th className="table-header text-left">Sector</th>
                </tr>
              </thead>
              <tbody>
                {posLoading ? (
                  <SkeletonTable rows={8} />
                ) : positions?.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="text-center py-12 text-text-muted text-sm">
                      No open positions
                    </td>
                  </tr>
                ) : (
                  positions?.map((pos, i) => (
                    <motion.tr
                      key={pos.ticker}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.02 }}
                      className="table-row"
                    >
                      <td className="table-cell">
                        <span className="font-mono font-semibold text-text-primary">
                          {pos.ticker.replace(".NS", "").replace(".BO", "")}
                        </span>
                      </td>
                      <td className="table-cell text-right">{pos.quantity.toLocaleString("en-IN")}</td>
                      <td className="table-cell text-right">₹{pos.avg_buy_price.toFixed(2)}</td>
                      <td className="table-cell text-right">₹{pos.current_price.toFixed(2)}</td>
                      <td className={cn("table-cell text-right", pctColor(pos.unrealized_pnl))}>
                        {formatCurrency(pos.unrealized_pnl, true)}
                      </td>
                      <td className="table-cell text-right">
                        <span className={cn("px-1.5 py-0.5 rounded text-xs font-mono", pctBg(pos.pnl_pct))}>
                          {formatPct(pos.pnl_pct)}
                        </span>
                      </td>
                      <td className="table-cell text-right">
                        {pos.weight.toFixed(1)}%
                      </td>
                      <td className="table-cell">
                        <Badge variant="primary" className="text-[10px]">
                          {pos.strategy}
                        </Badge>
                      </td>
                      <td className="table-cell text-text-secondary text-xs">
                        {pos.sector}
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
