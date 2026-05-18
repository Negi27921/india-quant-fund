import { useState, useRef } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import {
  TrendingUp, Activity, BarChart2,
  ArrowUpRight, ArrowDownRight, Calendar, Zap, Globe2,
  RefreshCw, FileText, Clock, Filter, ExternalLink,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { useUIStore } from "@/store/ui";
import {
  useMarketIndices, useMarketMovers, useMarketSectors,
  useFiiDiiToday, useAdvancesDeclines, useCorporateActions,
  useResultsCalendar, useFiiDii, useFilings, usePriceHistory,
  type CorporateAction, type ResultsMeeting, type FiiDiiRow,
  type IndexData, type Filing,
} from "@/api/market-queries";
import { MiniChart } from "@/components/charts/MiniChart";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";

// ── Helpers ────────────────────────────────────────────────────────────────────
const upDn = (v: number) => (v > 0 ? "▲" : v < 0 ? "▼" : "—");
const numColor = (v: number) => v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-3)";
const fmtCr = (v: number) => {
  const abs = Math.abs(v);
  const sign = v >= 0 ? "+" : "-";
  if (abs >= 1000) return `${sign}₹${(abs / 1000).toFixed(1)}K Cr`;
  return `${sign}₹${abs.toFixed(0)} Cr`;
};
const fmtDate = (s: string) => {
  try { return new Date(s).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }); }
  catch { return s; }
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

// ── Card wrapper ───────────────────────────────────────────────────────────────
// borderRadius: 12px (between Chakra xl=12px and 2xl=16px — sits at xl)
// borderTop: 3px solid accent
// header: padding 11px 16px, fontSize 11px, letterSpacing 0.07em
function Card({
  title, icon, accent = "var(--accent)", children, headerRight, style,
}: {
  title: string; icon?: React.ReactNode; accent?: string;
  children: React.ReactNode; headerRight?: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 12,              /* Chakra xl */
      borderTop: `3px solid ${accent}`,
      display: "flex", flexDirection: "column",
      overflow: "hidden",
      ...style,
    }}>
      {/* Card header: 11px 16px padding, 11px uppercase labels, 0.07em tracking */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "11px 16px",          /* Chakra space-4 */
        borderBottom: "1px solid var(--border)",
        background: "var(--surface-2)", flexShrink: 0,
      }}>
        {icon && (
          <span style={{ color: accent, display: "flex", alignItems: "center" }}>
            {icon}
          </span>
        )}
        <span style={{
          fontFamily: "var(--font-body)",
          fontSize: 11,                /* Chakra xs */
          fontWeight: 700,
          color: "var(--text-1)",
          letterSpacing: "0.07em",     /* Chakra tracking */
          textTransform: "uppercase",
        }}>
          {title}
        </span>
        {headerRight && <div style={{ marginLeft: "auto" }}>{headerRight}</div>}
      </div>
      {/* Panel body */}
      <div style={{ flex: 1, overflow: "hidden" }}>{children}</div>
    </div>
  );
}

