import { motion, AnimatePresence } from "framer-motion";
import { FileText, Clock, RefreshCw } from "lucide-react";
import { useFilings, type Filing } from "@/api/market-queries";

const CATEGORY_COLOR: Record<string, string> = {
  "Financial Results": "var(--blue)",
  "Dividend": "var(--green)",
  "Board Meeting": "var(--amber)",
  "Acquisition": "var(--violet)",
  "USFDA": "var(--green)",
  "Credit Rating": "var(--blue)",
  "Order Win": "var(--green)",
  "Shareholding": "var(--text-3)",
  "AGM": "var(--amber)",
  "Split": "var(--violet)",
  "Bonus": "var(--green)",
};

function timeAgo(dt: string): string {
  try {
    const d = new Date(dt);
    const diff = Date.now() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch { return ""; }
}

function FilingRow({ filing, index }: { filing: Filing; index: number }) {
  const color = CATEGORY_COLOR[filing.category] || "var(--text-3)";
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04 }}
      style={{
        padding: "10px 14px",
        borderBottom: "1px solid var(--border-2)",
        cursor: "pointer",
        transition: "background 120ms",
      }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, justifyContent: "space-between" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3, flexWrap: "wrap" }}>
            <span style={{ fontFamily: "Inter, sans-serif", fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>
              {filing.company}
            </span>
            <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 99, fontWeight: 700, fontFamily: "Inter, sans-serif", letterSpacing: "0.06em", background: `${color}18`, color, border: `1px solid ${color}30`, whiteSpace: "nowrap" }}>
              {filing.category}
            </span>
            <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "var(--surface-2)", color: "var(--text-3)", fontFamily: "Inter, sans-serif", fontWeight: 600 }}>
              {filing.exchange}
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-2)", fontFamily: "Inter, sans-serif", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as React.CSSProperties["WebkitBoxOrient"] }}>
            {filing.headline}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--text-4)", fontSize: 10 }}>
            <Clock style={{ width: 9, height: 9 }} />
            <span style={{ fontFamily: "JetBrains Mono, monospace" }}>{timeAgo(filing.dt)}</span>
          </div>
          {filing.has_pdf && (
            <a
              href={filing.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color: "var(--blue)", fontFamily: "Inter, sans-serif", fontWeight: 700, textDecoration: "none" }}
              onMouseEnter={e => (e.currentTarget.style.opacity = "0.7")}
              onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
            >
              <FileText style={{ width: 9, height: 9 }} /> PDF
            </a>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export function FilingsFeed() {
  const { data: filings, isLoading, refetch, isFetching } = useFilings(20);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px 8px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px var(--green)", animation: "pulse 2s infinite" }} />
          <span style={{ fontFamily: "Inter, sans-serif", fontSize: 11, fontWeight: 700, color: "var(--blue)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            LIVE FILINGS
          </span>
          {filings && <span style={{ fontSize: 10, background: "var(--blue-dim)", color: "var(--blue)", padding: "1px 6px", borderRadius: 99, fontFamily: "Inter, sans-serif", fontWeight: 700 }}>{filings.length}</span>}
        </div>
        <button onClick={() => refetch()} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", padding: 4, borderRadius: 6 }}>
          <RefreshCw style={{ width: 12, height: 12, animation: isFetching ? "spin 1s linear infinite" : "none" }} />
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ padding: "12px 14px", borderBottom: "1px solid var(--border-2)" }}>
              <div className="skeleton" style={{ height: 12, width: "60%", marginBottom: 6, borderRadius: 4 }} />
              <div className="skeleton" style={{ height: 10, width: "90%", borderRadius: 4 }} />
            </div>
          ))
        ) : (
          <AnimatePresence>
            {(filings ?? []).map((f, i) => <FilingRow key={f.id || i} filing={f} index={i} />)}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
