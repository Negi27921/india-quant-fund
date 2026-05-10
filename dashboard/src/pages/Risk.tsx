import { motion } from "framer-motion";
import { Shield, AlertTriangle, CheckCircle, XCircle, Info } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { StatCard } from "@/components/ui/StatCard";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { useRiskMetrics, useRiskLimits, useDrawdownHistory, useKillSwitchStatus } from "@/api/queries";
import { formatPct } from "@/lib/utils";
import { cn } from "@/lib/utils";

function LimitRow({
  label,
  value,
  limit,
  unit = "%",
}: {
  label: string;
  value: number;
  limit: number;
  unit?: string;
}) {
  const pct = Math.min((value / limit) * 100, 100);
  const isDanger = value >= limit;
  const isWarn = value >= limit * 0.75;

  return (
    <div className="flex items-center gap-4 py-3 border-b border-border last:border-0">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-sm text-text-primary">{label}</span>
          <div className="flex items-center gap-2">
            <span className={cn("text-sm font-mono font-semibold", isDanger ? "text-danger" : isWarn ? "text-warning" : "text-text-primary")}>
              {value.toFixed(2)}{unit}
            </span>
            <span className="text-xs text-text-muted">/ {limit}{unit}</span>
          </div>
        </div>
        <div className="h-1.5 rounded-full bg-bg-overlay overflow-hidden">
          <motion.div
            className={cn("h-full rounded-full transition-colors", isDanger ? "bg-danger" : isWarn ? "bg-warning" : "bg-primary")}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.7, ease: "easeOut" }}
          />
        </div>
      </div>
      {isDanger ? (
        <XCircle className="w-4 h-4 text-danger shrink-0" />
      ) : isWarn ? (
        <AlertTriangle className="w-4 h-4 text-warning shrink-0" />
      ) : (
        <CheckCircle className="w-4 h-4 text-success shrink-0" />
      )}
    </div>
  );
}

export function RiskPage() {
  const { data: risk, isLoading: riskLoading } = useRiskMetrics();
  const { data: limits } = useRiskLimits();
  const { data: dd, isLoading: ddLoading } = useDrawdownHistory(90);
  const { data: ks } = useKillSwitchStatus();

  return (
    <div className="flex flex-col min-h-screen">
      <KillSwitchBanner />
      <Header title="Risk" subtitle="Live risk metrics and limit utilization" />

      <div className="flex-1 p-6 space-y-6">
        {/* Kill switch status */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className={cn(
            "card p-5 border flex items-center gap-4",
            ks?.active
              ? "border-danger/30 bg-danger/5"
              : "border-success/20 bg-success/5"
          )}
        >
          {ks?.active ? (
            <XCircle className="w-8 h-8 text-danger shrink-0" />
          ) : (
            <CheckCircle className="w-8 h-8 text-success shrink-0" />
          )}
          <div className="flex-1">
            <p className={cn("text-base font-semibold", ks?.active ? "text-danger" : "text-success")}>
              Kill Switch: {ks?.active ? "ACTIVE — Trading Halted" : "Inactive — Normal Operation"}
            </p>
            {ks?.reason && (
              <p className="text-sm text-text-muted mt-0.5">{ks.reason}</p>
            )}
          </div>
          <Badge variant={ks?.active ? "danger" : "success"} dot>
            {ks?.active ? "HALTED" : "LIVE"}
          </Badge>
        </motion.div>

        {/* KPI grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {riskLoading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
              <StatCard
                label="Current Drawdown"
                value={<span className="text-danger">{formatPct(-(risk?.drawdown_pct ?? 0))}</span>}
                subValue={`Alert: ${risk?.drawdown_alert}% | Limit: ${risk?.drawdown_limit}%`}
                variant={risk?.drawdown_pct ?? 0 >= (risk?.drawdown_limit ?? 12) ? "danger" : risk?.drawdown_pct ?? 0 >= (risk?.drawdown_alert ?? 8) ? "warning" : "default"}
                delay={0}
              />
              <StatCard
                label="Daily P&L"
                value={<span className={risk?.daily_loss_pct ?? 0 >= 0 ? "text-success" : "text-danger"}>{formatPct(risk?.daily_loss_pct ?? 0)}</span>}
                subValue={`Limit: -${risk?.daily_loss_limit}%`}
                delay={0.05}
              />
              <StatCard
                label="Sharpe (63d)"
                value={
                  <span className={
                    (risk?.rolling_sharpe_63d ?? 0) >= 1 ? "text-success" :
                    (risk?.rolling_sharpe_63d ?? 0) >= 0 ? "text-warning" : "text-danger"
                  }>
                    {(risk?.rolling_sharpe_63d ?? 0).toFixed(2)}
                  </span>
                }
                subValue="Annualized, RFR 6.5%"
                delay={0.1}
              />
              <StatCard
                label="Max Position"
                value={`${risk?.max_position_pct ?? 0}%`}
                subValue={`Sector cap: ${risk?.max_sector_pct ?? 0}%`}
                delay={0.15}
              />
            </>
          )}
        </div>

        {/* Charts + limits */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Drawdown chart */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card p-5"
          >
            <h3 className="text-sm font-semibold text-text-primary mb-1">Drawdown History</h3>
            <p className="text-xs text-text-muted mb-4">90-day peak-to-trough</p>
            {ddLoading ? (
              <Skeleton className="h-44 w-full" />
            ) : (
              <DrawdownChart
                data={dd ?? []}
                alertLevel={risk?.drawdown_alert}
                limitLevel={risk?.drawdown_limit}
              />
            )}
          </motion.div>

          {/* Limit utilization */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="card p-5"
          >
            <h3 className="text-sm font-semibold text-text-primary mb-1">Limit Utilization</h3>
            <p className="text-xs text-text-muted mb-4">Current usage vs configured limits</p>
            {risk ? (
              <div>
                <LimitRow
                  label="Portfolio Drawdown"
                  value={Math.abs(risk.drawdown_pct)}
                  limit={risk.drawdown_limit}
                />
                <LimitRow
                  label="Daily Loss"
                  value={Math.abs(Math.min(0, risk.daily_loss_pct))}
                  limit={risk.daily_loss_limit}
                />
                <LimitRow
                  label="Max Position Size"
                  value={risk.position_utilization_pct ?? 0}
                  limit={risk.max_position_pct}
                />
                <LimitRow
                  label="Max Sector Exposure"
                  value={risk.sector_utilization_pct ?? 0}
                  limit={risk.max_sector_pct}
                />
              </div>
            ) : (
              <div className="space-y-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            )}
          </motion.div>
        </div>

        {/* Full limits config */}
        {limits && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="card p-5"
          >
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4 text-text-muted" />
              <h3 className="text-sm font-semibold text-text-primary">Risk Configuration</h3>
              <div className="flex-1" />
              <div className="flex items-center gap-1 text-xs text-text-muted">
                <Info className="w-3 h-3" />
                <span>From risk_limits.yaml</span>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(limits).map(([section, vals]) => (
                <div key={section} className="bg-bg-elevated rounded-lg p-4">
                  <p className="text-xs text-text-muted uppercase tracking-wider font-medium mb-3 capitalize">
                    {section}
                  </p>
                  <div className="space-y-2">
                    {Object.entries(vals as Record<string, number>).map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between">
                        <span className="text-xs text-text-muted capitalize">
                          {k.replace(/_/g, " ")}
                        </span>
                        <span className="text-xs font-mono text-text-primary">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
