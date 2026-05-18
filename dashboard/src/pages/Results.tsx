import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Trophy, Star, ThumbsUp, Minus, TrendingDown as WeakIcon,
  ExternalLink, FileText, RefreshCw, Search,
  Clock, BarChart3,
  Loader2, LayoutGrid, List,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { useQuarterlyResults, type QuarterlyResult, type Rating } from "@/api/market-queries";

// ── Rating config ─────────────────────────────────────────────────────────────
const RATING_CONFIG: Record<Rating, {
  color: string; bg: string; border: string;
  icon: React.ReactNode; glow: string; rank: number;
}> = {
  Excellent: { color: "#10b981", bg: "rgba(16,185,129,0.10)", border: "rgba(16,185,129,0.28)", icon: <Trophy style={{ width: 11, height: 11 }} />, glow: "0 0 24px rgba(16,185,129,0.22)", rank: 1 },
  Great:     { color: "#34d399", bg: "rgba(52,211,153,0.08)", border: "rgba(52,211,153,0.24)", icon: <Star style={{ width: 11, height: 11 }} />,   glow: "0 0 18px rgba(52,211,153,0.18)", rank: 2 },
  Good:      { color: "#60a5fa", bg: "rgba(96,165,250,0.09)", border: "rgba(96,165,250,0.24)", icon: <ThumbsUp style={{ width: 11, height: 11 }} />, glow: "0 0 14px rgba(96,165,250,0.14)", rank: 3 },
  Ok:        { color: "#f59e0b", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.24)", icon: <Minus style={{ width: 11, height: 11 }} />,   glow: "none", rank: 4 },
  Weak:      { color: "#f87171", bg: "rgba(248,113,113,0.08)", border: "rgba(248,113,113,0.24)", icon: <WeakIcon style={{ width: 11, height: 11 }} />, glow: "none", rank: 5 },
};

const RATINGS: Rating[] = ["Excellent", "Great", "Good", "Ok", "Weak"];

// ── Change formatter ──────────────────────────────────────────────────────────
function ChangePct({ v, isBps = false }: { v: number | null; isBps?: boolean }) {
  if (v === null) return <span style={{ color: "var(--text-4)", fontSize: 12 }}>—</span>;
  const pos = v >= 0;
  const label = isBps
    ? `${v > 0 ? "+" : ""}${v.toFixed(0)} bps`
    : `${v > 0 ? "+" : ""}${v.toFixed(0)}%`;
  return (
    <span style={{
      fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700,
      color: pos ? "#10b981" : "#f87171",
      display: "inline-flex", alignItems: "center", gap: 2,
    }}>
      {label}
    </span>
  );
}

// ── Mini inline bar chart (SVG) ───────────────────────────────────────────────
function MiniBarChart({
  values, labels, color, title, range,
}: {
  values: number[]; labels: string[]; color: string;
  title: string; range?: string;
}) {
  const maxV = Math.max(...values.map(Math.abs), 1);
  const w = 16, gap = 3, totalW = values.length * (w + gap) - gap;
  const chartH = 40;

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
        <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.07em", textTransform: "uppercase" }}>{title}</span>
        {range && <span style={{ fontSize: 8, color: color, fontFamily: "var(--font-mono)", fontWeight: 700 }}>{range}</span>}
      </div>
      <svg width="100%" viewBox={`0 0 ${totalW} ${chartH + 14}`} style={{ overflow: "visible", display: "block" }}>
        {values.map((v, i) => {
          const barH = Math.max(3, (Math.abs(v) / maxV) * chartH);
          const isLast = i === values.length - 1;
          const x = i * (w + gap);
          const y = chartH - barH;
          return (
            <g key={i}>
              <rect x={x} y={y} width={w} height={barH} rx={2}
                fill={isLast ? color : `${color}44`} />
              {isLast && (
                <text x={x + w / 2} y={chartH + 10}
                  textAnchor="middle" fontSize={7} fontFamily="JetBrains Mono, monospace"
                  fill={color} fontWeight="700">
                  {v >= 1000 ? `${(v / 1000).toFixed(1)}K` : v >= 100 ? v.toFixed(0) : v.toFixed(1)}
                </text>
              )}
            </g>
          );
        })}
        {/* quarter labels */}
        {labels.map((l, i) => (
          <text key={i}
            x={i * (w + gap) + w / 2}
            y={chartH + 20}
            textAnchor="middle" fontSize={6} fontFamily="JetBrains Mono, monospace"
            fill={i === labels.length - 1 ? color : "rgba(255,255,255,0.3)"}>
            {l}
          </text>
        ))}
      </svg>
    </div>
  );
}

