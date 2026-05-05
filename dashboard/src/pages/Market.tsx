import { useState } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp, Activity, BarChart2,
  ArrowUpRight, ArrowDownRight, Calendar, Zap, Globe2,
  RefreshCw, FileText, Clock, Filter,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import {
  useMarketIndices, useMarketMovers, useMarketSectors,
  useFiiDiiToday, useAdvancesDeclines, useCorporateActions,
  useResultsCalendar, useFiiDii, useFilings,
  type CorporateAction, type ResultsMeeting, type FiiDiiRow,
  type IndexData, type Filing,
} from "@/api/market-queries";
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
function Card({
  title, icon, accent = "var(--blue)", children, headerRight, style,
}: {
  title: string; icon?: React.ReactNode; accent?: string;
  children: React.ReactNode; headerRight?: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 14,
      borderTop: `3px solid ${accent}`,
      display: "flex", flexDirection: "column",
      overflow: "hidden",
      ...style,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "10px 14px", borderBottom: "1px solid var(--border)",
        background: "var(--surface-2)", flexShrink: 0,
      }}>
        {icon && <span style={{ color: accent, display: "flex", alignItems: "center" }}>{icon}</span>}
        <span style={{
          fontFamily: "var(--font-body)", fontSize: 11, fontWeight: 700,
          color: "var(--text-1)", letterSpacing: "0.06em", textTransform: "uppercase",
        }}>
          {title}
        </span>
        {headerRight && <div style={{ marginLeft: "auto" }}>{headerRight}</div>}
      </div>
      <div style={{ flex: 1, overflow: "hidden" }}>{children}</div>
    </div>
  );
}

// ── Index chip ─────────────────────────────────────────────────────────────────
function IndexChip({ label, data }: { label: string; data?: IndexData }) {
  if (!data) {
    return (
      <div style={{
        padding: "10px 16px", background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 10, flexShrink: 0, minWidth: 120,
      }}>
        <div className="skeleton" style={{ height: 9, width: 64, marginBottom: 6, borderRadius: 3 }} />
        <div className="skeleton" style={{ height: 14, width: 90, borderRadius: 3 }} />
      </div>
    );
  }
  const up = data.change_pct >= 0;
  const color = up ? "var(--green)" : "var(--red)";
  return (
    <div style={{
      padding: "10px 16px", background: "var(--surface)",
      border: `1px solid var(--border)`,
      borderLeft: `3px solid ${color}`,
      borderRadius: 10, flexShrink: 0, minWidth: 130,
      transition: "box-shadow 150ms",
    }}
      onMouseEnter={e => (e.currentTarget.style.boxShadow = `0 0 0 1px ${color}40`)}
      onMouseLeave={e => (e.currentTarget.style.boxShadow = "none")}
    >
      <div style={{ fontSize: 9, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-1)", lineHeight: 1, marginBottom: 3 }}>
        {data.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 2, fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color }}>
        {up ? <ArrowUpRight style={{ width: 10, height: 10 }} /> : <ArrowDownRight style={{ width: 10, height: 10 }} />}
        {Math.abs(data.change_pct).toFixed(2)}%
      </div>
    </div>
  );
}

// ── Filings feed ───────────────────────────────────────────────────────────────
const FILING_COLORS: Record<string, string> = {
  "Financial Results": "var(--blue)", "Dividend": "var(--green)",
  "Board Meeting": "var(--amber)", "Acquisition": "var(--violet)",
  "USFDA": "var(--green)", "Credit Rating": "var(--blue)",
  "Order Win": "var(--green)", "Shareholding": "var(--text-3)",
  "AGM": "var(--amber)", "Split": "var(--violet)", "Bonus": "var(--green)",
};

