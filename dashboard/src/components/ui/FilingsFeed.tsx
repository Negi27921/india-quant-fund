import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, Clock, RefreshCw, Filter, ChevronDown } from "lucide-react";
import { useFilings, type Filing } from "@/api/market-queries";

const CATEGORY_COLOR: Record<string, string> = {
  "Financial Results": "var(--accent)",
  "Dividend": "var(--green)",
  "Board Meeting": "var(--amber)",
  "Acquisition": "var(--amber)",
  "USFDA": "var(--green)",
  "Credit Rating": "var(--accent)",
  "Order Win": "var(--green)",
  "Shareholding": "var(--text-3)",
  "AGM": "var(--amber)",
  "Split": "var(--amber)",
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
        borderLeft: "2px solid transparent",
        transition: "all 100ms ease",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = "var(--card-hover)";
        e.currentTarget.style.borderLeftColor = color;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.borderLeftColor = "transparent";
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, justifyContent: "space-between" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3, flexWrap: "wrap" }}>
            <span style={{ fontFamily: "var(--font-body)", fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>
              {filing.company}
            </span>
            <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 99, fontWeight: 700, fontFamily: "var(--font-body)", letterSpacing: "0.06em", background: `${color}18`, color, border: `1px solid ${color}30`, whiteSpace: "nowrap" }}>
              {filing.category}
            </span>
            <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, background: "var(--surface-2)", color: "var(--text-3)", fontFamily: "var(--font-body)", fontWeight: 600 }}>
              {filing.exchange}
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-2)", fontFamily: "var(--font-body)", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as React.CSSProperties["WebkitBoxOrient"] }}>
            {filing.headline}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--text-4)", fontSize: 10 }}>
            <Clock style={{ width: 9, height: 9 }} />
            <span style={{ fontFamily: "var(--font-mono)" }}>{timeAgo(filing.dt)}</span>
          </div>
          {filing.has_pdf && (
            <a
              href={filing.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color: "var(--accent)", fontFamily: "var(--font-body)", fontWeight: 700, textDecoration: "none" }}
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

const inputStyle: React.CSSProperties = {
  background: "var(--surface-2)", border: "1px solid var(--border)",
  borderRadius: 4, padding: "3px 7px", color: "var(--text-1)",
  fontFamily: "var(--font-mono)", fontSize: 10, outline: "none",
  colorScheme: "dark",
};

export function FilingsFeed() {
  const { data: filings, isLoading, refetch, isFetching } = useFilings(50);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [catFilter, setCatFilter] = useState("ALL");
  const [catOpen, setCatOpen] = useState(false);

  const categories = ["ALL", ...Array.from(new Set((filings ?? []).map((f: Filing) => f.category).filter(Boolean))).sort()];

  const filtered = (filings ?? []).filter((f: Filing) => {
    if (catFilter !== "ALL" && f.category !== catFilter) return false;
    if (fromDate && f.dt && f.dt.slice(0, 10) < fromDate) return false;
    if (toDate && f.dt && f.dt.slice(0, 10) > toDate) return false;
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px 8px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px var(--green)", animation: "pulse-dot 2s infinite" }} />
          <span style={{ fontFamily: "var(--font-body)", fontSize: 11, fontWeight: 700, color: "var(--accent)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            LIVE FILINGS
          </span>
          {filtered.length > 0 && <span style={{ fontSize: 10, background: "var(--accent-dim)", color: "var(--accent)", padding: "1px 6px", borderRadius: 99, fontFamily: "var(--font-body)", fontWeight: 700 }}>{filtered.length}</span>}
        </div>
        <button onClick={() => refetch()} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", padding: 4, borderRadius: 6 }}>
          <RefreshCw style={{ width: 12, height: 12, animation: isFetching ? "spin 1s linear infinite" : "none" }} />
        </button>
      </div>

      {/* Filter row */}
      <div style={{
        display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap",
        padding: "6px 14px", borderBottom: "1px solid var(--border-2)", background: "var(--surface-2)", flexShrink: 0,
      }}>
        <Filter style={{ width: 9, height: 9, color: "var(--text-4)", flexShrink: 0 }} />
        <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} style={inputStyle} title="From date" />
        <span style={{ fontSize: 9, color: "var(--text-4)" }}>→</span>
        <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} style={inputStyle} title="To date" />
        {(fromDate || toDate) && (
          <button onClick={() => { setFromDate(""); setToDate(""); }}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-4)", fontSize: 10, padding: 0 }}>✕</button>
        )}

        {/* Category dropdown */}
        <div style={{ marginLeft: "auto", position: "relative" }}>
          <button
            onClick={() => setCatOpen(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 4,
              fontSize: 10, padding: "3px 8px", borderRadius: 6, cursor: "pointer",
              background: catFilter !== "ALL" ? "var(--accent-dim)" : "var(--surface-3)",
              border: `1px solid ${catFilter !== "ALL" ? "var(--accent-border)" : "var(--border)"}`,
              color: catFilter !== "ALL" ? "var(--accent)" : "var(--text-3)",
              fontFamily: "var(--font-body)", fontWeight: 600,
            }}
          >
            <span>{catFilter === "ALL" ? "All Categories" : catFilter}</span>
            <ChevronDown style={{ width: 10, height: 10, transform: catOpen ? "rotate(180deg)" : "none", transition: "transform 150ms" }} />
          </button>
          <AnimatePresence>
            {catOpen && (
              <motion.div
                initial={{ opacity: 0, y: -4, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -4, scale: 0.97 }}
                transition={{ duration: 0.12 }}
                style={{
                  position: "absolute", top: "calc(100% + 4px)", right: 0, zIndex: 50,
                  background: "var(--surface)", border: "1px solid var(--border)",
                  borderRadius: 8, boxShadow: "var(--shadow-lg)", minWidth: 160,
                  maxHeight: 240, overflowY: "auto",
                }}
              >
                {categories.map(cat => (
                  <button
                    key={cat}
                    onClick={() => { setCatFilter(cat); setCatOpen(false); }}
                    style={{
                      display: "block", width: "100%", textAlign: "left",
                      padding: "7px 12px", fontSize: 11, fontFamily: "var(--font-body)",
                      fontWeight: cat === catFilter ? 700 : 500,
                      color: cat === catFilter ? "var(--accent)" : "var(--text-2)",
                      background: cat === catFilter ? "var(--accent-dim)" : "transparent",
                      border: "none", cursor: "pointer",
                      transition: "background 80ms",
                    }}
                    onMouseEnter={e => { if (cat !== catFilter) e.currentTarget.style.background = "var(--surface-2)"; }}
                    onMouseLeave={e => { if (cat !== catFilter) e.currentTarget.style.background = "transparent"; }}
                  >
                    {cat === "ALL" ? "All Categories" : cat}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto" }} onClick={() => catOpen && setCatOpen(false)}>
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ padding: "12px 14px", borderBottom: "1px solid var(--border-2)" }}>
              <div className="skeleton" style={{ height: 12, width: "60%", marginBottom: 6, borderRadius: 4 }} />
              <div className="skeleton" style={{ height: 10, width: "90%", borderRadius: 4 }} />
            </div>
          ))
        ) : filtered.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center" }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
              No filings match filters
            </div>
          </div>
        ) : (
          <AnimatePresence>
            {filtered.map((f, i) => <FilingRow key={f.id || i} filing={f} index={i} />)}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
