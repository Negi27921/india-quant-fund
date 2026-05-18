import { motion } from "framer-motion";
import { Shield, AlertTriangle, CheckCircle, XCircle, Info } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { KillSwitchBanner } from "@/components/ui/KillSwitchBanner";
import { StatCard } from "@/components/ui/StatCard";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";
import { useRiskMetrics, useRiskLimits, useDrawdownHistory, useKillSwitchStatus } from "@/api/queries";
import { formatPct } from "@/lib/utils";

function LimitRow({ label, value, limit, unit = "%" }: { label: string; value: number; limit: number; unit?: string; }) {
  const pct = Math.min((value / limit) * 100, 100);
  const isDanger = value >= limit;
  const isWarn   = value >= limit * 0.75;
  const valColor = isDanger ? "var(--red)" : isWarn ? "var(--amber)" : "var(--text-1)";
  const barColor = isDanger ? "var(--red)" : isWarn ? "var(--amber)" : "var(--accent)";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ fontSize: 13, color: "var(--text-1)", fontFamily: "var(--font-body)" }}>{label}</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 13, fontFamily: "var(--font-mono)", fontWeight: 600, color: valColor }}>
              {value.toFixed(2)}{unit}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
              / {limit}{unit}
            </span>
          </div>
        </div>
        <div style={{ height: 6, borderRadius: 9999, background: "var(--surface-3)", overflow: "hidden" }}>
          <motion.div
            style={{ height: "100%", borderRadius: 9999, background: barColor }}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.7, ease: "easeOut" }}
          />
        </div>
      </div>
      {isDanger ? (
        <XCircle style={{ width: 16, height: 16, color: "var(--red)", flexShrink: 0 }} />
      ) : isWarn ? (
        <AlertTriangle style={{ width: 16, height: 16, color: "var(--amber)", flexShrink: 0 }} />
      ) : (
        <CheckCircle style={{ width: 16, height: 16, color: "var(--green)", flexShrink: 0 }} />
      )}
    </div>
  );
}

export function RiskPage() {
  const { data: risk, isLoading: riskLoading } = useRiskMetrics();
  const { data: limits } = useRiskLimits();
  const { data: dd, isLoading: ddLoading } = useDrawdownHistory(90);
  const { data: ks } = useKillSwitchStatus();

  const ksActive = ks?.active;

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <KillSwitchBanner />
      <Header title="Risk" subtitle="Live risk metrics and limit utilization" />

      <div style={{ flex: 1, padding: 24, display: "flex", flexDirection: "column", gap: 24, overflowY: "auto" }}>

        {/* Kill switch status */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          style={{
            display: "flex", alignItems: "center", gap: 16, padding: 20,
            borderRadius: 8,
            border: `1px solid ${ksActive ? "var(--red-border)" : "var(--green-border)"}`,
            background: ksActive ? "var(--red-dim)" : "var(--green-dim)",
          }}
        >
          {ksActive
            ? <XCircle style={{ width: 32, height: 32, color: "var(--red)", flexShrink: 0 }} />
            : <CheckCircle style={{ width: 32, height: 32, color: "var(--green)", flexShrink: 0 }} />
          }
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 15, fontWeight: 600, fontFamily: "var(--font-body)", color: ksActive ? "var(--red)" : "var(--green)" }}>
              Kill Switch: {ksActive ? "ACTIVE — Trading Halted" : "Inactive — Normal Operation"}
            </p>
            {ks?.reason && (
              <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 2, fontFamily: "var(--font-body)" }}>{ks.reason}</p>
            )}
          </div>
          <span style={{
            fontSize: 9, fontWeight: 800, letterSpacing: "0.12em",
            padding: "3px 10px", borderRadius: 9999,
            background: ksActive ? "var(--red)" : "var(--green)",
            color: "#fff", fontFamily: "var(--font-body)",
          }}>
            {ksActive ? "HALTED" : "LIVE"}
          </span>
        </motion.div>

        {/* KPI grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
          {riskLoading
            ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
            : (
              <>
                <StatCard
                  label="Current Drawdown"
                  value={<span style={{ color: "var(--red)" }}>{formatPct(-(risk?.drawdown_pct ?? 0))}</span>}
                  subValue={`Alert: ${risk?.drawdown_alert}% | Limit: ${risk?.drawdown_limit}%`}
                  variant={(risk?.drawdown_pct ?? 0) >= (risk?.drawdown_limit ?? 12) ? "danger" : (risk?.drawdown_pct ?? 0) >= (risk?.drawdown_alert ?? 8) ? "warning" : "default"}
                  delay={0}
                />
                <StatCard
                  label="Daily P&L"
                  value={<span style={{ color: (risk?.daily_loss_pct ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>{formatPct(risk?.daily_loss_pct ?? 0)}</span>}
                  subValue={`Limit: -${risk?.daily_loss_limit}%`}
                  delay={0.05}
                />
                <StatCard
                  label="Sharpe (63d)"
                  value={
                    <span style={{ color: (risk?.rolling_sharpe_63d ?? 0) >= 1 ? "var(--green)" : (risk?.rolling_sharpe_63d ?? 0) >= 0 ? "var(--amber)" : "var(--red)" }}>
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
            )
          }
        </div>

        {/* Charts + limits */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Drawdown chart */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card"
            style={{ padding: 20 }}
          >
            <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", fontFamily: "var(--font-body)", marginBottom: 4 }}>
              Drawdown History
            </h3>
            <p style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)", marginBottom: 16 }}>
              90-day peak-to-trough
            </p>
            {ddLoading
              ? <Skeleton className="h-44 w-full" />
              : <DrawdownChart data={dd ?? []} alertLevel={risk?.drawdown_alert} limitLevel={risk?.drawdown_limit} />
            }
          </motion.div>

          {/* Limit utilization */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="card"
            style={{ padding: 20 }}
          >
            <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", fontFamily: "var(--font-body)", marginBottom: 4 }}>
              Limit Utilization
            </h3>
            <p style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)", marginBottom: 16 }}>
              Current usage vs configured limits
            </p>
            {risk ? (
              <div>
                <LimitRow label="Portfolio Drawdown" value={Math.abs(risk.drawdown_pct)} limit={risk.drawdown_limit} />
                <LimitRow label="Daily Loss" value={Math.abs(Math.min(0, risk.daily_loss_pct))} limit={risk.daily_loss_limit} />
                <LimitRow label="Max Position Size" value={risk.position_utilization_pct ?? 0} limit={risk.max_position_pct} />
                <LimitRow label="Max Sector Exposure" value={risk.sector_utilization_pct ?? 0} limit={risk.max_sector_pct} />
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
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
            className="card"
            style={{ padding: 20 }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Shield style={{ width: 16, height: 16, color: "var(--text-3)" }} />
              <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", fontFamily: "var(--font-body)" }}>
                Risk Configuration
              </h3>
              <div style={{ flex: 1 }} />
              <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
                <Info style={{ width: 12, height: 12 }} />
                <span>From risk_limits.yaml</span>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
              {Object.entries(limits).map(([section, vals]) => (
                <div key={section} style={{ background: "var(--surface-2)", borderRadius: 8, padding: 16 }}>
                  <p style={{
                    fontSize: 10, color: "var(--text-3)", textTransform: "uppercase",
                    letterSpacing: "0.12em", fontWeight: 700, fontFamily: "var(--font-body)", marginBottom: 12,
                  }}>
                    {section}
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {Object.entries(vals as Record<string, number>).map(([k, v]) => (
                      <div key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
                          {k.replace(/_/g, " ")}
                        </span>
                        <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-1)" }}>{v}</span>
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