function FilingsPanel() {
  const { data: filings, isLoading, refetch, isFetching } = useFilings(20);

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
            animation: "pulse 2s infinite",
          }} />
          <span style={{ fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 600, color: "var(--text-3)" }}>
            BSE · NSE Real-Time
          </span>
          {filings && filings.length > 0 && (
            <span style={{
              fontSize: 10, background: "var(--green-dim)", color: "var(--green)",
              padding: "1px 7px", borderRadius: 99, fontWeight: 700,
              border: "1px solid var(--border-green)",
            }}>
              {filings.length}
            </span>
          )}
        </div>
        <button onClick={() => refetch()} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", padding: 4, borderRadius: 6 }}>
          <RefreshCw style={{ width: 12, height: 12, animation: isFetching ? "spin 1s linear infinite" : "none" }} />
        </button>
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
            <div style={{ fontSize: 28, marginBottom: 8 }}>📋</div>
            <div style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>No filings data</div>
            <div style={{ fontSize: 11, color: "var(--text-4)", marginTop: 4, fontFamily: "var(--font-body)" }}>BSE API may be rate-limited</div>
          </div>
        ) : (
          filings.map((f: Filing, i: number) => {
            const color = FILING_COLORS[f.category] || "var(--text-3)";
            return (
              <motion.div
                key={f.id || i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03 }}
                style={{
                  padding: "10px 14px", borderBottom: "1px solid var(--border-2)",
                  cursor: "pointer", borderLeft: "2px solid transparent", transition: "all 100ms",
                }}
                onMouseEnter={e => { e.currentTarget.style.background = "var(--card-hover)"; e.currentTarget.style.borderLeftColor = color; }}
                onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.borderLeftColor = "transparent"; }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: 8, justifyContent: "space-between" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 3, flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "var(--font-body)", fontSize: 12, fontWeight: 700, color: "var(--text-1)" }}>{f.company}</span>
                      <span style={{
                        fontSize: 9, padding: "1px 7px", borderRadius: 99, fontWeight: 700,
                        background: `${color}18`, color, border: `1px solid ${color}35`,
                        letterSpacing: "0.04em", whiteSpace: "nowrap",
                      }}>
                        {f.category}
                      </span>
                      <span style={{
                        fontSize: 9, padding: "1px 5px", borderRadius: 4,
                        background: "var(--surface-3)", color: "var(--text-3)",
                        fontWeight: 600, fontFamily: "var(--font-body)",
                      }}>
                        {f.exchange}
                      </span>
                    </div>
                    <div style={{
                      fontSize: 11.5, color: "var(--text-2)", fontFamily: "var(--font-body)",
                      lineHeight: 1.45, overflow: "hidden", textOverflow: "ellipsis",
                      display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as React.CSSProperties["WebkitBoxOrient"],
                    }}>
                      {f.headline}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--text-4)", fontSize: 10 }}>
                      <Clock style={{ width: 9, height: 9 }} />
                      <span style={{ fontFamily: "var(--font-mono)" }}>{timeAgo(f.dt)}</span>
                    </div>
                    {f.has_pdf && (
                      <a href={f.pdf_url} target="_blank" rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 9, color, fontWeight: 700, textDecoration: "none" }}>
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
    <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Today's snapshot */}
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
              <div style={{ fontSize: 9, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", marginBottom: 6 }}>
                {item.label}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontWeight: 800, fontSize: 16, color: col, lineHeight: 1, marginBottom: 4 }}>
                {fmtCr(item.val)}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <span style={{ fontSize: 9, color: "var(--green)", fontFamily: "var(--font-mono)" }}>B: {fmtCr(item.buy)}</span>
                <span style={{ fontSize: 9, color: "var(--red)", fontFamily: "var(--font-mono)" }}>S: {fmtCr(item.sell)}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Chart label */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          30-Day Flows
        </span>
        {[{ label: "FII", color: "var(--blue)" }, { label: "DII", color: "var(--green)" }].map(l => (
          <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
            <span style={{ width: 12, height: 3, borderRadius: 99, background: l.color, display: "inline-block" }} />
            {l.label}
          </div>
        ))}
      </div>

      {/* Bar chart */}
      {isLoading ? (
        <div className="skeleton" style={{ height: 130, borderRadius: 8 }} />
      ) : chartData.length === 0 ? (
        <div style={{ height: 130, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--surface-2)", borderRadius: 8 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 22, marginBottom: 6 }}>📊</div>
            <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>No flow data yet</div>
          </div>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={130}>
          <BarChart data={chartData} barGap={1} margin={{ top: 0, right: 4, left: -20, bottom: 0 }}>
            <XAxis dataKey="date" tick={{ fontSize: 8, fill: "var(--text-4)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} interval={4} />
            <YAxis tick={{ fontSize: 8, fill: "var(--text-4)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} tickFormatter={v => `${(v / 1000).toFixed(0)}K`} />
            <Tooltip
              contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-1)" }}
              formatter={(v: number, name: string) => [fmtCr(v), name === "fii" ? "FII Net" : "DII Net"]}
            />
            <ReferenceLine y={0} stroke="var(--border-strong)" strokeDasharray="3 3" />
            <Bar dataKey="fii" radius={[2, 2, 0, 0]} maxBarSize={8}>
              {chartData.map((d, i) => <Cell key={i} fill={d.fii >= 0 ? "var(--blue)" : "var(--red)"} fillOpacity={0.85} />)}
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
    <div style={{ padding: "14px 14px" }}>
      <div style={{ fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 10 }}>
        Market Breadth · Nifty 500
      </div>
      {isLoading ? (
        <div className="skeleton" style={{ height: 60, borderRadius: 8 }} />
      ) : (
        <>
          {/* Bar */}
          <div style={{ display: "flex", height: 8, borderRadius: 99, overflow: "hidden", gap: 1, marginBottom: 10 }}>
            <motion.div initial={{ width: 0 }} animate={{ width: `${(adv / total) * 100}%` }} transition={{ duration: 0.8 }}
              style={{ background: "var(--green)", borderRadius: "99px 0 0 99px" }} />
            <motion.div initial={{ width: 0 }} animate={{ width: `${(unch / total) * 100}%` }} transition={{ duration: 0.8 }}
              style={{ background: "var(--border-strong)" }} />
            <motion.div initial={{ width: 0 }} animate={{ width: `${(dec / total) * 100}%` }} transition={{ duration: 0.8 }}
              style={{ background: "var(--red)", borderRadius: "0 99px 99px 0" }} />
          </div>
          {/* Counters */}
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
                <div style={{ fontFamily: "var(--font-mono)", fontWeight: 800, fontSize: 20, color: item.color, lineHeight: 1 }}>{item.val}</div>
                <div style={{ fontSize: 9, color: item.color, opacity: 0.75, letterSpacing: "0.06em", marginTop: 3, fontFamily: "var(--font-body)", fontWeight: 600 }}>
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
            display: "flex", alignItems: "center", gap: 10, padding: "8px 14px",
            borderBottom: "1px solid var(--border-2)", transition: "background 100ms",
          }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
          onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
        >
          <div style={{ fontSize: 11.5, fontFamily: "var(--font-body)", fontWeight: 500, color: "var(--text-2)", width: 100, flexShrink: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {d.sector}
          </div>
          <div style={{ flex: 1, height: 5, background: "var(--surface-3)", borderRadius: 99, overflow: "hidden" }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(Math.abs(d.change_pct) / max) * 100}%` }}
              transition={{ duration: 0.6, delay: i * 0.04 }}
              style={{ height: "100%", borderRadius: 99, background: d.change_pct >= 0 ? "var(--green)" : "var(--red)" }}
            />
          </div>
          <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color: numColor(d.change_pct), width: 52, textAlign: "right", flexShrink: 0 }}>
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
      <div style={{ display: "flex", gap: 6, padding: "8px 14px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        {([["gainers", "var(--green)"], ["losers", "var(--red)"]] as const).map(([key, color]) => (
          <button key={key} onClick={() => setTab(key as MoverTab)} style={{
            fontSize: 10, fontFamily: "var(--font-body)", fontWeight: 700, letterSpacing: "0.06em",
            padding: "4px 12px", borderRadius: 99, border: "1px solid",
            cursor: "pointer", transition: "all 120ms", textTransform: "uppercase",
            background: tab === key ? color : "transparent",
            color: tab === key ? "#fff" : "var(--text-3)",
            borderColor: tab === key ? color : "var(--border)",
          }}>
            {key}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-2)", display: "flex", gap: 10 }}>
              <div className="skeleton" style={{ height: 12, width: "60%", borderRadius: 3 }} />
              <div className="skeleton" style={{ height: 12, width: "30%", borderRadius: 3, marginLeft: "auto" }} />
            </div>
          ))
        ) : rows.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
            No data
          </div>
        ) : rows.map((m, i) => {
          const up = m.change_pct >= 0;
          const color = up ? "var(--green)" : "var(--red)";
          return (
            <div key={m.ticker} style={{
              display: "flex", alignItems: "center", padding: "9px 14px",
              borderBottom: "1px solid var(--border-2)", gap: 10, transition: "background 80ms", cursor: "default",
            }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
            >
              <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-mono)", width: 16, flexShrink: 0 }}>{i + 1}</span>
              <div style={{ width: 22, height: 22, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, background: up ? "var(--green-dim)" : "var(--red-dim)", border: `1px solid ${up ? "var(--border-green)" : "var(--border-red)"}` }}>
                {up ? <ArrowUpRight style={{ width: 11, height: 11, color: "var(--green)" }} /> : <ArrowDownRight style={{ width: 11, height: 11, color: "var(--red)" }} />}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-1)" }}>{m.ticker}</div>
              </div>
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
    Dividend: "var(--green)", Bonus: "var(--violet)",
    Split: "var(--amber)", Buyback: "var(--blue)", Rights: "var(--blue)",
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
        <div style={{ padding: 24, textAlign: "center" }}>
          <div style={{ fontSize: 22, marginBottom: 6 }}>📅</div>
          <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>No upcoming corporate actions</div>
        </div>
      ) : data.map((ca: CorporateAction, i: number) => {
        const color = ACTION_COLOR[ca.action] || "var(--text-3)";
        return (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
            borderBottom: "1px solid var(--border-2)", transition: "background 80ms",
          }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 2 }}>
                {ca.company}
              </div>
              <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-3)" }}>
                Ex: {fmtDate(ca.ex_date)}
              </div>
            </div>
            <span style={{
              fontSize: 9, padding: "2px 8px", borderRadius: 99, fontFamily: "var(--font-body)",
              fontWeight: 700, letterSpacing: "0.06em", background: `${color}18`, color, border: `1px solid ${color}35`,
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
    "Financial Results": "var(--blue)", "Dividend": "var(--green)",
    "Board Meeting": "var(--amber)", "AGM": "var(--violet)",
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
        <div style={{ padding: 24, textAlign: "center" }}>
          <div style={{ fontSize: 22, marginBottom: 6 }}>📆</div>
          <div style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>No upcoming results</div>
        </div>
      ) : data.map((r: ResultsMeeting, i: number) => {
        const color = PURPOSE_COLOR[r.purpose] || "var(--text-3)";
        const dt = new Date(r.meeting_date);
        return (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
            borderBottom: "1px solid var(--border-2)", transition: "background 80ms",
          }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            <div style={{
              flexShrink: 0, width: 38, textAlign: "center",
              background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 8, padding: "4px 0",
            }}>
              <div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 800, color: "var(--text-1)", lineHeight: 1 }}>
                {dt.getDate()}
              </div>
              <div style={{ fontSize: 8, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                {dt.toLocaleString("en-IN", { month: "short" })}
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontFamily: "var(--font-body)", fontWeight: 700, color: "var(--text-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.company}
              </div>
              <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-3)" }}>{r.symbol}</div>
            </div>
            <span style={{
              fontSize: 9, padding: "2px 8px", borderRadius: 99, fontFamily: "var(--font-body)",
              fontWeight: 700, letterSpacing: "0.04em", background: `${color}18`, color, border: `1px solid ${color}35`, flexShrink: 0,
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

export function MarketPage() {
  const { data: indices, isLoading: idxLoading } = useMarketIndices();
  const { data: sectors, isLoading: sectorsLoading } = useMarketSectors();

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: "var(--bg)" }}>
      <Header title="Market" subtitle="NSE · BSE · Real-Time Intelligence" />

      <div style={{ flex: 1, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14, overflowY: "auto" }}>

        {/* ── Index chips row ── */}
        <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 2 }}>
          {INDEX_KEYS.map(({ key, label }, idx) => (
            <motion.div key={key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.06 }}>
              <IndexChip
                label={label}
                data={idxLoading ? undefined : (indices as unknown as Record<string, IndexData>)?.[key]}
              />
            </motion.div>
          ))}
        </div>

        {/* ── Main grid: 3 columns ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr 0.9fr", gap: 12, flex: 1 }}>

          {/* LEFT — Live Filings */}
          <Card
            title="Live Filings"
            icon={<Zap style={{ width: 12, height: 12 }} />}
            accent="var(--green)"
            style={{ minHeight: 500 }}
          >
            <FilingsPanel />
          </Card>

          {/* MIDDLE — FII/DII + Breadth */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Card
              title="FII / DII Flows"
              icon={<Globe2 style={{ width: 12, height: 12 }} />}
              accent="var(--blue)"
              style={{ flex: 1 }}
            >
              <FiiDiiPanel />
            </Card>

            <Card
              title="Market Breadth"
              icon={<Activity style={{ width: 12, height: 12 }} />}
              accent="var(--violet)"
            >
              <BreadthPanel />
            </Card>
          </div>

          {/* RIGHT — Sectors + Movers */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Card
              title="Sector Performance"
              icon={<Filter style={{ width: 12, height: 12 }} />}
              accent="var(--amber)"
              style={{ flex: 1, minHeight: 260 }}
            >
              <SectorPanel data={sectors ?? []} isLoading={sectorsLoading} />
            </Card>

            <Card
              title="Top Movers"
              icon={<BarChart2 style={{ width: 12, height: 12 }} />}
              accent="var(--blue)"
              style={{ flex: 1, minHeight: 200 }}
            >
              <TopMoversPanel />
            </Card>
          </div>
        </div>

        {/* ── Bottom row: Corporate Actions + Results Calendar ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
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
            accent="var(--violet)"
            style={{ minHeight: 200 }}
          >
            <ResultsCalendarPanel />
          </Card>
        </div>
      </div>
    </div>
  );
}
