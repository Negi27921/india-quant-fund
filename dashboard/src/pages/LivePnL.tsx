import { motion, AnimatePresence } from "framer-motion";
import { Activity, Wifi, WifiOff, TrendingUp, TrendingDown } from "lucide-react";
import { format } from "date-fns";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLiveStore } from "@/store/live";
import { useDrawdownHistory, useRiskMetrics, useOrders } from "@/api/queries";
import { formatCurrency, formatPct, formatDateTime } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { OrderStatusBadge, SideBadge } from "@/components/ui/Badge";

function LivePulse({ active }: { active: boolean }) {
  return (
    <div className="relative flex items-center justify-center w-8 h-8">
      {active && (
        <>
          <motion.div
            className="absolute inset-0 rounded-full bg-success/20"
            animate={{ scale: [1, 2, 1], opacity: [0.5, 0, 0.5] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.div
            className="absolute inset-1 rounded-full bg-success/30"
            animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut", delay: 0.3 }}
          />
        </>
      )}
      <div
        className={cn(
          "w-3 h-3 rounded-full",
          active ? "bg-success" : "bg-danger"
        )}
      />
    </div>
  );
}

export function LivePnLPage() {
  const { data: live, connected, lastUpdate } = useLiveStore();
  const { data: ddHistory, isLoading: ddLoading } = useDrawdownHistory(90);
  const { data: risk } = useRiskMetrics();
  const { data: orders, isLoading: ordersLoading } = useOrders("all", 20);

  const pnlIsPositive = (live?.day_pnl_pct ?? 0) >= 0;

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Live P&L" subtitle="Real-time portfolio performance" />

      <div className="flex-1 p-6 space-y-6">
        {/* Connection status */}
        <div className="flex items-center gap-3">
          <LivePulse active={connected} />
          <div>
            <p className={cn("text-sm font-medium", connected ? "text-success" : "text-danger")}>
              {connected ? "Live Feed Connected" : "Reconnecting…"}
            </p>
            {lastUpdate && (
              <p className="text-xs text-text-muted">
                Last update: {format(lastUpdate, "HH:mm:ss")}
              </p>
            )}
          </div>
          {!connected && <WifiOff className="w-4 h-4 text-danger" />}
          {connected && <Wifi className="w-4 h-4 text-success" />}
        </div>

        {/* Big PnL display */}
        <motion.div
          className={cn(
            "card p-8 text-center relative overflow-hidden",
            pnlIsPositive
              ? "border-success/20 bg-success/5"
              : "border-danger/20 bg-danger/5"
          )}
        >
          {/* Background glow */}
          <div
            className={cn(
              "absolute inset-0 pointer-events-none",
              pnlIsPositive
                ? "bg-gradient-to-b from-success/5 to-transparent"
                : "bg-gradient-to-b from-danger/5 to-transparent"
            )}
          />

          <p className="text-sm text-text-muted uppercase tracking-widest mb-2">
            Today's Return
          </p>

          <div
            className={cn(
              "text-7xl font-mono font-bold tabular-nums leading-none mb-3",
              pnlIsPositive ? "text-success" : "text-danger"
            )}
          >
            {live ? (
              <AnimatedNumber
                value={live.day_pnl_pct}
                format={(v) => formatPct(v)}
                duration={0.8}
              />
            ) : (
              <Skeleton className="h-20 w-48 mx-auto" />
            )}
          </div>

          <div className="flex items-center justify-center gap-2 mb-6">
            {pnlIsPositive ? (
              <TrendingUp className="w-5 h-5 text-success" />
            ) : (
              <TrendingDown className="w-5 h-5 text-danger" />
            )}
            <span className={cn("text-2xl font-mono font-semibold", pnlIsPositive ? "text-success" : "text-danger")}>
              {live ? formatCurrency(live.day_pnl, true) : "—"}
            </span>
          </div>

          {/* Sub stats */}
          <div className="grid grid-cols-3 gap-6 pt-6 border-t border-border/50">
            <div>
              <p className="text-xs text-text-muted mb-1">Portfolio Value</p>
              <p className="text-lg font-mono font-semibold text-text-primary">
                {live ? formatCurrency(live.portfolio_value, true) : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-muted mb-1">Drawdown</p>
              <p className={cn("text-lg font-mono font-semibold", live && live.drawdown_pct > 5 ? "text-danger" : "text-text-primary")}>
                {live ? `-${live.drawdown_pct.toFixed(2)}%` : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-muted mb-1">Positions</p>
              <p className="text-lg font-mono font-semibold text-text-primary">
                {live?.n_positions ?? "—"}
              </p>
            </div>
          </div>
        </motion.div>

        {/* Drawdown history + risk gauge */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="lg:col-span-2 card p-5"
          >
            <h3 className="text-sm font-semibold text-text-primary mb-1">
              Drawdown History
            </h3>
            <p className="text-xs text-text-muted mb-4">
              90-day rolling drawdown from peak
            </p>
            {ddLoading ? (
              <Skeleton className="h-44 w-full" />
            ) : (
              <DrawdownChart
                data={ddHistory ?? []}
                alertLevel={risk?.drawdown_alert}
                limitLevel={risk?.drawdown_limit}
                height={180}
              />
            )}
            <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
              <div className="flex items-center gap-1.5">
                <div className="w-8 h-0.5 bg-warning opacity-60" style={{ borderTop: "1px dashed" }} />
                <span>Alert ({risk?.drawdown_alert}%)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-8 h-0.5 bg-danger opacity-60" style={{ borderTop: "1px dashed" }} />
                <span>Kill switch ({risk?.drawdown_limit}%)</span>
              </div>
            </div>
          </motion.div>

          {/* Risk gauges */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="card p-5 space-y-4"
          >
            <h3 className="text-sm font-semibold text-text-primary">Risk Gauges</h3>

            {risk ? (
              <>
                <RiskGauge
                  label="Drawdown"
                  value={risk.drawdown_pct}
                  max={risk.drawdown_limit}
                  warnAt={risk.drawdown_alert}
                  format={(v) => `${v.toFixed(1)}%`}
                />
                <RiskGauge
                  label="Daily Loss"
                  value={Math.abs(Math.min(0, risk.daily_loss_pct))}
                  max={risk.daily_loss_limit}
                  warnAt={risk.daily_loss_limit * 0.7}
                  format={(v) => `${v.toFixed(1)}%`}
                />
                <div className="pt-3 border-t border-border">
                  <p className="text-xs text-text-muted mb-1">Rolling Sharpe (63d)</p>
                  <p
                    className={cn(
                      "text-2xl font-mono font-semibold",
                      risk.rolling_sharpe_63d >= 1
                        ? "text-success"
                        : risk.rolling_sharpe_63d >= 0
                        ? "text-warning"
                        : "text-danger"
                    )}
                  >
                    {risk.rolling_sharpe_63d.toFixed(2)}
                  </p>
                </div>
              </>
            ) : (
              <div className="space-y-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            )}
          </motion.div>
        </div>

        {/* Recent orders */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card overflow-hidden"
        >
          <div className="px-5 py-4 border-b border-border flex items-center gap-2">
            <Activity className="w-4 h-4 text-text-muted" />
            <h3 className="text-sm font-semibold text-text-primary">Recent Orders</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-elevated/50">
                  <th className="table-header text-left">Ticker</th>
                  <th className="table-header text-left">Side</th>
                  <th className="table-header text-right">Qty</th>
                  <th className="table-header text-right">Price</th>
                  <th className="table-header text-left">Status</th>
                  <th className="table-header text-left">Strategy</th>
                  <th className="table-header text-right">Time</th>
                </tr>
              </thead>
              <tbody>
                {ordersLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="border-b border-border">
                      {Array.from({ length: 7 }).map((_, j) => (
                        <td key={j} className="px-4 py-3">
                          <Skeleton className="h-4 w-full" />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : orders?.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-10 text-center text-text-muted text-sm">
                      No orders today
                    </td>
                  </tr>
                ) : (
                  orders?.map((order, i) => (
                    <AnimatePresence key={order.id}>
                      <motion.tr
                        initial={{ opacity: 0, backgroundColor: "rgba(59,130,246,0.08)" }}
                        animate={{ opacity: 1, backgroundColor: "transparent" }}
                        transition={{ delay: i * 0.03 }}
                        className="table-row"
                      >
                        <td className="table-cell font-semibold">
                          {order.ticker.replace(".NS", "").replace(".BO", "")}
                        </td>
                        <td className="table-cell">
                          <SideBadge side={order.side} />
                        </td>
                        <td className="table-cell text-right">{order.quantity.toLocaleString("en-IN")}</td>
                        <td className="table-cell text-right">
                          ₹{(order.avg_fill_price ?? order.limit_price ?? 0).toFixed(2)}
                        </td>
                        <td className="table-cell">
                          <OrderStatusBadge status={order.status} />
                        </td>
                        <td className="table-cell text-text-secondary text-xs">
                          {order.strategy}
                        </td>
                        <td className="table-cell text-right text-text-muted text-xs">
                          {formatDateTime(order.created_at)}
                        </td>
                      </motion.tr>
                    </AnimatePresence>
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

function RiskGauge({
  label,
  value,
  max,
  warnAt,
  format: fmt,
}: {
  label: string;
  value: number;
  max: number;
  warnAt: number;
  format: (v: number) => string;
}) {
  const pct = Math.min((value / max) * 100, 100);
  const isWarn = value >= warnAt;
  const isDanger = value >= max;

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-text-muted">{label}</span>
        <span
          className={cn(
            "text-xs font-mono font-semibold",
            isDanger ? "text-danger" : isWarn ? "text-warning" : "text-text-primary"
          )}
        >
          {fmt(value)}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-bg-overlay overflow-hidden">
        <motion.div
          className={cn(
            "h-full rounded-full",
            isDanger ? "bg-danger" : isWarn ? "bg-warning" : "bg-primary"
          )}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
      <p className="text-[10px] text-text-muted mt-1">Limit: {fmt(max)}</p>
    </div>
  );
}
