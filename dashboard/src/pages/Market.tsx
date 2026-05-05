import { useState } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp, TrendingDown, Activity, BarChart2, Filter,
  ArrowUpRight, ArrowDownRight, Calendar, Zap, Globe2,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { FilingsFeed } from "@/components/ui/FilingsFeed";
import { useMarketIndices, useMarketMovers, useMarketSectors } from "@/api/market-queries";
import {
  useFiiDiiToday, useAdvancesDeclines, useCorporateActions,
  useResultsCalendar, useFiiDii,
  type CorporateAction, type ResultsMeeting, type FiiDiiRow,
} from "@/api/market-queries";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import type { IndexData } from "@/api/market-queries";

// ── Helpers ────────────────────────────────────────────────────────────────────
const upDn = (v: number) => (v > 0 ? "▲" : v < 0 ? "▼" : "—");
const numColor = (v: number) => (v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-3)");
const fmtCr = (v: number) => {
  const abs = Math.abs(v);
  const sign = v >= 0 ? "+" : "-";
  if (abs >= 1000) return `${sign}₹${(abs / 1000).toFixed(2)}K Cr`;
  return `${sign}₹${abs.toFixed(0)} Cr`;
};
const fmtDate = (s: string) => {
  try {
    return new Date(s).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  } catch { return s; }
};

// ── Panel wrapper ──────────────────────────────────────────────────────────────
function Panel({
  title,
  icon,
  accentColor = "var(--blue)",
  children,
  style,
  headerRight,
}: {
  title: string;
  icon?: React.ReactNode;
  accentColor?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
  headerRight?: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-lg)",
        borderLeft: `2px solid ${accentColor}`,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        backdropFilter: "blur(12px)",
        ...style,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.02)", flexShrink: 0 }}>
        {icon}
        <span className="panel-title" style={{ color: accentColor }}>{title}</span>
        {headerRight && <div style={{ marginLeft: "auto" }}>{headerRight}</div>}
      </div>
      <div style={{ flex: 1, overflow: "hidden" }}>
        {children}
      </div>
    </div>
  );
}

// ── INDEX KEYS ─────────────────────────────────────────────────────────────────
const INDEX_KEYS: { key: string; label: string }[] = [
  { key: "nifty50",    label: "NIFTY 50" },
  { key: "banknifty",  label: "BANK NIFTY" },
  { key: "sensex",     label: "SENSEX" },
  { key: "niftymid50", label: "MIDCAP 50" },
  { key: "niftyit",    label: "NIFTY IT" },
];

// ── Index chip ─────────────────────────────────────────────────────────────────
function IndexChip({ label, data }: { label: string; data: IndexData | undefined }) {
  if (!data) {
    return (
      <div className="index-chip">
        <div style={{ width: 72 }}>
          <div className="skeleton" style={{ height: 9, width: 60, marginBottom: 5 }} />
          <div className="skeleton" style={{ height: 13, width: 80 }} />
        </div>
      </div>
    );
  }
  const up = data.change_pct >= 0;
  return (
    <div className="index-chip">
      <div>
        <div style={{ fontSize: 9, fontFamily: "Inter, sans-serif", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3 }}>
          {label}
        </div>
        <div style={{ fontSize: 13, fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: "var(--text-1)", lineHeight: 1 }}>
          {data.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 11, fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: up ? "var(--green)" : "var(--red)" }}>
        {up ? <ArrowUpRight style={{ width: 12, height: 12 }} /> : <ArrowDownRight style={{ width: 12, height: 12 }} />}
        {Math.abs(data.change_pct).toFixed(2)}%
      </div>
    </div>
  );
}