// ── Index chip ─────────────────────────────────────────────────────────────────
function IndexChip({ label, data }: { label: string; data?: IndexData; indexKey: string }) {
  const [hovered, setHovered] = useState(false);
  const chipRef = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const { openChart } = useUIStore();
  const { data: history } = usePriceHistory(data?.symbol ?? "", hovered && !!data?.symbol);
  const chartPoints = (history ?? []).map(b => ({ time: b.time as string, value: b.close }));

  if (!data) {
    return (
      <div style={{
        padding: "10px 16px",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        flexShrink: 0, minWidth: 120,
      }}>
        <div className="skeleton" style={{ height: 9, width: 64, marginBottom: 6, borderRadius: 3 }} />
        <div className="skeleton" style={{ height: 14, width: 90, borderRadius: 3 }} />
      </div>
    );
  }

  const up = data.change_pct >= 0;
  const color = up ? "var(--green)" : "var(--red)";

  const handleMouseEnter = () => {
    if (chipRef.current) setRect(chipRef.current.getBoundingClientRect());
    setHovered(true);
  };

  return (
    <>
      {/* Portal hover tooltip */}
      {hovered && rect && createPortal(
        <div
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          style={{
            position: "fixed",
            top: rect.bottom + 8,
            left: rect.left + rect.width / 2,
            transform: "translateX(-50%)",
            zIndex: 9999,
            background: "var(--surface)",
            border: `1px solid ${color}55`,
            borderRadius: 10,
            padding: "10px 10px 8px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            minWidth: 210,
            pointerEvents: "auto",
          }}
        >
          <div style={{ fontSize: 9, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
            {label} · 30-day
          </div>
          {chartPoints.length >= 2
            ? <MiniChart data={chartPoints} width={190} height={60} color={color} />
            : <div style={{ height: 60, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ width: 190, height: 60, borderRadius: 4, background: "var(--surface-2)", animation: "pulse 1.5s ease-in-out infinite" }} />
              </div>
          }
          <div style={{ marginTop: 6, fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)", textAlign: "center" }}>
            Click chip to open full chart
          </div>
        </div>,
        document.body
      )}

      {/* Chip */}
      <div
        ref={chipRef}
        role="button"
        tabIndex={0}
        onClick={() => data?.symbol && openChart(data.symbol, label)}
        onKeyDown={e => e.key === "Enter" && data?.symbol && openChart(data.symbol, label)}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => setHovered(false)}
        style={{
          padding: "10px 16px",
          background: "var(--surface)",
          border: `1px solid var(--border)`,
          borderLeft: `3px solid ${color}`,
          borderRadius: 8,
          minWidth: 130,
          transition: "box-shadow 150ms ease",
          cursor: "pointer",
          boxShadow: hovered ? `0 0 0 1px ${color}40` : "none",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <div style={{ fontSize: 9, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
            {label}
          </div>
          <ExternalLink style={{ width: 8, height: 8, color: "var(--text-4)", opacity: hovered ? 1 : 0.4, transition: "opacity 150ms" }} />
        </div>
        <div style={{ fontSize: 14, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-1)", lineHeight: 1, marginBottom: 3 }}>
          {data.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 2, fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color }}>
          {up ? <ArrowUpRight style={{ width: 10, height: 10 }} /> : <ArrowDownRight style={{ width: 10, height: 10 }} />}
          {Math.abs(data.change_pct).toFixed(2)}%
        </div>
      </div>
    </>
  );
}

// ── Filings feed ───────────────────────────────────────────────────────────────
const FILING_COLORS: Record<string, string> = {
  "Financial Results": "var(--accent)", "Dividend": "var(--green)",
  "Board Meeting": "var(--amber)", "Acquisition": "var(--amber)",
  "USFDA": "var(--green)", "Credit Rating": "var(--accent)",
  "Order Win": "var(--green)", "Shareholding": "var(--text-3)",
  "AGM": "var(--amber)", "Split": "var(--amber)", "Bonus": "var(--green)",
};

function FilingsPanel() {
  const { data: filings, isLoading, refetch, isFetching } = useFilings(50);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [catFilter, setCatFilter] = useState("ALL");

  const categories = ["ALL", ...Array.from(new Set((filings ?? []).map((f: Filing) => f.category).filter(Boolean)))];
  const filtered = (filings ?? []).filter((f: Filing) => {
    if (catFilter !== "ALL" && f.category !== catFilter) return false;
    if (fromDate && f.dt && f.dt < fromDate) return false;
    if (toDate && f.dt && f.dt.slice(0, 10) > toDate) return false;
    return true;
  });

  const inputStyle: React.CSSProperties = {
    background: "var(--surface-2)", border: "1px solid var(--border)",
    borderRadius: 4, padding: "3px 7px", color: "var(--text-1)",
    fontFamily: "var(--font-mono)", fontSize: 10, outline: "none",
    colorScheme: "dark",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Sub-header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "8px 14px 6px", borderBottom: "1px solid var(--border-2)", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%", background: "var(--green)",
            display: "inline-block", boxShadow: "0 0 6px var(--green)",
            animation: "pulse-dot 2s infinite",
          }} />
          <span style={{
            fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 600,
            color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em",
          }}>
            BSE · NSE Real-Time
          </span>
          {filtered.length > 0 && (
            <span style={{
              fontSize: 10, background: "var(--green-dim)", color: "var(--green)",
              padding: "1px 7px", borderRadius: 9999, fontWeight: 700,
              border: "1px solid var(--border-green)",
            }}>
              {filtered.length}
            </span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "var(--text-3)", padding: 4, borderRadius: 6,
          }}
        >
          <RefreshCw style={{ width: 12, height: 12, animation: isFetching ? "spin 1s linear infinite" : "none" }} />
        </button>
      </div>

      {/* Date + category filter row */}
      <div style={{
        display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap",
        padding: "6px 14px", borderBottom: "1px solid var(--border-2)", flexShrink: 0,
        background: "var(--surface-2)",
      }}>
        <Filter style={{ width: 10, height: 10, color: "var(--text-4)", flexShrink: 0 }} />
        <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} style={inputStyle} title="From date" />
        <span style={{ fontSize: 10, color: "var(--text-4)" }}>→</span>
        <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} style={inputStyle} title="To date" />
        {(fromDate || toDate) && (
          <button onClick={() => { setFromDate(""); setToDate(""); }}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-4)", fontSize: 10, padding: 0 }}>
            ✕
          </button>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          {categories.slice(0, 6).map(cat => (
            <button key={cat} onClick={() => setCatFilter(cat)} style={{
              padding: "2px 7px", borderRadius: 9999, fontSize: 9, fontWeight: 700,
              fontFamily: "var(--font-body)", cursor: "pointer", border: "1px solid",
              background: catFilter === cat ? "var(--accent-dim)" : "transparent",
              borderColor: catFilter === cat ? "var(--accent-border)" : "var(--border)",
              color: catFilter === cat ? "var(--accent)" : "var(--text-4)",
              transition: "all 120ms",
            }}>{cat === "ALL" ? "All" : cat.slice(0, 6)}</button>
          ))}
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          Array.from({ length: 7 }).map((_, i) => (
            <div key={i} style={{ padding: "12px 14px", borderBottom: "1px solid var(--border-2)" }}>
              <div className="skeleton" style={{ height: 12, width: "55%", marginBottom: 6, borderRadius: 3 }} />
              <div className="skeleton" style={{ height: 10, width: "85%", borderRadius: 3 }} />
            </div>
          ))
        ) : !filings || filings.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center" }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>📋</div>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>No filings data</div>
            <div style={{ fontSize: 12, color: "var(--text-4)", marginTop: 4, fontFamily: "var(--font-body)" }}>BSE API may be rate-limited</div>
          </div>
        ) : (
          filtered.map((f: Filing, i: number) => {
            const color = FILING_COLORS[f.category] || "var(--text-3)";
            return (
              <motion.div
                key={f.id || i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
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
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 3, flexWrap: "wrap" }}>
                      {/* Company: 12px semibold */}
                      <span style={{ fontFamily: "var(--font-body)", fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>
                        {f.company}
                      </span>
                      {/* Category badge */}
                      <span style={{
                        fontSize: 9, padding: "1px 7px", borderRadius: 9999, fontWeight: 700,
                        background: `${color}18`, color, border: `1px solid ${color}35`,
                        letterSpacing: "0.04em", whiteSpace: "nowrap",
                      }}>
                        {f.category}
                      </span>
                      {/* Exchange badge */}
                      <span style={{
                        fontSize: 9, padding: "1px 5px", borderRadius: 4,
                        background: "var(--surface-3)", color: "var(--text-3)",
                        fontWeight: 600, fontFamily: "var(--font-body)",
                      }}>
                        {f.exchange}
                      </span>
                    </div>
                    {/* Headline: 11-12px text-2 */}
                    <div style={{
                      fontSize: 11, color: "var(--text-2)", fontFamily: "var(--font-body)",
                      lineHeight: 1.45, overflow: "hidden", textOverflow: "ellipsis",
                      display: "-webkit-box", WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical" as React.CSSProperties["WebkitBoxOrient"],
                    }}>
                      {f.headline}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
                    {/* Time: 10px text-4 */}
                    <div style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--text-4)", fontSize: 10 }}>
                      <Clock style={{ width: 9, height: 9 }} />
                      <span style={{ fontFamily: "var(--font-mono)" }}>{timeAgo(f.dt)}</span>
                    </div>
                    {f.has_pdf && (
                      <a
                        href={f.pdf_url} target="_blank" rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color, fontWeight: 700, textDecoration: "none" }}
                      >
                        <FileText style={{ width: 9, height: 9 }} /> PDF
                      </a>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── FII / DII panel ────────────────────────────────────────────────────────────
function FiiDiiPanel() {
  const { data: today } = useFiiDiiToday();
  const { data: history, isLoading } = useFiiDii();

  const chartData = (history ?? []).slice(-20).map((r: FiiDiiRow) => ({
    date: r.date?.slice(0, 5) || "",
    fii: r.fii_net,
    dii: r.dii_net,
  }));

  return (
    /* Panel body padding: 14px */
    <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Today snapshot: 2-col grid, gap 8px (Chakra space-2) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {[
          { label: "FII Net Today", val: today?.fii_net ?? 0, buy: today?.fii_buy ?? 0, sell: today?.fii_sell ?? 0 },
          { label: "DII Net Today", val: today?.dii_net ?? 0, buy: today?.dii_buy ?? 0, sell: today?.dii_sell ?? 0 },
        ].map(item => {
          const pos = item.val >= 0;
          const bg = pos ? "var(--green-dim)" : "var(--red-dim)";
          const border = pos ? "var(--border-green)" : "var(--border-red)";
          const col = pos ? "var(--green)" : "var(--red)";
          return (
            <div key={item.label} style={{
              padding: "10px 12px", background: bg,
              border: `1px solid ${border}`, borderRadius: 10,
            }}>
              {/* Label: uppercase 9px tracking */}
              <div style={{
                fontSize: 9, fontFamily: "var(--font-body)", fontWeight: 700,
                color: "var(--text-3)", letterSpacing: "0.1em",
                textTransform: "uppercase", marginBottom: 6,
              }}>
                {item.label}
              </div>
              {/* Value: 15px semibold mono (Chakra md) */}
              <div style={{
                fontFamily: "var(--font-mono)", fontWeight: 800,
                fontSize: 15, color: col, lineHeight: 1, marginBottom: 4,
              }}>
                {fmtCr(item.val)}
              </div>
              {/* Buy/Sell: 9px mono */}
              <div style={{ display: "flex", gap: 8 }}>
                <span style={{ fontSize: 9, color: "var(--green)", fontFamily: "var(--font-mono)" }}>B: {fmtCr(item.buy)}</span>
                <span style={{ fontSize: 9, color: "var(--red)", fontFamily: "var(--font-mono)" }}>S: {fmtCr(item.sell)}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* FAO Sentiment + PCR row */}
      {today && (today.pcr !== undefined || today.sentiment) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
          {today.pcr !== undefined && (
            <div style={{
              padding: "8px 10px", background: "var(--surface-2)",
              border: "1px solid var(--border)", borderRadius: 8,
            }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>PCR</div>
              <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 14, color: today.pcr > 1.2 ? "var(--green)" : today.pcr < 0.8 ? "var(--red)" : "var(--text-1)" }}>
                {today.pcr.toFixed(2)}
              </div>
              <div style={{ fontSize: 9, color: "var(--text-3)", marginTop: 2 }}>{today.pcr > 1.2 ? "Bullish" : today.pcr < 0.8 ? "Bearish" : "Neutral"}</div>
            </div>
          )}
          {today.fii_idx_fut_net !== undefined && (
            <div style={{
              padding: "8px 10px", background: "var(--surface-2)",
              border: "1px solid var(--border)", borderRadius: 8,
            }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>FII Idx Fut</div>
              <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 13, color: (today.fii_idx_fut_net ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                {fmtCr(today.fii_idx_fut_net ?? 0)}
              </div>
            </div>
          )}
          {today.sentiment && (
            <div style={{
              padding: "8px 10px", background: today.sentiment === "Bullish" ? "var(--green-dim)" : today.sentiment === "Bearish" ? "var(--red-dim)" : "var(--surface-2)",
              border: `1px solid ${today.sentiment === "Bullish" ? "rgba(34,197,94,0.3)" : today.sentiment === "Bearish" ? "rgba(239,68,68,0.3)" : "var(--border)"}`,
              borderRadius: 8,
            }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>Sentiment</div>
              <div style={{ fontFamily: "var(--font-body)", fontWeight: 700, fontSize: 12, color: today.sentiment === "Bullish" ? "var(--green)" : today.sentiment === "Bearish" ? "var(--red)" : "var(--text-2)" }}>
                {today.sentiment}
              </div>
              {today.sentiment_score !== undefined && (
                <div style={{ fontSize: 9, color: "var(--text-3)", fontFamily: "var(--font-mono)", marginTop: 2 }}>Score: {today.sentiment_score}</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Chart legend + source link */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{
          fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 700,
          color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em",
        }}>
          30-Day Flows
        </span>
        {[{ label: "FII", color: "var(--accent)" }, { label: "DII", color: "var(--green)" }].map(l => (
          <div key={l.label} style={{
            display: "flex", alignItems: "center", gap: 4,
            fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)",
          }}>
            <span style={{ width: 12, height: 3, borderRadius: 9999, background: l.color, display: "inline-block" }} />
            {l.label}
          </div>
        ))}
        <a
          href="https://www.nseindia.com/reports/fii-dii"
          target="_blank" rel="noopener noreferrer"
          style={{
            marginLeft: "auto", display: "flex", alignItems: "center", gap: 3,
            fontSize: 9, color: "var(--text-4)", textDecoration: "none", fontFamily: "var(--font-body)",
            fontWeight: 600, letterSpacing: "0.06em",
            transition: "color 150ms",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
          onMouseLeave={e => (e.currentTarget.style.color = "var(--text-4)")}
        >
          <ExternalLink style={{ width: 9, height: 9 }} /> NSE Source
        </a>
      </div>

      {/* Bar chart */}
      {isLoading ? (
        <div className="skeleton" style={{ height: 130, borderRadius: 8 }} />
      ) : chartData.length === 0 ? (
        /* Empty state: icon 36px, text 13px weight 500 */
        <div style={{ height: 130, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--surface-2)", borderRadius: 8 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 36, marginBottom: 6 }}>📊</div>
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>No flow data yet</div>
          </div>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={130}>
          <BarChart data={chartData} barGap={1} margin={{ top: 0, right: 4, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 8, fill: "var(--text-4)", fontFamily: "var(--font-mono)" }}
              axisLine={false} tickLine={false} interval={4}
            />
            <YAxis
              tick={{ fontSize: 8, fill: "var(--text-4)", fontFamily: "var(--font-mono)" }}
              axisLine={false} tickLine={false}
              tickFormatter={v => `${(v / 1000).toFixed(0)}K`}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--border-2)",
                borderRadius: 6,
                fontSize: 11.5,
                fontFamily: "var(--font-mono)",
                color: "var(--text-1)",
                boxShadow: "var(--shadow-md)",
                padding: "8px 12px",
              }}
              labelStyle={{ color: "var(--accent)", fontWeight: 700, fontSize: 11, letterSpacing: "0.06em", marginBottom: 4 }}
              itemStyle={{ color: "var(--text-2)", padding: "2px 0" }}
              cursor={{ fill: "var(--accent-dim)" }}
              formatter={(v: number, name: string) => {
                const label = name === "fii" ? "FII Net" : "DII Net";
                const color = name === "fii" ? "var(--accent)" : "var(--green)";
                return [<span style={{ color, fontWeight: 700 }}>{fmtCr(v)}</span>, label];
              }}
            />
            <ReferenceLine y={0} stroke="var(--border-2)" strokeDasharray="3 3" />
            <Bar dataKey="fii" radius={[2, 2, 0, 0]} maxBarSize={8}>
              {chartData.map((d, i) => <Cell key={i} fill={d.fii >= 0 ? "var(--accent)" : "var(--red)"} fillOpacity={0.85} />)}
            </Bar>
            <Bar dataKey="dii" radius={[2, 2, 0, 0]} maxBarSize={8}>
              {chartData.map((d, i) => <Cell key={i} fill={d.dii >= 0 ? "var(--green)" : "var(--red)"} fillOpacity={0.75} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ── Advances / Declines ────────────────────────────────────────────────────────
function BreadthPanel() {
  const { data: ad, isLoading } = useAdvancesDeclines();
  const adv = ad?.advances ?? 0;
  const dec = ad?.declines ?? 0;
  const unch = ad?.unchanged ?? 0;
  const total = ad?.total ?? 1;

  return (
    /* Panel body padding: 14px */
    <div style={{ padding: 14 }}>
      {/* Label: uppercase 10px tracking-widest */}
      <div style={{
        fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 700,
        color: "var(--text-3)", letterSpacing: "0.1em",
        textTransform: "uppercase", marginBottom: 10,
      }}>
        Market Breadth · Nifty 500
      </div>
      {isLoading ? (
        <div className="skeleton" style={{ height: 60, borderRadius: 8 }} />
      ) : (
        <>
          {/* Progress bar */}
          <div style={{ display: "flex", height: 8, borderRadius: 9999, overflow: "hidden", gap: 1, marginBottom: 10 }}>
            <motion.div
              initial={{ width: 0 }} animate={{ width: `${(adv / total) * 100}%` }}
              transition={{ duration: 0.8 }}
              style={{ background: "var(--green)", borderRadius: "9999px 0 0 9999px" }}
            />
            <motion.div
              initial={{ width: 0 }} animate={{ width: `${(unch / total) * 100}%` }}
              transition={{ duration: 0.8 }}
              style={{ background: "var(--border-2)" }}
            />
            <motion.div
              initial={{ width: 0 }} animate={{ width: `${(dec / total) * 100}%` }}
              transition={{ duration: 0.8 }}
              style={{ background: "var(--red)", borderRadius: "0 9999px 9999px 0" }}
            />
          </div>
          {/* Counter grid: gap 8px (Chakra space-2) */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            {[
              { label: "Advances", val: adv, color: "var(--green)", bg: "var(--green-dim)", border: "var(--border-green)" },
              { label: "Unchanged", val: unch, color: "var(--text-3)", bg: "var(--surface-2)", border: "var(--border)" },
              { label: "Declines", val: dec, color: "var(--red)", bg: "var(--red-dim)", border: "var(--border-red)" },
            ].map(item => (
              <div key={item.label} style={{
                textAlign: "center", padding: "8px 4px",
                background: item.bg, border: `1px solid ${item.border}`, borderRadius: 8,
              }}>
                {/* Value: 20px mono */}
                <div style={{ fontFamily: "var(--font-mono)", fontWeight: 800, fontSize: 20, color: item.color, lineHeight: 1 }}>
                  {item.val}
                </div>
                {/* Label: 9px uppercase */}
                <div style={{
                  fontSize: 9, color: item.color, opacity: 0.75,
                  letterSpacing: "0.07em", marginTop: 3,
                  fontFamily: "var(--font-body)", fontWeight: 600,
                  textTransform: "uppercase",
                }}>
                  {item.label}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Sector performance ─────────────────────────────────────────────────────────
function SectorPanel({ data, isLoading }: { data: { sector: string; change_pct: number }[]; isLoading: boolean }) {
  const max = Math.max(...(data ?? []).map(d => Math.abs(d.change_pct)), 1);
  return (
    <div style={{ overflowY: "auto", height: "100%", padding: "4px 0" }}>
      {isLoading ? (
        Array.from({ length: 7 }).map((_, i) => (
          <div key={i} style={{ padding: "8px 14px", borderBottom: "1px solid var(--border-2)" }}>
            <div className="skeleton" style={{ height: 10, borderRadius: 3 }} />
          </div>
        ))
      ) : (data ?? []).map((d, i) => (
        <motion.div
          key={d.sector}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.04 }}
          style={{
            display: "flex", alignItems: "center",
            /* 8px gap between items (Chakra space-2) */
            gap: 8, padding: "8px 14px",
            borderBottom: "1px solid var(--border-2)",
            transition: "background 100ms ease",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
          onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
        >
          {/* Sector name: 11px text-2 */}
          <div style={{
            fontSize: 11, fontFamily: "var(--font-body)", fontWeight: 500,
            color: "var(--text-2)", width: 100, flexShrink: 0,
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {d.sector}
          </div>
          {/* Progress bar */}
          <div style={{ flex: 1, height: 5, background: "var(--surface-3)", borderRadius: 9999, overflow: "hidden" }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(Math.abs(d.change_pct) / max) * 100}%` }}
              transition={{ duration: 0.6, delay: i * 0.04 }}
              style={{ height: "100%", borderRadius: 9999, background: d.change_pct >= 0 ? "var(--green)" : "var(--red)" }}
            />
          </div>
          {/* Value: 11px semibold mono */}
          <div style={{
            fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700,
            color: numColor(d.change_pct), width: 52, textAlign: "right", flexShrink: 0,
          }}>
            {upDn(d.change_pct)}{Math.abs(d.change_pct).toFixed(2)}%
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Top Movers ─────────────────────────────────────────────────────────────────
type MoverTab = "gainers" | "losers";

function TopMoversPanel() {
  const [tab, setTab] = useState<MoverTab>("gainers");
  const { data: movers, isLoading } = useMarketMovers(10);
  const rows = tab === "gainers" ? (movers?.gainers ?? []) : (movers?.losers ?? []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Tab row */}
      <div style={{
        display: "flex", gap: 6, padding: "8px 14px",
        borderBottom: "1px solid var(--border)", flexShrink: 0,
      }}>
        {([["gainers", "var(--green)"], ["losers", "var(--red)"]] as const).map(([key, color]) => (
          <button key={key} onClick={() => setTab(key as MoverTab)} style={{
            fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 700,
            letterSpacing: "0.07em",
            padding: "4px 12px", borderRadius: 9999, border: "1px solid",
            cursor: "pointer", transition: "all 120ms ease",
            textTransform: "uppercase",
            background: tab === key ? color : "transparent",
            color: tab === key ? "#fff" : "var(--text-3)",
            borderColor: tab === key ? color : "var(--border)",
          }}>
            {key}
          </button>
        ))}
      </div>
      {/* List */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-2)", display: "flex", gap: 10 }}>
              <div className="skeleton" style={{ height: 12, width: "60%", borderRadius: 3 }} />
              <div className="skeleton" style={{ height: 12, width: "30%", borderRadius: 3, marginLeft: "auto" }} />
            </div>
          ))
        ) : rows.length === 0 ? (
          /* Empty state: 13px weight 500 */
          <div style={{
            padding: 24, textAlign: "center",
            fontSize: 13, fontWeight: 500,
            color: "var(--text-4)", fontFamily: "var(--font-body)",
          }}>
            No data
          </div>
        ) : rows.map((m, i) => {
          const up = m.change_pct >= 0;
          const color = up ? "var(--green)" : "var(--red)";
          return (
            <div key={m.ticker} style={{
              display: "flex", alignItems: "center", padding: "9px 14px",
              /* 8px gap (Chakra space-2) */
              borderBottom: "1px solid var(--border-2)", gap: 8,
              transition: "background 80ms ease", cursor: "default",
            }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
            >
              {/* Rank: 10px text-4 mono */}
              <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", width: 16, flexShrink: 0 }}>
                {i + 1}
              </span>
              {/* Direction icon */}
              <div style={{
                width: 22, height: 22, borderRadius: 6,
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
                background: up ? "var(--green-dim)" : "var(--red-dim)",
                border: `1px solid ${up ? "var(--border-green)" : "var(--border-red)"}`,
              }}>
                {up
                  ? <ArrowUpRight style={{ width: 11, height: 11, color: "var(--green)" }} />
                  : <ArrowDownRight style={{ width: 11, height: 11, color: "var(--red)" }} />
                }
              </div>
              {/* Ticker: 12px semibold mono */}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-1)" }}>
                  {m.ticker}
                </div>
              </div>
              {/* Price + change: 12px / 11px mono */}
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-1)", fontWeight: 500 }}>
                  ₹{m.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color }}>
                  {upDn(m.change_pct)} {Math.abs(m.change_pct).toFixed(2)}%
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Corporate Actions ──────────────────────────────────────────────────────────
function CorporateActionsPanel() {
  const { data, isLoading } = useCorporateActions();
  const ACTION_COLOR: Record<string, string> = {
    Dividend: "var(--green)", Bonus: "var(--amber)",
    Split: "var(--amber)", Buyback: "var(--accent)", Rights: "var(--accent)",
  };

  return (
    <div style={{ overflowY: "auto", height: "100%" }}>
      {isLoading ? (
        Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-2)" }}>
            <div className="skeleton" style={{ height: 11, width: "60%", marginBottom: 4, borderRadius: 3 }} />
            <div className="skeleton" style={{ height: 9, width: "35%", borderRadius: 3 }} />
          </div>
        ))
      ) : !data || data.length === 0 ? (
        /* Empty state: icon 36px, text 13px weight 500 */
        <div style={{ padding: 24, textAlign: "center" }}>
          <div style={{ fontSize: 36, marginBottom: 6 }}>📅</div>
          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
            No upcoming corporate actions
          </div>
        </div>
      ) : data.map((ca: CorporateAction, i: number) => {
        const color = ACTION_COLOR[ca.action] || "var(--text-3)";
        return (
          <div key={i} style={{
            display: "flex", alignItems: "center",
            /* 8px gap (Chakra space-2) */
            gap: 8, padding: "9px 14px",
            borderBottom: "1px solid var(--border-2)", transition: "background 80ms ease",
          }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Company + symbol badge */}
              <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 2, flexWrap: "wrap" }}>
                <div style={{
                  fontSize: 12, fontFamily: "var(--font-body)", fontWeight: 700,
                  color: "var(--text-1)", overflow: "hidden", textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}>
                  {ca.company}
                </div>
                {ca.symbol && (
                  <span style={{
                    background: "var(--surface-3)",
                    border: "1px solid var(--border)",
                    borderRadius: 3,
                    padding: "1px 6px",
                    fontSize: 9,
                    fontFamily: "monospace",
                    color: "var(--text-2)",
                    flexShrink: 0,
                  }}>
                    {ca.symbol}
                  </span>
                )}
              </div>
              {/* Ex-date: 10px text-3 mono */}
              <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-3)" }}>
                Ex: {fmtDate(ca.ex_date)}
              </div>
            </div>
            {/* Action badge */}
            <span style={{
              fontSize: 9, padding: "2px 8px", borderRadius: 9999, fontFamily: "var(--font-body)",
              fontWeight: 700, letterSpacing: "0.06em",
              background: `${color}18`, color, border: `1px solid ${color}35`,
            }}>
              {ca.action}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Results Calendar ───────────────────────────────────────────────────────────
function ResultsCalendarPanel() {
  const { data, isLoading } = useResultsCalendar();
  const PURPOSE_COLOR: Record<string, string> = {
    "Financial Results": "var(--accent)", "Dividend": "var(--green)",
    "Board Meeting": "var(--amber)", "AGM": "var(--amber)",
  };

  return (
    <div style={{ overflowY: "auto", height: "100%" }}>
      {isLoading ? (
        Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-2)" }}>
            <div className="skeleton" style={{ height: 11, width: "55%", marginBottom: 4, borderRadius: 3 }} />
            <div className="skeleton" style={{ height: 9, width: "30%", borderRadius: 3 }} />
          </div>
        ))
      ) : !data || data.length === 0 ? (
        /* Empty state: icon 36px, text 13px weight 500 */
        <div style={{ padding: 24, textAlign: "center" }}>
          <div style={{ fontSize: 36, marginBottom: 6 }}>📆</div>
          <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
            No upcoming results
          </div>
        </div>
      ) : data.map((r: ResultsMeeting, i: number) => {
        const color = PURPOSE_COLOR[r.purpose] || "var(--text-3)";
        const dt = new Date(r.meeting_date);
        return (
          <div key={i} style={{
            display: "flex", alignItems: "center",
            /* 8px gap (Chakra space-2) */
            gap: 8, padding: "9px 14px",
            borderBottom: "1px solid var(--border-2)", transition: "background 80ms ease",
          }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            {/* Date badge */}
            <div style={{
              flexShrink: 0, width: 38, textAlign: "center",
              background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "4px 0",
            }}>
              {/* Day: 15px mono bold */}
              <div style={{
                fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 800,
                color: "var(--text-1)", lineHeight: 1,
              }}>
                {dt.getDate()}
              </div>
              {/* Month: 8px uppercase */}
              <div style={{
                fontSize: 8, fontFamily: "var(--font-body)", fontWeight: 700,
                color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em",
              }}>
                {dt.toLocaleString("en-IN", { month: "short" })}
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Company: 12px semibold */}
              <div style={{
                fontSize: 12, fontFamily: "var(--font-body)", fontWeight: 700,
                color: "var(--text-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {r.company}
              </div>
              {/* Symbol: 10px text-3 mono */}
              <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-3)" }}>
                {r.symbol}
              </div>
            </div>
            {/* Purpose badge */}
            <span style={{
              fontSize: 9, padding: "2px 8px", borderRadius: 9999, fontFamily: "var(--font-body)",
              fontWeight: 700, letterSpacing: "0.04em",
              background: `${color}18`, color, border: `1px solid ${color}35`, flexShrink: 0,
            }}>
              {r.purpose}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
const INDEX_KEYS: { key: string; label: string }[] = [
  { key: "nifty50",    label: "NIFTY 50" },
  { key: "banknifty",  label: "BANK NIFTY" },
  { key: "sensex",     label: "SENSEX" },
  { key: "niftymid50", label: "MIDCAP 50" },
  { key: "niftyit",    label: "NIFTY IT" },
];

function IndexTable({ indices, loading }: { indices: unknown; loading: boolean }) {
  const idxMap = indices as Record<string, IndexData> | undefined;
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 8, overflow: "hidden",
    }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            {["Index", "Price", "Chg %", "Chg Pts", "Prev Close", "Day High", "Day Low"].map(h => (
              <th key={h} style={{
                padding: "7px 14px", textAlign: h === "Index" ? "left" : "right",
                fontSize: 8.5, fontWeight: 700, color: "var(--text-3)",
                letterSpacing: "0.12em", textTransform: "uppercase",
                fontFamily: "var(--font-body)", background: "var(--surface-2)",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {INDEX_KEYS.map(({ key, label }) => {
            const d = idxMap?.[key];
            const up = (d?.change_pct ?? 0) >= 0;
            const col = up ? "var(--green)" : "var(--red)";
            const chgPts = d ? (d.price * d.change_pct / (100 + d.change_pct)).toFixed(2) : "—";
            return (
              <tr key={key} style={{ borderBottom: "1px solid var(--border-2)", transition: "background 80ms" }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <td style={{ padding: "8px 14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <span style={{ width: 3, height: 18, borderRadius: 9999, background: col, flexShrink: 0 }} />
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-body)" }}>{label}</span>
                  </div>
                </td>
                {loading || !d ? (
                  [0,1,2,3,4,5].map(i => (
                    <td key={i} style={{ padding: "8px 14px", textAlign: "right" }}>
                      <div className="skeleton" style={{ height: 10, width: 55, borderRadius: 3, marginLeft: "auto" }} />
                    </td>
                  ))
                ) : (
                  <>
                    <td style={{ padding: "8px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>
                      {d.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: "8px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: col }}>
                      {up ? "+" : ""}{d.change_pct.toFixed(2)}%
                    </td>
                    <td style={{ padding: "8px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 11, color: col }}>
                      {up ? "+" : ""}{chgPts}
                    </td>
                    <td style={{ padding: "8px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--text-3)" }}>
                      {d.prev_close ? d.prev_close.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "—"}
                    </td>
                    <td style={{ padding: "8px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--green)" }}>
                      {d.day_high ? d.day_high.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "—"}
                    </td>
                    <td style={{ padding: "8px 14px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--red)" }}>
                      {d.day_low ? d.day_low.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "—"}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function MarketPage() {
  const { data: indices, isLoading: idxLoading } = useMarketIndices();
  const { data: sectors, isLoading: sectorsLoading } = useMarketSectors();

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: "var(--bg)" }}>
      <Header title="Market" subtitle="NSE · BSE · Real-Time Intelligence" />

      {/*
        Page wrapper:
          - paddingTop: 20px (Chakra space-5)
          - paddingLeft/Right: 24px (Chakra space-6)
          - paddingBottom: 24px
      */}
      <div style={{
        flex: 1,
        padding: "20px 24px 24px",
        display: "flex", flexDirection: "column",
        /* Main grid gap: 16px (Chakra space-4) */
        gap: 16,
        overflowY: "auto",
      }}>

        {/* ── Index chips row ── gap: 12px */}
        <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 2 }}>
          {INDEX_KEYS.map(({ key, label }, idx) => (
            <motion.div key={key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.06 }}>
              <IndexChip
                label={label}
                indexKey={key}
                data={idxLoading ? undefined : (indices as unknown as Record<string, IndexData>)?.[key]}
              />
            </motion.div>
          ))}
        </div>

        {/* ── Index detail table ── */}
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <IndexTable indices={indices} loading={idxLoading} />
        </motion.div>

        {/* ── Main grid: 3 columns, gap 16px (Chakra space-4) ── */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1.1fr 1fr 0.9fr",
          gap: 16,               /* Chakra space-4 */
          flex: 1,
        }}>

          {/* LEFT — Live Filings */}
          <Card
            title="Live Filings"
            icon={<Zap style={{ width: 12, height: 12 }} />}
            accent="var(--green)"
            style={{ minHeight: 500 }}
          >
            <FilingsPanel />
          </Card>

          {/* MIDDLE — FII/DII + Breadth, inner gap 16px */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Card
              title="FII / DII Flows"
              icon={<Globe2 style={{ width: 12, height: 12 }} />}
              accent="var(--accent)"
              style={{ flex: 1 }}
            >
              <FiiDiiPanel />
            </Card>

            <Card
              title="Market Breadth"
              icon={<Activity style={{ width: 12, height: 12 }} />}
              accent="var(--amber)"
            >
              <BreadthPanel />
            </Card>
          </div>

          {/* RIGHT — Sectors + Movers, inner gap 16px */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Card
              title="Sector Performance"
              icon={<Filter style={{ width: 12, height: 12 }} />}
              accent="var(--amber)"
              style={{ flex: 1, minHeight: 260 }}
              headerRight={
                <a
                  href="https://www.nseindia.com/market-data/sector-indices"
                  target="_blank" rel="noopener noreferrer"
                  style={{
                    display: "flex", alignItems: "center", gap: 3,
                    fontSize: 9, color: "var(--text-4)", textDecoration: "none",
                    fontFamily: "var(--font-body)", fontWeight: 600, letterSpacing: "0.06em",
                    transition: "color 150ms",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.color = "var(--amber)")}
                  onMouseLeave={e => (e.currentTarget.style.color = "var(--text-4)")}
                >
                  <ExternalLink style={{ width: 9, height: 9 }} /> NSE
                </a>
              }
            >
              <SectorPanel data={sectors ?? []} isLoading={sectorsLoading} />
            </Card>

            <Card
              title="Top Movers"
              icon={<BarChart2 style={{ width: 12, height: 12 }} />}
              accent="var(--accent)"
              style={{ flex: 1, minHeight: 200 }}
            >
              <TopMoversPanel />
            </Card>
          </div>
        </div>

        {/* ── Bottom row: Corporate Actions + Results Calendar, gap 16px ── */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,               /* Chakra space-4 */
        }}>
          <Card
            title="Corporate Actions"
            icon={<Calendar style={{ width: 12, height: 12 }} />}
            accent="var(--green)"
            style={{ minHeight: 200 }}
          >
            <CorporateActionsPanel />
          </Card>

          <Card
            title="Results Calendar"
            icon={<TrendingUp style={{ width: 12, height: 12 }} />}
            accent="var(--amber)"
            style={{ minHeight: 200 }}
          >
            <ResultsCalendarPanel />
          </Card>
        </div>
      </div>
    </div>
  );
}
