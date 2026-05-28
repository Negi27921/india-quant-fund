import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, TrendingUp, TrendingDown, Search, Filter, RefreshCw, ChevronDown, ChevronUp, BarChart3, ExternalLink, Clock, Award } from "lucide-react";
import { Header } from "@/components/layout/Header";
import {
  useLatestEarnings, useEarningsStats, useEarningsQuarters,
  type EarningsResult,
} from "@/api/earnings-queries";
import { useQueryClient } from "@tanstack/react-query";

// ── Helpers ───────────────────────────────────────────────────────────────────
const numColor = (v: number | null) =>
  v == null ? "var(--text-4)" : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-3)";

const bpsColor = (v: number | null) =>
  v == null ? "var(--text-4)" : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-3)";

function fmt(v: number | null, decimals = 0): string {
  if (v == null) return "—";
  return v.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(v: number | null, sign = true): string {
  if (v == null) return "—";
  return `${sign && v > 0 ? "+" : ""}${v.toFixed(0)}%`;
}

function fmtBps(v: number | null): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(0)} bps`;
}

const RATING_META: Record<string, { color: string; bg: string; border: string; emoji: string }> = {
  Great: { color: "#22c55e", bg: "rgba(34,197,94,0.12)",  border: "rgba(34,197,94,0.35)",  emoji: "🚀" },
  Good:  { color: "#3b82f6", bg: "rgba(59,130,246,0.12)", border: "rgba(59,130,246,0.35)", emoji: "✅" },
  Mixed: { color: "#f59e0b", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.35)", emoji: "⚠️" },
  Poor:  { color: "#ef4444", bg: "rgba(239,68,68,0.12)",  border: "rgba(239,68,68,0.35)",  emoji: "🔴" },
};

// ── Metric row inside card ─────────────────────────────────────────────────────
function MetricRow({
  label, qoq, yoy, current, prevQ, prevY, isBps = false, isMarg = false,
}: {
  label: string;
  qoq: number | null;
  yoy: number | null;
  current: number | null;
  prevQ: number | null;
  prevY: number | null;
  isBps?: boolean;
  isMarg?: boolean;
}) {
  const qoqEl = isBps
    ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: bpsColor(qoq) }}>{fmtBps(qoq)}</span>
    : qoq == null
      ? <span style={{ color: "var(--text-4)", fontSize: 12 }}>—</span>
      : <span style={{ display: "flex", alignItems: "center", gap: 2, fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: numColor(qoq) }}>
          {qoq > 0 ? <TrendingUp style={{ width: 10, height: 10 }} /> : qoq < 0 ? <TrendingDown style={{ width: 10, height: 10 }} /> : null}
          {fmtPct(qoq)}
        </span>;

  const yoyEl = isBps
    ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: bpsColor(yoy) }}>{fmtBps(yoy)}</span>
    : yoy == null
      ? <span style={{ color: "var(--text-4)", fontSize: 12 }}>—</span>
      : <span style={{ display: "flex", alignItems: "center", gap: 2, fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: numColor(yoy) }}>
          {yoy > 0 ? <TrendingUp style={{ width: 10, height: 10 }} /> : yoy < 0 ? <TrendingDown style={{ width: 10, height: 10 }} /> : null}
          {fmtPct(yoy)}
        </span>;

  const fmtVal = (v: number | null) =>
    v == null ? "—" : isMarg ? `${fmt(v, 1)}%` : fmt(v, 0);

  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      <td style={{ padding: "7px 14px", fontWeight: 700, fontSize: 13, color: "var(--text-1)", fontFamily: "var(--font-body)", whiteSpace: "nowrap" }}>{label}</td>
      <td style={{ padding: "7px 14px", textAlign: "center" }}>{qoqEl}</td>
      <td style={{ padding: "7px 14px", textAlign: "center" }}>{yoyEl}</td>
      <td style={{ padding: "7px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--text-1)" }}>{fmtVal(current)}</td>
      <td style={{ padding: "7px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtVal(prevQ)}</td>
      <td style={{ padding: "7px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtVal(prevY)}</td>
    </tr>
  );
}

// ── Mini sparkline bar chart ──────────────────────────────────────────────────
function MiniBars({ values, color }: { values: (number | null)[]; color: string }) {
  const valid = values.map(v => v ?? 0);
  const max = Math.max(...valid, 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 36 }}>
      {valid.map((v, i) => (
        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
          <div style={{
            width: "100%",
            height: `${Math.max(4, (v / max) * 36)}px`,
            background: i === valid.length - 1 ? color : `${color}55`,
            borderRadius: 2,
            transition: "height 400ms ease",
          }} />
        </div>
      ))}
    </div>
  );
}

// ── Earnings Card ─────────────────────────────────────────────────────────────
function EarningsCard({ result, index }: { result: EarningsResult; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const rating = result.pulse_rating ?? "Mixed";
  const rm = RATING_META[rating] ?? RATING_META.Mixed;

  // Derive quarter label from column headers
  const q = result.quarter ?? "";
  const qNum = q.match(/Q(\d)/)?.[1];
  const fy   = q.match(/FY(\d+)/)?.[1];
  const monthMap: Record<string, string> = { "1": "Jun", "2": "Sep", "3": "Dec", "4": "Mar" };
  const curLabel  = qNum ? `${monthMap[qNum] ?? ""}\'${fy ?? ""}` : "Current";
  const prevQNum  = qNum ? String((Number(qNum) === 1 ? 4 : Number(qNum) - 1)) : null;
  const prevQFY   = qNum && Number(qNum) === 1 ? String(Number(fy) - 1) : fy;
  const prevQLabel = prevQNum ? `${monthMap[prevQNum] ?? ""}\'${prevQFY ?? ""}` : "Prev Q";
  const prevYLabel = qNum ? `${monthMap[qNum] ?? ""}\'${String(Number(fy) - 1) ?? ""}` : "Prev Y";

  const mktCapFmt = result.market_cap_cr
    ? result.market_cap_cr >= 100_000
      ? `${(result.market_cap_cr / 100_000).toFixed(1)}L Cr`
      : result.market_cap_cr >= 1000
        ? `${(result.market_cap_cr / 1000).toFixed(1)}K Cr`
        : `${result.market_cap_cr.toFixed(0)} Cr`
    : null;

  const capTag = result.market_cap_cr
    ? result.market_cap_cr >= 200_000 ? "Large-Cap"
      : result.market_cap_cr >= 50_000 ? "Mid-Cap"
        : "Small-Cap"
    : null;

  const filedAgo = result.filed_at
    ? (() => {
        const diff = Date.now() - new Date(result.filed_at).getTime();
        const h = Math.floor(diff / 3_600_000);
        const d = Math.floor(diff / 86_400_000);
        if (h < 1) return "just now";
        if (h < 24) return `${h}h ago`;
        return `${d}d ago`;
      })()
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.05, 0.5), duration: 0.22 }}
      style={{
        background: "var(--surface)",
        border: `1px solid var(--border)`,
        borderTop: `3px solid ${rm.color}`,
        borderRadius: 14,
        overflow: "hidden",
      }}
    >
      {/* Card header */}
      <div style={{ padding: "14px 18px 10px" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 10 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Company + ticker */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 18, fontWeight: 800, color: "var(--text-1)", fontFamily: "var(--font-heading)", letterSpacing: "-0.02em", lineHeight: 1.2 }}>
                {result.company ?? result.ticker}
              </span>
              <span style={{
                fontSize: 10, fontWeight: 800, letterSpacing: "0.06em",
                padding: "2px 8px", borderRadius: 5,
                background: "var(--surface-3)", border: "1px solid var(--border)",
                color: "var(--text-2)", fontFamily: "var(--font-mono)",
              }}>
                {result.ticker}
              </span>
            </div>
            {/* Sector */}
            {result.sector && (
              <div style={{ fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-body)", marginTop: 3 }}>
                {result.sector}
              </div>
            )}
          </div>

          {/* Rating badge */}
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0,
          }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
              {result.quarter}
            </div>
            <div style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "4px 12px", borderRadius: 8,
              background: rm.bg, border: `1px solid ${rm.border}`,
            }}>
              <span style={{ fontSize: 13 }}>{rm.emoji}</span>
              <span style={{ fontFamily: "var(--font-heading)", fontSize: 16, fontWeight: 800, color: rm.color }}>
                {rating}
              </span>
            </div>
          </div>
        </div>

        {/* Market info strip */}
        {(result.cmp || result.pe_ratio || mktCapFmt) && (
          <div style={{
            display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
            padding: "6px 10px", background: "var(--surface-2)", borderRadius: 8,
            marginBottom: 10,
          }}>
            {result.cmp && (
              <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-2)", fontWeight: 700 }}>
                CMP: <b style={{ color: "var(--text-1)" }}>₹{fmt(result.cmp)}</b>
              </span>
            )}
            {result.pe_ratio && (
              <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-2)" }}>
                P/E: <b style={{ color: "var(--text-1)" }}>{result.pe_ratio.toFixed(1)}</b>
              </span>
            )}
            {mktCapFmt && (
              <span style={{
                fontSize: 9.5, fontWeight: 700, color: "var(--text-3)",
                background: "var(--surface-3)", padding: "1px 7px", borderRadius: 4,
              }}>
                {capTag} ({mktCapFmt})
              </span>
            )}
            {filedAgo && (
              <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 3, fontSize: 9.5, color: "var(--text-4)" }}>
                <Clock style={{ width: 9, height: 9 }} /> {filedAgo}
              </span>
            )}
          </div>
        )}

        {/* Metrics table */}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--surface-3)", borderBottom: "1px solid var(--border)" }}>
                {["Metric", "QoQ", "YoY", curLabel, prevQLabel, prevYLabel].map(h => (
                  <th key={h} style={{
                    padding: "5px 14px", fontSize: 9, fontWeight: 700,
                    color: "var(--text-3)", letterSpacing: "0.08em",
                    fontFamily: "var(--font-body)", textTransform: "uppercase",
                    textAlign: h === "Metric" ? "left" : h === curLabel || h === prevQLabel || h === prevYLabel ? "right" : "center",
                    whiteSpace: "nowrap",
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <MetricRow label="Sales" qoq={result.sales_qoq_pct} yoy={result.sales_yoy_pct}
                current={result.sales_cr} prevQ={result.sales_prev_q_cr} prevY={result.sales_prev_y_cr} />
              <MetricRow label="Other Inc." qoq={null} yoy={null}
                current={result.other_income_cr} prevQ={null} prevY={null} />
              <MetricRow label="OP" qoq={result.op_qoq_pct} yoy={result.op_yoy_pct}
                current={result.op_cr} prevQ={result.op_prev_q_cr} prevY={result.op_prev_y_cr} />
              <MetricRow label="OPM" qoq={result.opm_qoq_bps} yoy={result.opm_yoy_bps}
                current={result.opm_pct} prevQ={result.opm_prev_q_pct} prevY={result.opm_prev_y_pct}
                isBps isMarg />
              <MetricRow label="PAT" qoq={result.pat_qoq_pct} yoy={result.pat_yoy_pct}
                current={result.pat_cr} prevQ={result.pat_prev_q_cr} prevY={result.pat_prev_y_cr} />
              <MetricRow label="EPS" qoq={result.eps_qoq_pct} yoy={result.eps_yoy_pct}
                current={result.eps} prevQ={result.eps_prev_q} prevY={result.eps_prev_y} />
            </tbody>
          </table>
        </div>

        {/* Expand toggle */}
        <button
          onClick={() => setExpanded(x => !x)}
          style={{
            marginTop: 8, width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 4,
            background: "none", border: "none", cursor: "pointer", color: "var(--text-4)",
            fontSize: 10, fontFamily: "var(--font-body)", padding: "4px 0",
          }}
        >
          {expanded ? <ChevronUp style={{ width: 12, height: 12 }} /> : <ChevronDown style={{ width: 12, height: 12 }} />}
          {expanded ? "Less" : "Trend charts"}
        </button>
      </div>

      {/* Expanded: mini trend charts */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{
              padding: "12px 18px 16px",
              borderTop: "1px solid var(--border)",
              display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14,
            }}>
              {[
                { label: "REVENUE", color: "#818cf8",
                  values: [result.sales_prev_y_cr, null, null, result.sales_prev_q_cr, result.sales_cr] },
                { label: "PAT", color: "#34d399",
                  values: [result.pat_prev_y_cr, null, null, result.pat_prev_q_cr, result.pat_cr] },
                { label: "EPS", color: "#a78bfa",
                  values: [result.eps_prev_y, null, null, result.eps_prev_q, result.eps] },
              ].map(chart => (
                <div key={chart.label} style={{
                  background: "var(--surface-2)", borderRadius: 8, padding: "8px 10px",
                  border: "1px solid var(--border)",
                }}>
                  <div style={{ fontSize: 8.5, fontWeight: 700, color: chart.color, letterSpacing: "0.1em", marginBottom: 6 }}>
                    {chart.label}
                    {chart.values[4] != null && (
                      <span style={{ color: "var(--text-3)", marginLeft: 6, fontWeight: 400, fontFamily: "var(--font-mono)" }}>
                        {chart.label === "EPS" ? chart.values[4]?.toFixed(1) : fmt(chart.values[4])}
                        {chart.label === "EPS" ? "" : " Cr"}
                      </span>
                    )}
                  </div>
                  <MiniBars values={chart.values} color={chart.color} />
                </div>
              ))}
            </div>

            {/* Source + confidence */}
            <div style={{ padding: "4px 18px 12px", display: "flex", gap: 10, alignItems: "center" }}>
              {result.source && (
                <span style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
                  Source: {result.source === "telegram_ocr" ? "Telegram OCR" : result.source === "bse_xbrl" ? "BSE XBRL" : result.source}
                </span>
              )}
              {result.confidence_score != null && (
                <span style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
                  · Confidence: {(result.confidence_score * 100).toFixed(0)}%
                </span>
              )}
              <a
                href={`https://www.bseindia.com/stock-share-price/${result.ticker}`}
                target="_blank" rel="noopener noreferrer"
                style={{ marginLeft: "auto", fontSize: 9, color: "var(--accent)", display: "flex", alignItems: "center", gap: 3, textDecoration: "none" }}
              >
                <ExternalLink style={{ width: 9, height: 9 }} /> BSE
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────
function StatsBar() {
  const { data: stats } = useEarningsStats();
  if (!stats) return null;

  const ratingOrder = ["Great", "Good", "Mixed", "Poor"];
  return (
    <div style={{
      display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap",
    }}>
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 16px", minWidth: 120 }}>
        <div style={{ fontSize: 10, color: "var(--text-3)", letterSpacing: "0.06em", marginBottom: 4 }}>TOTAL RESULTS</div>
        <div style={{ fontSize: 20, fontWeight: 800, color: "var(--accent)", fontFamily: "var(--font-mono)" }}>{stats.total}</div>
      </div>
      {ratingOrder.map(r => {
        const count = stats.by_rating[r] ?? 0;
        if (!count) return null;
        const rm = RATING_META[r];
        return (
          <div key={r} style={{ background: rm.bg, border: `1px solid ${rm.border}`, borderRadius: 10, padding: "10px 16px", minWidth: 100 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: rm.color, letterSpacing: "0.06em", marginBottom: 4 }}>{r.toUpperCase()}</div>
            <div style={{ fontSize: 20, fontWeight: 800, color: rm.color, fontFamily: "var(--font-mono)" }}>{count}</div>
          </div>
        );
      })}
      {stats.latest_quarter && (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 16px", marginLeft: "auto" }}>
          <div style={{ fontSize: 10, color: "var(--text-3)", letterSpacing: "0.06em", marginBottom: 4 }}>LATEST</div>
          <div style={{ fontSize: 16, fontWeight: 800, color: "var(--text-1)", fontFamily: "var(--font-mono)" }}>{stats.latest_quarter}</div>
        </div>
      )}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div style={{ textAlign: "center", padding: 80 }}>
      <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-2)", marginBottom: 8 }}>
        No earnings results yet
      </div>
      <div style={{ fontSize: 12, color: "var(--text-4)", maxWidth: 420, margin: "0 auto", lineHeight: 1.6, fontFamily: "var(--font-body)" }}>
        Start the earnings listener to populate this feed:
      </div>
      <div style={{
        marginTop: 16, padding: "10px 16px",
        background: "var(--surface-2)", border: "1px solid var(--border)",
        borderRadius: 8, fontFamily: "var(--font-mono)", fontSize: 11.5,
        color: "var(--text-2)", display: "inline-block", textAlign: "left",
      }}>
        python scripts/earnings_listener.py
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
        Or run backfill: <code>python scripts/earnings_listener.py --backfill 500</code>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export function EarningsPulsePage() {
  const [search, setSearch] = useState("");
  const [ratingFilter, setRatingFilter] = useState<string>("");
  const [quarterFilter, setQuarterFilter] = useState<string>("");
  const [limit, setLimit] = useState(20);

  const qc = useQueryClient();
  const { data: quarters = [] } = useEarningsQuarters();

  const { data: results = [], isLoading, isFetching } = useLatestEarnings({
    limit,
    rating: ratingFilter || undefined,
    quarter: quarterFilter || undefined,
    search: search.trim() || undefined,
  });

  const handleRefresh = () => {
    qc.invalidateQueries({ queryKey: ["earnings"] });
  };

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header title="Earnings Pulse" />

      <div style={{ padding: "20px 24px", maxWidth: 1200, margin: "0 auto" }}>

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20, gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 26, fontWeight: 700, color: "var(--text-1)", margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
              <Zap style={{ width: 24, height: 24, color: "#f59e0b" }} />
              Earnings Pulse
            </h1>
            <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 4, fontFamily: "var(--font-body)" }}>
              Live quarterly results · sourced from @earnings_pulse via Gemini Flash OCR
              {isFetching && <span style={{ color: "var(--amber)", marginLeft: 8 }}>· Refreshing...</span>}
            </div>
          </div>
          <button
            onClick={handleRefresh}
            style={{
              display: "flex", alignItems: "center", gap: 6, padding: "8px 16px",
              borderRadius: 9, background: "var(--surface)", border: "1px solid var(--border)",
              cursor: "pointer", color: "var(--text-2)", fontFamily: "var(--font-body)",
              fontSize: 12, fontWeight: 600,
            }}
          >
            <RefreshCw style={{ width: 13, height: 13 }} /> Refresh
          </button>
        </div>

        {/* Stats */}
        <StatsBar />

        {/* Filters */}
        <div style={{
          display: "flex", gap: 10, marginBottom: 20, alignItems: "center",
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 12, padding: "10px 14px", flexWrap: "wrap",
        }}>
          <Filter style={{ width: 13, height: 13, color: "var(--text-3)", flexShrink: 0 }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.06em" }}>FILTERS</span>

          {/* Search */}
          <div style={{ position: "relative" }}>
            <Search style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", width: 11, height: 11, color: "var(--text-4)" }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Ticker / company…"
              style={{
                paddingLeft: 26, paddingRight: 8, paddingTop: 5, paddingBottom: 5,
                background: "var(--surface-2)", border: "1px solid var(--border)",
                borderRadius: 7, color: "var(--text-1)", fontFamily: "var(--font-mono)",
                fontSize: 12, outline: "none", width: 150,
              }}
            />
          </div>

          {/* Rating filter */}
          <div style={{ display: "flex", gap: 4 }}>
            {["", "Great", "Good", "Mixed", "Poor"].map(r => {
              const rm = r ? RATING_META[r] : null;
              const active = ratingFilter === r;
              return (
                <button key={r} onClick={() => setRatingFilter(r)}
                  style={{
                    fontSize: 10, padding: "4px 10px", borderRadius: 6, cursor: "pointer",
                    background: active ? (rm?.bg ?? "var(--accent-dim)") : "var(--surface-2)",
                    color: active ? (rm?.color ?? "var(--accent)") : "var(--text-3)",
                    border: `1px solid ${active ? (rm?.border ?? "var(--accent-border)") : "var(--border)"}`,
                    fontFamily: "var(--font-body)", fontWeight: active ? 700 : 500,
                  }}>
                  {r || "All"}
                </button>
              );
            })}
          </div>

          {/* Quarter filter */}
          {quarters.length > 0 && (
            <select
              value={quarterFilter}
              onChange={e => setQuarterFilter(e.target.value)}
              style={{
                background: "var(--surface-2)", border: "1px solid var(--border)",
                borderRadius: 7, padding: "4px 8px", color: "var(--text-1)",
                fontFamily: "var(--font-mono)", fontSize: 11, outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="">All Quarters</option>
              {quarters.map(q => <option key={q} value={q}>{q}</option>)}
            </select>
          )}

          {/* Limit */}
          <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
            {[20, 50, 100].map(n => (
              <button key={n} onClick={() => setLimit(n)}
                style={{
                  fontSize: 10, padding: "3px 9px", borderRadius: 6, cursor: "pointer",
                  background: limit === n ? "var(--accent-dim)" : "var(--surface-2)",
                  color: limit === n ? "var(--accent)" : "var(--text-3)",
                  border: `1px solid ${limit === n ? "var(--accent-border)" : "var(--border)"}`,
                  fontFamily: "var(--font-body)", fontWeight: limit === n ? 700 : 400,
                }}>
                {n}
              </button>
            ))}
          </div>
        </div>

        {/* Cards grid */}
        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
            <div style={{ fontSize: 14, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
              Loading earnings results...
            </div>
          </div>
        ) : results.length === 0 ? (
          <EmptyState />
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(560px, 1fr))", gap: 16 }}>
            {results.map((r, i) => (
              <EarningsCard key={r.id} result={r} index={i} />
            ))}
          </div>
        )}

        {/* Footer */}
        {results.length > 0 && (
          <div style={{ marginTop: 16, textAlign: "center" }}>
            <div style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-body)", marginBottom: 8 }}>
              Showing {results.length} results · ⚠ Mid Accuracy — OCR via Gemini Flash. Verify with official BSE filings.
            </div>
            {results.length >= limit && (
              <button
                onClick={() => setLimit(l => l + 20)}
                style={{
                  padding: "7px 20px", borderRadius: 8, cursor: "pointer",
                  background: "var(--surface)", border: "1px solid var(--border)",
                  color: "var(--text-2)", fontFamily: "var(--font-body)", fontSize: 12,
                }}
              >
                Load more
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