// ── Sector bar list ────────────────────────────────────────────────────────────
function SectorList({ data }: { data: { sector: string; change_pct: number }[] }) {
  const max = Math.max(...data.map(d => Math.abs(d.change_pct)), 1);
  return (
    <div style={{ padding: "6px 0", overflowY: "auto", height: "100%" }}>
      {data.map((d, i) => (
        <motion.div
          key={d.sector}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.04 }}
          style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 14px", borderBottom: "1px solid var(--border-2)", cursor: "default" }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
          onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
        >
          <div style={{ fontSize: 12, fontFamily: "Inter, sans-serif", fontWeight: 500, color: "var(--text-2)", width: 110, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {d.sector}
          </div>
          <div style={{ flex: 1, height: 4, background: "var(--surface-3)", borderRadius: 99, overflow: "hidden" }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(Math.abs(d.change_pct) / max) * 100}%` }}
              transition={{ duration: 0.6, delay: i * 0.04 }}
              style={{ height: "100%", borderRadius: 99, background: d.change_pct >= 0 ? "var(--green)" : "var(--red)", boxShadow: d.change_pct >= 0 ? "0 0 4px var(--green-glow)" : "0 0 4px var(--red-glow)" }}
            />
          </div>
          <div style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: numColor(d.change_pct), width: 52, textAlign: "right", flexShrink: 0 }}>
            {upDn(d.change_pct)} {Math.abs(d.change_pct).toFixed(2)}%
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Market Pulse (Advances/Declines + FII/DII today) ──────────────────────────
function MarketPulse() {
  const { data: ad, isLoading: adLoading } = useAdvancesDeclines();
  const { data: fiiDii, isLoading: fdLoading } = useFiiDiiToday();

  const adv = ad?.advances ?? 0;
  const dec = ad?.declines ?? 0;
  const unch = ad?.unchanged ?? 0;
  const total = ad?.total ?? 1;

  return (
    <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Advances / Declines */}
      <div>
        <div style={{ fontSize: 10, fontFamily: "Inter, sans-serif", fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
          Market Breadth
        </div>
        {adLoading ? (
          <div className="skeleton" style={{ height: 36, borderRadius: 8 }} />
        ) : (
          <>
            <div style={{ display: "flex", height: 6, borderRadius: 99, overflow: "hidden", gap: 1, marginBottom: 8 }}>
              <motion.div initial={{ width: 0 }} animate={{ width: `${(adv / total) * 100}%` }} transition={{ duration: 0.8 }} style={{ background: "var(--green)", boxShadow: "0 0 6px var(--green-glow)" }} />
              <motion.div initial={{ width: 0 }} animate={{ width: `${(unch / total) * 100}%` }} transition={{ duration: 0.8 }} style={{ background: "var(--border-strong)" }} />
              <motion.div initial={{ width: 0 }} animate={{ width: `${(dec / total) * 100}%` }} transition={{ duration: 0.8 }} style={{ background: "var(--red)", boxShadow: "0 0 6px var(--red-glow)" }} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
              {[
                { label: "ADV", val: adv, color: "var(--green)", bg: "var(--green-dim)" },
                { label: "UNCH", val: unch, color: "var(--text-3)", bg: "var(--surface-2)" },
                { label: "DEC", val: dec, color: "var(--red)", bg: "var(--red-dim)" },
              ].map(item => (
                <div key={item.label} style={{ textAlign: "center", padding: "6px 4px", background: item.bg, borderRadius: 8, border: `1px solid ${item.color}30` }}>
                  <div style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 700, fontSize: 18, color: item.color, lineHeight: 1 }}>{item.val}</div>
                  <div style={{ fontSize: 9, color: item.color, opacity: 0.7, letterSpacing: "0.1em", marginTop: 2 }}>{item.label}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* FII / DII Today */}
      <div>
        <div style={{ fontSize: 10, fontFamily: "Inter, sans-serif", fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 8 }}>
          FII / DII Today
        </div>
        {fdLoading ? (
          <div className="skeleton" style={{ height: 48, borderRadius: 8 }} />
        ) : fiiDii ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[
              { label: "FII Net", val: fiiDii.fii_net },
              { label: "DII Net", val: fiiDii.dii_net },
            ].map(item => (
              <div key={item.label} style={{ padding: "8px 10px", background: item.val >= 0 ? "var(--green-dim)" : "var(--red-dim)", border: `1px solid ${item.val >= 0 ? "var(--border-green)" : "var(--border-red)"}`, borderRadius: 10 }}>
                <div style={{ fontSize: 9, fontFamily: "Inter, sans-serif", fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", marginBottom: 4 }}>{item.label}</div>
                <div style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 700, fontSize: 14, color: numColor(item.val), lineHeight: 1 }}>
                  {fmtCr(item.val)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "var(--text-4)", fontFamily: "Inter, sans-serif" }}>No data</div>
        )}
      </div>
    </div>
  );
}

// ── Top Movers panel ───────────────────────────────────────────────────────────
type MoverTab = "gainers" | "losers" | "active";

function TopMovers() {
  const [tab, setTab] = useState<MoverTab>("gainers");
  const { data: movers, isLoading } = useMarketMovers(8);

  const tabs: { key: MoverTab; label: string; icon: React.ReactNode; color: string }[] = [
    { key: "gainers", label: "Gainers", icon: <TrendingUp style={{ width: 10, height: 10 }} />, color: "var(--green)" },
    { key: "losers",  label: "Losers",  icon: <TrendingDown style={{ width: 10, height: 10 }} />, color: "var(--red)" },
    { key: "active",  label: "Active",  icon: <Activity style={{ width: 10, height: 10 }} />, color: "var(--blue)" },
  ];

  const rows = tab === "gainers" ? (movers?.gainers ?? []) : tab === "losers" ? (movers?.losers ?? []) : (movers?.gainers ?? []).slice(0, 4).concat(movers?.losers?.slice(0, 4) ?? []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, padding: "8px 14px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              display: "flex", alignItems: "center", gap: 4,
              fontSize: 10, fontFamily: "Inter, sans-serif", fontWeight: 700,
              padding: "4px 10px", borderRadius: 99, border: "1px solid",
              cursor: "pointer", transition: "all 120ms",
              background: tab === t.key ? t.color : "transparent",
              color: tab === t.key ? "#fff" : "var(--text-3)",
              borderColor: tab === t.key ? t.color : "var(--border)",
            }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Rows */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-2)" }}>
              <div className="skeleton" style={{ height: 12, width: "70%", marginBottom: 4 }} />
              <div className="skeleton" style={{ height: 10, width: "40%" }} />
            </div>
          ))
        ) : rows.map((m, i) => {
          const up = m.change_pct >= 0;
          return (
            <div
              key={m.ticker}
              style={{ display: "flex", alignItems: "center", padding: "9px 14px", borderBottom: "1px solid var(--border-2)", gap: 10, transition: "background 100ms", cursor: "default" }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
            >
              <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "JetBrains Mono, monospace", width: 14, flexShrink: 0 }}>{i + 1}</span>
              <div style={{ width: 20, height: 20, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, background: up ? "var(--green-dim)" : "var(--red-dim)" }}>
                {up ? <ArrowUpRight style={{ width: 10, height: 10, color: "var(--green)" }} /> : <ArrowDownRight style={{ width: 10, height: 10, color: "var(--red)" }} />}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: "var(--text-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.ticker}</div>
              </div>
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ fontSize: 12, fontFamily: "JetBrains Mono, monospace", color: "var(--text-1)" }}>₹{m.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</div>
                <div style={{ fontSize: 10, fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: numColor(m.change_pct) }}>
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

// ── Corporate Actions table ────────────────────────────────────────────────────
function CorporateActionsPanel() {
  const { data, isLoading } = useCorporateActions();

  const ACTION_COLOR: Record<string, string> = {
    "Dividend": "var(--green)",
    "Bonus": "var(--violet)",
    "Split": "var(--amber)",
    "Buyback": "var(--blue)",
    "Rights": "var(--blue)",
  };

  return (
    <div style={{ overflowY: "auto", height: "100%" }}>
      {isLoading ? (
        Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-2)" }}>
            <div className="skeleton" style={{ height: 11, width: "60%", marginBottom: 4 }} />
            <div className="skeleton" style={{ height: 9, width: "40%" }} />
          </div>
        ))
      ) : !data || data.length === 0 ? (
        <div style={{ padding: 20, textAlign: "center", fontSize: 11, color: "var(--text-4)", fontFamily: "Inter, sans-serif" }}>No upcoming corporate actions</div>
      ) : data.map((ca: CorporateAction, i) => {
        const color = ACTION_COLOR[ca.action] || "var(--text-3)";
        return (
          <div
            key={i}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: "1px solid var(--border-2)", transition: "background 100ms" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11.5, fontFamily: "Inter, sans-serif", fontWeight: 700, color: "var(--text-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginBottom: 2 }}>
                {ca.company}
              </div>
              <div style={{ fontSize: 10, fontFamily: "JetBrains Mono, monospace", color: "var(--text-3)" }}>
                Ex: {fmtDate(ca.ex_date)}
              </div>
            </div>
            <div style={{ flexShrink: 0 }}>
              <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 99, fontFamily: "Inter, sans-serif", fontWeight: 700, letterSpacing: "0.06em", background: `${color}18`, color, border: `1px solid ${color}30` }}>
                {ca.action}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Results Calendar ──────────────────────────────────────────────────────────
function ResultsCalendarPanel() {
  const { data, isLoading } = useResultsCalendar();

  const PURPOSE_COLOR: Record<string, string> = {
    "Financial Results": "var(--blue)",
    "Dividend": "var(--green)",
    "Board Meeting": "var(--amber)",
    "AGM": "var(--violet)",
  };

  return (
    <div style={{ overflowY: "auto", height: "100%" }}>
      {isLoading ? (
        Array.from({ length: 5 }).map((_, i) => (
          <div key={i} style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-2)" }}>
            <div className="skeleton" style={{ height: 11, width: "55%", marginBottom: 4 }} />
            <div className="skeleton" style={{ height: 9, width: "35%" }} />
          </div>
        ))
      ) : !data || data.length === 0 ? (
        <div style={{ padding: 20, textAlign: "center", fontSize: 11, color: "var(--text-4)", fontFamily: "Inter, sans-serif" }}>No upcoming results</div>
      ) : data.map((r: ResultsMeeting, i) => {
        const color = PURPOSE_COLOR[r.purpose] || "var(--text-3)";
        return (
          <div
            key={i}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: "1px solid var(--border-2)", transition: "background 100ms" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
          >
            <div style={{ flexShrink: 0, width: 36, textAlign: "center", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "3px 0" }}>
              <div style={{ fontSize: 14, fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: "var(--text-1)", lineHeight: 1 }}>
                {new Date(r.meeting_date).getDate()}
              </div>
              <div style={{ fontSize: 8, fontFamily: "Inter, sans-serif", fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                {new Date(r.meeting_date).toLocaleString("en-IN", { month: "short" })}
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11.5, fontFamily: "Inter, sans-serif", fontWeight: 700, color: "var(--text-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.company}
              </div>
              <div style={{ fontSize: 10, fontFamily: "JetBrains Mono, monospace", color: "var(--text-3)" }}>{r.symbol}</div>
            </div>
            <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 99, fontFamily: "Inter, sans-serif", fontWeight: 700, letterSpacing: "0.06em", background: `${color}18`, color, border: `1px solid ${color}30`, flexShrink: 0 }}>
              {r.purpose}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── FII/DII 30-day chart ──────────────────────────────────────────────────────
const FII_TOOLTIP_STYLE = {
  contentStyle: { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 10, fontSize: 11, fontFamily: "JetBrains Mono, monospace", color: "var(--text-1)" },
  labelStyle: { color: "var(--text-3)", fontSize: 10 },
};

function FiiDiiChart() {
  const { data, isLoading } = useFiiDii();

  const chartData = (data ?? []).slice(-20).map((r: FiiDiiRow) => ({
    date: fmtDate(r.date),
    fii: r.fii_net,
    dii: r.dii_net,
  }));

  if (isLoading) {
    return <div className="skeleton" style={{ margin: 16, borderRadius: 8, height: 160 }} />;
  }

  if (!data || data.length === 0) {
    return <div style={{ padding: 20, textAlign: "center", fontSize: 11, color: "var(--text-4)", fontFamily: "Inter, sans-serif" }}>No FII/DII data available</div>;
  }

  return (
    <div style={{ padding: "8px 4px 4px 0" }}>
      <div style={{ display: "flex", gap: 16, paddingLeft: 20, paddingBottom: 6 }}>
        {[
          { label: "FII Net", color: "var(--blue)" },
          { label: "DII Net", color: "var(--green)" },
        ].map(l => (
          <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, fontFamily: "Inter, sans-serif", color: "var(--text-3)" }}>
            <span style={{ width: 10, height: 3, borderRadius: 99, background: l.color, display: "inline-block" }} />
            {l.label}
          </div>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={chartData} barGap={1} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: "var(--text-4)", fontFamily: "JetBrains Mono, monospace" }} axisLine={false} tickLine={false} interval={3} />
          <YAxis tick={{ fontSize: 9, fill: "var(--text-4)", fontFamily: "JetBrains Mono, monospace" }} axisLine={false} tickLine={false} tickFormatter={v => `${(v / 1000).toFixed(0)}K`} />
          <Tooltip
            {...FII_TOOLTIP_STYLE}
            formatter={(v: number, name: string) => [fmtCr(v), name === "fii" ? "FII Net" : "DII Net"]}
          />
          <ReferenceLine y={0} stroke="var(--border-strong)" strokeDasharray="3 3" />
          <Bar dataKey="fii" radius={[3, 3, 0, 0]} maxBarSize={10}>
            {chartData.map((d, i) => (
              <Cell key={i} fill={d.fii >= 0 ? "var(--blue)" : "var(--red)"} fillOpacity={0.85} />
            ))}
          </Bar>
          <Bar dataKey="dii" radius={[3, 3, 0, 0]} maxBarSize={10}>
            {chartData.map((d, i) => (
              <Cell key={i} fill={d.dii >= 0 ? "var(--green)" : "var(--red)"} fillOpacity={0.75} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────
export function MarketPage() {
  const { data: indices, isLoading: idxLoading } = useMarketIndices();
  const { data: sectors, isLoading: sectorsLoading } = useMarketSectors();

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <Header title="Market" subtitle="NSE · BSE · Real-Time Intelligence" />

      <div style={{ flex: 1, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 14, overflowY: "auto" }}>

        {/* ── Top row: Index chips ── */}
        <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 2 }}>
          {INDEX_KEYS.map(({ key, label }) => {
            const d = indices ? (indices as unknown as Record<string, IndexData>)[key] : undefined;
            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 * INDEX_KEYS.findIndex(x => x.key === key) }}
              >
                <IndexChip label={label} data={idxLoading ? undefined : d} />
              </motion.div>
            );
          })}
        </div>

        {/* ── Main 3-column grid ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, flex: 1, minHeight: 0 }}>

          {/* LEFT: Live Filings */}
          <Panel
            title="Live Filings"
            icon={<Zap style={{ width: 12, height: 12, color: "var(--green)" }} />}
            accentColor="var(--green)"
            style={{ minHeight: 480 }}
          >
            <FilingsFeed />
          </Panel>

          {/* MIDDLE: Sectors + Corporate Actions */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Panel
              title="Sector Performance"
              icon={<Filter style={{ width: 12, height: 12, color: "var(--violet)" }} />}
              accentColor="var(--violet)"
              style={{ flex: 1, minHeight: 240 }}
            >
              {sectorsLoading ? (
                <div style={{ padding: 14 }}>
                  {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 11, marginBottom: 8, borderRadius: 4 }} />)}
                </div>
              ) : (
                <SectorList data={sectors ?? []} />
              )}
            </Panel>

            <Panel
              title="Corporate Actions"
              icon={<Calendar style={{ width: 12, height: 12, color: "var(--amber)" }} />}
              accentColor="var(--amber)"
              style={{ flex: 1, minHeight: 200 }}
            >
              <CorporateActionsPanel />
            </Panel>
          </div>

          {/* RIGHT: Top Movers + Market Pulse */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Panel
              title="Top Movers"
              icon={<BarChart2 style={{ width: 12, height: 12, color: "var(--blue)" }} />}
              accentColor="var(--blue)"
              style={{ flex: 1, minHeight: 240 }}
            >
              <TopMovers />
            </Panel>

            <Panel
              title="Market Pulse"
              icon={<Activity style={{ width: 12, height: 12, color: "var(--green)" }} />}
              accentColor="var(--green)"
              style={{ flex: 1, minHeight: 200 }}
            >
              <MarketPulse />
            </Panel>
          </div>
        </div>

        {/* ── Bottom row: FII/DII Chart + Results Calendar (2 col) ── */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
          <Panel
            title="FII / DII 30-Day Flows"
            icon={<Globe2 style={{ width: 12, height: 12, color: "var(--blue)" }} />}
            accentColor="var(--blue)"
          >
            <FiiDiiChart />
          </Panel>

          <Panel
            title="Results Calendar"
            icon={<Calendar style={{ width: 12, height: 12, color: "var(--violet)" }} />}
            accentColor="var(--violet)"
          >
            <ResultsCalendarPanel />
          </Panel>
        </div>

      </div>
    </div>
  );
}