// ── Result Card ───────────────────────────────────────────────────────────────
function ResultCard({ r }: { r: QuarterlyResult }) {
  const cfg = RATING_CONFIG[r.rating];
  const m = r.metrics;

  const rows = [
    { label: "Sales",     qoq: m.sales.qoq,     yoy: m.sales.yoy,     q1: m.sales.q1,     q2: m.sales.q2,     q3: m.sales.q3,     isBps: false },
    { label: "Other Inc.", qoq: null,            yoy: null,            q1: m.other_income.q1, q2: m.other_income.q2, q3: m.other_income.q3, isBps: false },
    { label: "OP",        qoq: m.op.qoq,        yoy: m.op.yoy,        q1: m.op.q1,        q2: m.op.q2,        q3: m.op.q3,        isBps: false },
    { label: "OPM",       qoq: m.opm.qoq,       yoy: m.opm.yoy,       q1: m.opm.q1,       q2: m.opm.q2,       q3: m.opm.q3,       isBps: true,  pct: true },
    { label: "PAT",       qoq: m.pat.qoq,       yoy: m.pat.yoy,       q1: m.pat.q1,       q2: m.pat.q2,       q3: m.pat.q3,       isBps: false },
    { label: "EPS",       qoq: m.eps.qoq,       yoy: m.eps.yoy,       q1: m.eps.q1,       q2: m.eps.q2,       q3: m.eps.q3,       isBps: false },
  ] as const;

  const ql = r.quarter_labels;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      style={{
        background: "var(--surface)",
        border: `1px solid var(--border)`,
        borderRadius: 16, overflow: "hidden",
        boxShadow: r.rating === "Excellent" || r.rating === "Great" ? cfg.glow : "0 2px 12px rgba(0,0,0,0.3)",
        borderTop: `3px solid ${cfg.color}`,
        position: "relative",
      }}
    >
      {/* Header */}
      <div style={{ padding: "14px 16px 10px", borderBottom: "1px solid var(--border-2)" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, marginBottom: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            {/* Logo placeholder */}
            <div style={{
              width: 38, height: 38, borderRadius: 10, flexShrink: 0,
              background: `${cfg.color}18`, border: `1.5px solid ${cfg.color}44`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 800, color: cfg.color, fontFamily: "var(--font-mono)",
              letterSpacing: "0.02em",
            }}>
              {r.symbol.slice(0, 3)}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 700, color: "var(--text-1)", letterSpacing: "-0.01em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {r.company}
              </div>
              <div style={{ fontSize: 9.5, color: "var(--text-3)", fontFamily: "var(--font-body)", marginTop: 1 }}>
                {r.sector} · {r.industry}
              </div>
            </div>
          </div>

          {/* Quarter + exchange */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, flexShrink: 0 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}>{r.quarter}</span>
            <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 4, background: "var(--surface-2)", color: "var(--text-3)", fontFamily: "var(--font-body)", fontWeight: 700 }}>{r.exchange}</span>
          </div>
        </div>

        {/* Pulse rating */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>Pulse Rating:</span>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            fontSize: 11, fontWeight: 800, color: cfg.color, fontFamily: "var(--font-body)",
            letterSpacing: "0.03em",
          }}>
            {cfg.icon} {r.rating}
          </span>
          <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>₹ in Cr</span>
        </div>
      </div>

      {/* Metrics table */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
          <thead>
            <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
              {["Metric", "QoQ", "YoY", ql[4], ql[3], ql[2]].map((h, i) => (
                <th key={i} style={{
                  padding: "5px 10px", textAlign: i === 0 ? "left" : "right",
                  fontSize: 9, fontWeight: 700, color: "var(--text-3)",
                  letterSpacing: "0.07em", fontFamily: "var(--font-body)",
                  textTransform: "uppercase", whiteSpace: "nowrap",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={row.label} style={{
                borderBottom: "1px solid var(--border-2)",
                background: ri % 2 === 0 ? "transparent" : "rgba(255,255,255,0.012)",
              }}>
                <td style={{ padding: "5px 10px", fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-2)", fontSize: 11, whiteSpace: "nowrap" }}>
                  {row.label}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right" }}>
                  <ChangePct v={row.qoq ?? null} isBps={'isBps' in row && row.isBps && !('pct' in row && row.pct) ? false : false} />
                  {'pct' in row && row.pct
                    ? (row.qoq !== null ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: row.qoq >= 0 ? "#10b981" : "#f87171" }}>{row.qoq > 0 ? "+" : ""}{row.qoq.toFixed(0)} bps</span> : <span style={{ color: "var(--text-4)" }}>—</span>)
                    : null
                  }
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right" }}>
                  {'pct' in row && row.pct
                    ? (row.yoy !== null ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: row.yoy >= 0 ? "#10b981" : "#f87171" }}>{row.yoy > 0 ? "+" : ""}{row.yoy.toFixed(0)} bps</span> : <span style={{ color: "var(--text-4)" }}>—</span>)
                    : <ChangePct v={row.yoy ?? null} />
                  }
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, color: "var(--text-1)" }}>
                  {'pct' in row && row.pct ? `${row.q1.toFixed(1)}%` : row.q1.toLocaleString("en-IN")}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                  {'pct' in row && row.pct ? `${row.q2.toFixed(1)}%` : row.q2.toLocaleString("en-IN")}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>
                  {'pct' in row && row.pct ? `${row.q3.toFixed(1)}%` : row.q3.toLocaleString("en-IN")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Insight box */}
      <div style={{ margin: "10px 12px 0", padding: "7px 10px", borderRadius: 7, border: `1px solid ${cfg.color}33`, background: `${cfg.color}08` }}>
        <p style={{ fontSize: 10.5, color: cfg.color, fontFamily: "var(--font-body)", lineHeight: 1.5, margin: 0, fontWeight: 500 }}>
          {r.insight}
        </p>
      </div>

      {/* Mini bar charts */}
      <div style={{ padding: "10px 12px 6px", display: "flex", gap: 10 }}>
        <MiniBarChart
          values={r.revenue_trend}
          labels={r.quarter_labels}
          color={cfg.color}
          title="Revenue"
          range={`${(r.revenue_trend[0] / 100).toFixed(0)}–${(Math.max(...r.revenue_trend) / 100).toFixed(0)} Cr`}
        />
        <MiniBarChart
          values={r.pat_trend}
          labels={r.quarter_labels}
          color={cfg.color}
          title="PAT"
          range={`${r.pat_trend[r.pat_trend.length - 1].toFixed(0)} Cr`}
        />
        <MiniBarChart
          values={r.eps_trend}
          labels={r.quarter_labels}
          color={cfg.color}
          title="EPS"
          range={`₹${r.eps_trend[r.eps_trend.length - 1].toFixed(1)}`}
        />
      </div>

      {/* Footer */}
      <div style={{
        padding: "8px 12px 10px",
        borderTop: "1px solid var(--border-2)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexWrap: "wrap", gap: 6,
      }}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-1)" }}>
            CMP: ₹{(r.cmp ?? 0).toLocaleString("en-IN")}
          </span>
          <span style={{ fontSize: 11, fontFamily: "var(--font-body)", color: "var(--text-3)" }}>
            {r.market_cap >= 10000
              ? `Large-Cap (${(r.market_cap / 1000).toFixed(0)}K Cr)`
              : r.market_cap >= 1000
              ? `Mid-Cap (${(r.market_cap).toFixed(0)} Cr)`
              : `Small-Cap (${r.market_cap.toFixed(0)} Cr)`}
          </span>
          {r.pe !== null && (
            <span style={{ fontSize: 11, fontFamily: "var(--font-body)", color: "var(--text-3)" }}>P/E: {r.pe.toFixed(1)}</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--text-4)", fontSize: 9 }}>
            <Clock style={{ width: 9, height: 9 }} />
            <span style={{ fontFamily: "var(--font-mono)" }}>{r.report_time}</span>
          </div>
          {r.pdf_url && (
            <a href={r.pdf_url} target="_blank" rel="noopener noreferrer"
              style={{
                display: "inline-flex", alignItems: "center", gap: 3,
                padding: "3px 8px", borderRadius: 5, fontSize: 9.5, fontWeight: 700,
                background: "var(--surface-2)", border: "1px solid var(--border)",
                color: "var(--text-2)", textDecoration: "none",
                fontFamily: "var(--font-body)",
              }}>
              <FileText style={{ width: 9, height: 9 }} /> PDF
            </a>
          )}
          <a
            href={`https://www.tradingview.com/chart/?symbol=${r.exchange}:${r.symbol}`}
            target="_blank" rel="noopener noreferrer"
            style={{
              display: "inline-flex", alignItems: "center", gap: 3,
              padding: "3px 8px", borderRadius: 5, fontSize: 9.5, fontWeight: 700,
              background: "var(--accent-dim)", border: "1px solid var(--accent-border)",
              color: "var(--accent)", textDecoration: "none",
              fontFamily: "var(--font-body)",
            }}>
            <ExternalLink style={{ width: 9, height: 9 }} /> Chart
          </a>
        </div>
      </div>
    </motion.div>
  );
}

// ── List row (compact view) ───────────────────────────────────────────────────
function ResultListRow({ r, idx }: { r: QuarterlyResult; idx: number }) {
  const cfg = RATING_CONFIG[r.rating];
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: idx * 0.03, duration: 0.18 }}
      style={{
        display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
        borderBottom: "1px solid var(--border-2)", cursor: "default",
        borderLeft: `3px solid ${cfg.color}`,
      }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      {/* Rating dot */}
      <div style={{ width: 26, height: 26, borderRadius: 7, background: cfg.bg, border: `1px solid ${cfg.border}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <span style={{ color: cfg.color, display: "flex" }}>{cfg.icon}</span>
      </div>
      {/* Company */}
      <div style={{ flex: 2, minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text-1)", letterSpacing: "-0.01em" }}>{r.symbol}</div>
        <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.company}</div>
      </div>
      {/* Quarter */}
      <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-mono)", flexShrink: 0 }}>{r.quarter}</div>
      {/* Rating */}
      <div style={{
        fontSize: 9, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
        background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
        fontFamily: "var(--font-body)", letterSpacing: "0.05em", flexShrink: 0,
      }}>{r.rating}</div>
      {/* Key metrics */}
      <div style={{ display: "flex", gap: 16, flexShrink: 0 }}>
        {[
          { l: "Sales YoY", v: r.metrics.sales.yoy },
          { l: "PAT YoY",   v: r.metrics.pat.yoy },
          { l: "EPS",       v: r.metrics.eps.q1 },
        ].map(m => (
          <div key={m.l} style={{ textAlign: "right" }}>
            <div style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>{m.l}</div>
            <div style={{
              fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)",
              color: m.l !== "EPS" && m.v !== null
                ? ((m.v ?? 0) >= 0 ? "#10b981" : "#f87171")
                : "var(--text-1)",
            }}>
              {m.l === "EPS" ? `₹${(m.v ?? 0).toFixed(1)}` : m.v !== null ? `${(m.v ?? 0) > 0 ? "+" : ""}${(m.v ?? 0).toFixed(0)}%` : "—"}
            </div>
          </div>
        ))}
      </div>
      {/* CMP */}
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ fontSize: 9, color: "var(--text-4)" }}>CMP</div>
        <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text-1)" }}>₹{(r.cmp ?? 0).toLocaleString("en-IN")}</div>
      </div>
      {/* Actions */}
      <div style={{ display: "flex", gap: 5, flexShrink: 0 }}>
        {r.pdf_url && (
          <a href={r.pdf_url} target="_blank" rel="noopener noreferrer"
            style={{ padding: "3px 7px", borderRadius: 5, fontSize: 9, background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-2)", textDecoration: "none", display: "flex", alignItems: "center", gap: 3 }}>
            <FileText style={{ width: 9, height: 9 }} /> PDF
          </a>
        )}
        <a href={`https://www.tradingview.com/chart/?symbol=${r.exchange}:${r.symbol}`} target="_blank" rel="noopener noreferrer"
          style={{ padding: "3px 7px", borderRadius: 5, fontSize: 9, background: "var(--accent-dim)", border: "1px solid var(--accent-border)", color: "var(--accent)", textDecoration: "none", display: "flex", alignItems: "center", gap: 3 }}>
          <ExternalLink style={{ width: 9, height: 9 }} /> TV
        </a>
      </div>
    </motion.div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function ResultsPage() {
  const [ratingFilter, setRatingFilter] = useState<Rating | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [sortBy, setSortBy] = useState<"time" | "rating" | "sales" | "pat">("time");

  const { data: apiResults, isLoading, isFetching, refetch } = useQuarterlyResults();
  const results = (apiResults && apiResults.length > 0) ? apiResults : SAMPLE_RESULTS;

  const filtered = useMemo(() => {
    let r = results;
    if (ratingFilter !== "ALL") r = r.filter(x => x.rating === ratingFilter);
    if (search.trim()) {
      const q = search.trim().toUpperCase();
      r = r.filter(x => x.symbol.includes(q) || x.company.toUpperCase().includes(q));
    }
    return [...r].sort((a, b) => {
      if (sortBy === "rating") return RATING_CONFIG[a.rating].rank - RATING_CONFIG[b.rating].rank;
      if (sortBy === "sales") return (b.metrics.sales.yoy ?? -999) - (a.metrics.sales.yoy ?? -999);
      if (sortBy === "pat")   return (b.metrics.pat.yoy ?? -999) - (a.metrics.pat.yoy ?? -999);
      return new Date(b.report_date).getTime() - new Date(a.report_date).getTime();
    });
  }, [results, ratingFilter, search, sortBy]);

  // Rating counts
  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: results.length };
    RATINGS.forEach(r => { c[r] = results.filter(x => x.rating === r).length; });
    return c;
  }, [results]);

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header title="Earnings Results" />

      <div style={{ padding: "20px 24px", maxWidth: 1600, margin: "0 auto" }}>

        {/* Page title */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20, gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{
              fontFamily: "var(--font-heading)", fontSize: 26, fontWeight: 700,
              color: "var(--text-1)", margin: 0,
              display: "flex", alignItems: "center", gap: 10,
            }}>
              <BarChart3 style={{ width: 24, height: 24, color: "var(--accent)" }} />
              Earnings Results
            </h1>
            <p style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)", marginTop: 5, marginBottom: 0 }}>
              Q4 FY26 quarterly results with AI-powered pulse rating · {results.length} results loaded
              {!apiResults && <span style={{ color: "var(--amber)", marginLeft: 8 }}>· Demo data (connect backend for live results)</span>}
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* View toggle */}
            <div style={{ display: "flex", gap: 2, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 9, padding: 3 }}>
              {([
                { id: "grid", icon: <LayoutGrid style={{ width: 13, height: 13 }} /> },
                { id: "list", icon: <List style={{ width: 13, height: 13 }} /> },
              ] as { id: "grid" | "list"; icon: React.ReactNode }[]).map(v => (
                <button key={v.id} onClick={() => setViewMode(v.id)}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "center",
                    width: 30, height: 28, borderRadius: 6, border: "none", cursor: "pointer",
                    background: viewMode === v.id ? "var(--accent)" : "transparent",
                    color: viewMode === v.id ? "#fff" : "var(--text-3)",
                    transition: "all 150ms",
                  }}>
                  {v.icon}
                </button>
              ))}
            </div>

            <button onClick={() => refetch()}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "8px 14px", borderRadius: 9,
                background: "var(--surface)", border: "1px solid var(--border)",
                color: "var(--text-2)", cursor: "pointer",
                fontFamily: "var(--font-body)", fontSize: 12, fontWeight: 600,
              }}>
              <RefreshCw style={{ width: 13, height: 13, animation: isFetching ? "spin 1s linear infinite" : "none" }} />
              Refresh
            </button>
          </div>
        </div>

        {/* Rating filter pills */}
        <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
          {(["ALL", ...RATINGS] as const).map(r => {
            const cfg = r !== "ALL" ? RATING_CONFIG[r] : null;
            const active = ratingFilter === r;
            const cnt = counts[r] ?? 0;
            return (
              <motion.button
                key={r}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.96 }}
                onClick={() => setRatingFilter(r)}
                style={{
                  display: "flex", alignItems: "center", gap: 5,
                  padding: "6px 14px", borderRadius: 99, cursor: "pointer",
                  background: active ? (cfg ? cfg.bg : "var(--accent-dim)") : "var(--surface)",
                  border: `1.5px solid ${active ? (cfg ? cfg.color : "var(--accent)") : "var(--border)"}`,
                  color: active ? (cfg ? cfg.color : "var(--accent)") : "var(--text-3)",
                  fontFamily: "var(--font-body)", fontSize: 12, fontWeight: active ? 700 : 500,
                  boxShadow: active && cfg ? cfg.glow : "none",
                  transition: "all 150ms",
                }}
              >
                {cfg && <span style={{ display: "flex" }}>{cfg.icon}</span>}
                {r === "ALL" ? "All Results" : r}
                {cnt > 0 && (
                  <span style={{ fontSize: 9, fontWeight: 800, background: active ? (cfg ? cfg.color : "var(--accent)") : "var(--surface-2)", color: active ? "#fff" : "var(--text-3)", borderRadius: 99, padding: "0px 5px", minWidth: 16, textAlign: "center" }}>
                    {cnt}
                  </span>
                )}
              </motion.button>
            );
          })}

          {/* Sort + search on right */}
          <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value as typeof sortBy)}
              style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: 8, padding: "6px 10px", color: "var(--text-2)",
                fontFamily: "var(--font-body)", fontSize: 11, outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="time">Latest first</option>
              <option value="rating">By rating</option>
              <option value="sales">Sales growth</option>
              <option value="pat">PAT growth</option>
            </select>

            <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "6px 10px" }}>
              <Search style={{ width: 12, height: 12, color: "var(--text-3)" }} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search symbol or name…"
                style={{
                  background: "none", border: "none", outline: "none",
                  color: "var(--text-1)", fontFamily: "var(--font-mono)",
                  fontSize: 11.5, width: 160,
                }}
              />
              {search && (
                <button onClick={() => setSearch("")} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-4)", padding: 0, fontSize: 11, lineHeight: 1 }}>✕</button>
              )}
            </div>
          </div>
        </div>

        {/* Summary stats */}
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          {RATINGS.map(r => {
            const cfg = RATING_CONFIG[r];
            const cnt = counts[r] ?? 0;
            return (
              <div key={r} style={{
                flex: 1, minWidth: 100,
                background: "var(--surface)", border: "1px solid var(--border)",
                borderTop: `3px solid ${cfg.color}`, borderRadius: 10,
                padding: "10px 14px", cursor: "pointer",
                opacity: ratingFilter !== "ALL" && ratingFilter !== r ? 0.45 : 1,
                transition: "opacity 200ms",
              }} onClick={() => setRatingFilter(prev => prev === r ? "ALL" : r)}>
                <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                  <span style={{ color: cfg.color, display: "flex" }}>{cfg.icon}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, color: cfg.color, fontFamily: "var(--font-body)", letterSpacing: "0.05em" }}>{r.toUpperCase()}</span>
                </div>
                <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", color: cnt > 0 ? cfg.color : "var(--text-4)" }}>{cnt}</div>
              </div>
            );
          })}
        </div>

        {/* Content */}
        {isLoading ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 80, gap: 16 }}>
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
              <Loader2 style={{ width: 32, height: 32, color: "var(--accent)" }} />
            </motion.div>
            <div style={{ fontSize: 13, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>Loading results...</div>
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 80, gap: 12 }}>
            <div style={{ fontSize: 40 }}>📊</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)", fontFamily: "var(--font-body)" }}>No results match your filters</div>
            <button onClick={() => { setRatingFilter("ALL"); setSearch(""); }}
              style={{ padding: "8px 20px", borderRadius: 8, background: "var(--accent)", color: "#fff", border: "none", cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
              Clear Filters
            </button>
          </div>
        ) : viewMode === "grid" ? (
          <motion.div layout style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))",
            gap: 18,
          }}>
            <AnimatePresence>
              {filtered.map(r => <ResultCard key={r.id} r={r} />)}
            </AnimatePresence>
          </motion.div>
        ) : (
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, overflow: "hidden" }}>
            <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)", display: "flex", gap: 10 }}>
              {["Company", "Quarter", "Rating", "Sales YoY", "PAT YoY", "EPS", "CMP", ""].map(h => (
                <span key={h} style={{ fontSize: 9, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", textTransform: "uppercase", flex: h === "Company" ? 2 : 1 }}>{h}</span>
              ))}
            </div>
            <AnimatePresence>
              {filtered.map((r, i) => <ResultListRow key={r.id} r={r} idx={i} />)}
            </AnimatePresence>
          </div>
        )}

        <div style={{ marginTop: 20, padding: "10px 0", textAlign: "center", fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
          ⚠ Results data is for informational purposes only. Always verify with official exchange filings before trading.
        </div>
      </div>
    </div>
  );
}

// ── Sample data (shown when backend /api/market/quarterly-results is unavailable) ─
const Q = ["Mar'25", "Jun'25", "Sep'25", "Dec'25", "Mar'26"] as const;

const SAMPLE_RESULTS: QuarterlyResult[] = [
  {
    id: "jkpaper_q4fy26",
    symbol: "JKPAPER", company: "JK Paper", exchange: "NSE",
    sector: "Paper", industry: "Paper & Paper Products",
    quarter: "Q4 FY26", report_date: "2026-05-18", report_time: "18-May-26 20:11",
    rating: "Excellent",
    rating_note: "Strong beat on all fronts",
    cmp: 372.6, market_cap: 6300, pe: 24.4,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: 15, yoy: 17, q1: 1966, q2: 1717, q3: 1677 },
      other_income: { qoq: null, yoy: null, q1: 2, q2: 17, q3: 12 },
      op:           { qoq: 57, yoy: 27, q1: 276, q2: 176, q3: 217 },
      opm:          { qoq: 379, yoy: 110, q1: 14.1, q2: 10.3, q3: 13.0 },
      pat:          { qoq: 336, yoy: 36, q1: 92, q2: 21, q3: 68 },
      eps:          { qoq: 325, yoy: 38, q1: 5.1, q2: 1.2, q3: 3.7 },
    },
    insight: "Strong operating beat driven by volume recovery and price mix. Watch rising debt and stretched receivables — net debt up ₹180 Cr QoQ.",
    revenue_trend: [1677, 1750, 1680, 1717, 1966],
    pat_trend:     [68, 77.2, 79, 21, 92],
    eps_trend:     [3.7, 4.3, 4.4, 1.2, 5.1],
    quarter_labels: Q as unknown as string[],
  },
  {
    id: "getd_q4fy26",
    symbol: "GET&D", company: "GE Vernova T&D India", exchange: "NSE",
    sector: "Capital Goods", industry: "T&D Equipment",
    quarter: "Q4 FY26", report_date: "2026-05-18", report_time: "18-May-26 17:45",
    rating: "Excellent",
    rating_note: "Order book at all-time high",
    cmp: 4427, market_cap: 113510, pe: 88.7,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: -4, yoy: 42, q1: 1637, q2: 1701, q3: 1153 },
      other_income: { qoq: null, yoy: null, q1: 8, q2: 6, q3: 5 },
      op:           { qoq: -2, yoy: 76, q1: 445, q2: 455, q3: 252 },
      opm:          { qoq: 70, yoy: 630, q1: 27.2, q2: 26.7, q3: 21.9 },
      pat:          { qoq: 21, yoy: 86, q1: 352, q2: 291, q3: 186 },
      eps:          { qoq: 21, yoy: 89, q1: 13.74, q2: 11.36, q3: 7.28 },
    },
    insight: "Structural re-rating story intact. T&D capex tailwind strong with ₹9L Cr national grid investment. Margins at record high; order book ₹18,400 Cr.",
    revenue_trend: [1153, 1280, 1450, 1701, 1637],
    pat_trend:     [186, 210, 240, 291, 352],
    eps_trend:     [7.28, 8.2, 9.4, 11.36, 13.74],
    quarter_labels: Q as unknown as string[],
  },
  {
    id: "dixon_q4fy26",
    symbol: "DIXON", company: "Dixon Technologies", exchange: "NSE",
    sector: "Electronics", industry: "Consumer Durable - Electronic",
    quarter: "Q4 FY26", report_date: "2026-05-16", report_time: "16-May-26 19:00",
    rating: "Great",
    rating_note: "Revenue doubled YoY on PLI-led scale-up",
    cmp: 18540, market_cap: 110000, pe: 148.2,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: 12, yoy: 98, q1: 8840, q2: 7890, q3: 4461 },
      other_income: { qoq: null, yoy: null, q1: 18, q2: 22, q3: 14 },
      op:           { qoq: 18, yoy: 82, q1: 292, q2: 248, q3: 160 },
      opm:          { qoq: 18, yoy: -80, q1: 3.3, q2: 3.1, q3: 3.6 },
      pat:          { qoq: 24, yoy: 92, q1: 202, q2: 163, q3: 105 },
      eps:          { qoq: 24, yoy: 90, q1: 33.8, q2: 27.3, q3: 17.8 },
    },
    insight: "Volume-driven revenue surge from smartphone PLI. Margin compress is expected at this scale — focus shifts to absolute EBITDA trajectory.",
    revenue_trend: [4461, 5200, 7120, 7890, 8840],
    pat_trend:     [105, 120, 145, 163, 202],
    eps_trend:     [17.8, 20.1, 24.3, 27.3, 33.8],
    quarter_labels: Q as unknown as string[],
  },
  {
    id: "hdfcbank_q4fy26",
    symbol: "HDFCBANK", company: "HDFC Bank", exchange: "NSE",
    sector: "Financial Services", industry: "Banks - Private",
    quarter: "Q4 FY26", report_date: "2026-04-19", report_time: "19-Apr-26 16:30",
    rating: "Good",
    rating_note: "Stable NIM, loan growth recovering",
    cmp: 1918, market_cap: 1460000, pe: 18.2,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: 3, yoy: 9, q1: 34910, q2: 33907, q3: 32070 },
      other_income: { qoq: null, yoy: null, q1: 12400, q2: 11800, q3: 11200 },
      op:           { qoq: 4, yoy: 11, q1: 22640, q2: 21750, q3: 20390 },
      opm:          { qoq: 30, yoy: 40, q1: 64.9, q2: 64.2, q3: 63.6 },
      pat:          { qoq: 2, yoy: 7, q1: 17616, q2: 17260, q3: 16510 },
      eps:          { qoq: 2, yoy: 7, q1: 23.1, q2: 22.6, q3: 21.6 },
    },
    insight: "Steady as she goes. Loan growth at 7% YoY — below system average. NIM stable at 3.46%. CD ratio normalising, credit costs benign. Dividend ₹22/share.",
    revenue_trend: [32070, 32900, 33400, 33907, 34910],
    pat_trend:     [16510, 16736, 17026, 17260, 17616],
    eps_trend:     [21.6, 21.9, 22.3, 22.6, 23.1],
    quarter_labels: Q as unknown as string[],
  },
  {
    id: "rvnl_q4fy26",
    symbol: "RVNL", company: "Rail Vikas Nigam", exchange: "NSE",
    sector: "Industrials", industry: "Civil Construction",
    quarter: "Q4 FY26", report_date: "2026-05-14", report_time: "14-May-26 20:00",
    rating: "Great",
    rating_note: "Order book at ₹85,000 Cr; execution ramp",
    cmp: 447, market_cap: 23400, pe: 34.1,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: 22, yoy: 28, q1: 6840, q2: 5610, q3: 5344 },
      other_income: { qoq: null, yoy: null, q1: 42, q2: 38, q3: 31 },
      op:           { qoq: 24, yoy: 30, q1: 362, q2: 292, q3: 278 },
      opm:          { qoq: 10, yoy: 10, q1: 5.3, q2: 5.2, q3: 5.2 },
      pat:          { qoq: 18, yoy: 22, q1: 318, q2: 270, q3: 260 },
      eps:          { qoq: 18, yoy: 22, q1: 6.1, q2: 5.2, q3: 5.0 },
    },
    insight: "Kavach deployment adding top-line momentum. Record order inflow from metros + dedicated freight corridor. On track for 25% revenue CAGR over FY27-28.",
    revenue_trend: [5344, 5100, 5800, 5610, 6840],
    pat_trend:     [260, 250, 280, 270, 318],
    eps_trend:     [5.0, 4.8, 5.4, 5.2, 6.1],
    quarter_labels: Q as unknown as string[],
  },
  {
    id: "zomato_q4fy26",
    symbol: "ZOMATO", company: "Zomato (Eternal)", exchange: "NSE",
    sector: "Consumer", industry: "Internet & E-Commerce",
    quarter: "Q4 FY26", report_date: "2026-05-13", report_time: "13-May-26 17:15",
    rating: "Good",
    rating_note: "Profitability established; Blinkit scaling fast",
    cmp: 242, market_cap: 214000, pe: 96.4,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: 9, yoy: 64, q1: 5833, q2: 5352, q3: 3562 },
      other_income: { qoq: null, yoy: null, q1: 210, q2: 195, q3: 180 },
      op:           { qoq: 15, yoy: null, q1: 188, q2: 163, q3: -142 },
      opm:          { qoq: 50, yoy: 600, q1: 3.2, q2: 3.0, q3: -4.0 },
      pat:          { qoq: 18, yoy: null, q1: 268, q2: 226, q3: -188 },
      eps:          { qoq: 18, yoy: null, q1: 0.30, q2: 0.25, q3: -0.21 },
    },
    insight: "Maiden sustained profitability across food + quick commerce. Blinkit GOV at ₹9,400 Cr/qtr growing 95% YoY. Unit economics improving with scale.",
    revenue_trend: [3562, 4206, 4799, 5352, 5833],
    pat_trend:     [-188, -60, 176, 226, 268],
    eps_trend:     [-0.21, -0.07, 0.20, 0.25, 0.30],
    quarter_labels: Q as unknown as string[],
  },
  {
    id: "tatamotors_q4fy26",
    symbol: "TATAMOTORS", company: "Tata Motors", exchange: "NSE",
    sector: "Auto", industry: "Automobiles",
    quarter: "Q4 FY26", report_date: "2026-05-08", report_time: "08-May-26 16:00",
    rating: "Ok",
    rating_note: "JLR margin pressure; EV ramp costs",
    cmp: 724, market_cap: 265000, pe: 9.1,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: -6, yoy: 4, q1: 119086, q2: 126620, q3: 114413 },
      other_income: { qoq: null, yoy: null, q1: 890, q2: 940, q3: 820 },
      op:           { qoq: -12, yoy: -8, q1: 14640, q2: 16610, q3: 15920 },
      opm:          { qoq: -80, yoy: -160, q1: 12.3, q2: 13.1, q3: 13.9 },
      pat:          { qoq: -21, yoy: -15, q1: 8536, q2: 10779, q3: 10124 },
      eps:          { qoq: -21, yoy: -15, q1: 23.1, q2: 29.2, q3: 27.4 },
    },
    insight: "JLR demand moderating in key UK/EU markets with macro headwinds. India CV business showing early-cycle slowdown. FY27 outlook cautious — watch JLR volume guidance.",
    revenue_trend: [114413, 108924, 112455, 126620, 119086],
    pat_trend:     [10124, 7506, 8469, 10779, 8536],
    eps_trend:     [27.4, 20.3, 22.9, 29.2, 23.1],
    quarter_labels: Q as unknown as string[],
  },
  {
    id: "paytm_q4fy26",
    symbol: "PAYTM", company: "One97 Communications", exchange: "NSE",
    sector: "Financial Services", industry: "Fintech",
    quarter: "Q4 FY26", report_date: "2026-05-06", report_time: "06-May-26 18:30",
    rating: "Weak",
    rating_note: "Revenue decline; path to profitability unclear",
    cmp: 812, market_cap: 51800, pe: null,
    currency_unit: "Cr",
    metrics: {
      sales:        { qoq: -8, yoy: -22, q1: 1544, q2: 1679, q3: 1981 },
      other_income: { qoq: null, yoy: null, q1: 62, q2: 58, q3: 71 },
      op:           { qoq: -18, yoy: -41, q1: -122, q2: -100, q3: -208 },
      opm:          { qoq: -80, yoy: -290, q1: -7.9, q2: -5.9, q3: -10.5 },
      pat:          { qoq: -22, yoy: -38, q1: -568, q2: -462, q3: -916 },
      eps:          { qoq: -22, yoy: -38, q1: -8.9, q2: -7.2, q3: -14.4 },
    },
    insight: "Revenue erosion accelerating post-RBI restrictions on Paytm Payments Bank. Merchant subscriber base declining. Cost rationalisation underway but inadequate to offset top-line pressure.",
    revenue_trend: [1981, 1836, 1660, 1679, 1544],
    pat_trend:     [-916, -780, -620, -462, -568],
    eps_trend:     [-14.4, -12.2, -9.7, -7.2, -8.9],
    quarter_labels: Q as unknown as string[],
  },
];
