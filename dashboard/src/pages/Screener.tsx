import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ScanSearch, RefreshCw, CheckCircle2, XCircle, TrendingUp, TrendingDown, ChevronDown, ChevronUp, Filter, Loader2, Rocket, Layers, Zap } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { useScreener, useTriggerScan, type ScreenerResult } from "@/api/market-queries";
import { useQueryClient } from "@tanstack/react-query";

// ── Types ─────────────────────────────────────────────────────────────────────
type Strategy = "vcp" | "ipo_base" | "rocket_base";

const STRATEGY_META: Record<Strategy, { label: string; icon: React.ReactNode; color: string; desc: string }> = {
  vcp: {
    label: "VCP",
    icon: <Layers style={{ width: 14, height: 14 }} />,
    color: "#5B7FFF",
    desc: "Volatility Contraction Pattern — 4-wave tightening with declining volume",
  },
  ipo_base: {
    label: "IPO Base",
    icon: <Zap style={{ width: 14, height: 14 }} />,
    color: "#06D6A0",
    desc: "Tight base after a strong leg-up, EMA support, volume drying up",
  },
  rocket_base: {
    label: "Rocket Base",
    icon: <Rocket style={{ width: 14, height: 14 }} />,
    color: "#FF6B35",
    desc: "80%+ momentum move, now consolidating ≤20% from peak",
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function confBadge(conf: number): { label: string; color: string; bg: string; border: string } {
  if (conf >= 70) return { label: "Strong", color: "#06D6A0", bg: "rgba(6,214,160,0.12)", border: "rgba(6,214,160,0.3)" };
  if (conf >= 45) return { label: "Moderate", color: "#FFB017", bg: "rgba(255,176,23,0.12)", border: "rgba(255,176,23,0.3)" };
  return { label: "Weak", color: "#5C5C78", bg: "rgba(92,92,120,0.1)", border: "rgba(92,92,120,0.2)" };
}

const numColor = (v: number) => v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-3)";

function ConfBar({ value }: { value: number }) {
  const badge = confBadge(value);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: "var(--surface-3)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${value}%`, background: badge.color, borderRadius: 2, transition: "width 400ms ease" }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color: badge.color, minWidth: 28, textAlign: "right" }}>{value}%</span>
    </div>
  );
}

// ── Expandable row ────────────────────────────────────────────────────────────
function StockRow({ r, strategy }: { r: ScreenerResult; strategy: Strategy }) {
  const [expanded, setExpanded] = useState(false);
  const badge = confBadge(r.confidence);
  const meta = STRATEGY_META[strategy];

  return (
    <>
      <tr
        onClick={() => setExpanded(x => !x)}
        style={{
          borderBottom: "1px solid var(--border)",
          cursor: "pointer",
          background: expanded ? "var(--surface-2)" : "transparent",
          transition: "background 120ms",
        }}
        onMouseEnter={e => !expanded && (e.currentTarget.style.background = "var(--card-hover)")}
        onMouseLeave={e => !expanded && (e.currentTarget.style.background = "transparent")}
      >
        {/* Symbol */}
        <td style={{ padding: "10px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: badge.bg, border: `1px solid ${badge.border}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 9, fontWeight: 800, color: badge.color, fontFamily: "var(--font-mono)",
              letterSpacing: "0.04em",
            }}>
              {r.symbol.slice(0, 4)}
            </div>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, fontWeight: 700, color: "var(--text-1)", letterSpacing: "-0.01em" }}>{r.symbol}</div>
              <div style={{ fontSize: 9, color: "var(--text-3)", fontFamily: "var(--font-body)", marginTop: 1 }}>NSE</div>
            </div>
          </div>
        </td>

        {/* Price */}
        <td style={{ padding: "10px 14px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
            ₹{r.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div style={{ fontSize: 11, color: numColor(r.change_pct), fontFamily: "var(--font-mono)", display: "flex", alignItems: "center", gap: 3 }}>
            {r.change_pct > 0 ? <TrendingUp style={{ width: 10, height: 10 }} /> : r.change_pct < 0 ? <TrendingDown style={{ width: 10, height: 10 }} /> : null}
            {r.change_pct > 0 ? "+" : ""}{r.change_pct.toFixed(2)}%
          </div>
        </td>

        {/* Confidence */}
        <td style={{ padding: "10px 14px", minWidth: 140 }}>
          <ConfBar value={r.confidence} />
          <div style={{
            display: "inline-flex", alignItems: "center", marginTop: 4,
            fontSize: 9, fontWeight: 700, color: badge.color,
            background: badge.bg, border: `1px solid ${badge.border}`,
            padding: "1px 7px", borderRadius: 99,
          }}>
            {badge.label}
          </div>
        </td>

        {/* Conditions met */}
        <td style={{ padding: "10px 14px" }}>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--green)", background: "rgba(6,214,160,0.1)", border: "1px solid rgba(6,214,160,0.25)", padding: "1px 7px", borderRadius: 99 }}>
              {r.matched_conditions.length}/{r.matched_conditions.length + r.failed_conditions.length} ✓
            </span>
          </div>
        </td>

        {/* RSI */}
        <td style={{ padding: "10px 14px" }}>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600,
            color: r.rsi > 70 ? "var(--red)" : r.rsi < 30 ? "var(--green)" : "var(--text-2)",
          }}>
            {r.rsi.toFixed(0)}
          </span>
        </td>

        {/* SL / TP */}
        <td style={{ padding: "10px 14px" }}>
          <div style={{ fontSize: 10, color: "var(--red)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
            SL ₹{r.sl.toLocaleString("en-IN")} <span style={{ color: "var(--text-4)" }}>({r.sl_pct.toFixed(1)}%)</span>
          </div>
          <div style={{ fontSize: 10, color: "var(--green)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
            TP1 ₹{r.tp1.toLocaleString("en-IN")} · TP2 ₹{r.tp2.toLocaleString("en-IN")}
          </div>
        </td>

        {/* Expand */}
        <td style={{ padding: "10px 14px", textAlign: "right" }}>
          {expanded ? <ChevronUp style={{ width: 14, height: 14, color: "var(--text-3)" }} /> : <ChevronDown style={{ width: 14, height: 14, color: "var(--text-4)" }} />}
        </td>
      </tr>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <tr style={{ background: "var(--surface-2)" }}>
            <td colSpan={7} style={{ padding: 0, borderBottom: "1px solid var(--border)" }}>
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                style={{ overflow: "hidden" }}
              >
                <div style={{ padding: "12px 14px 14px 62px", display: "flex", gap: 24, flexWrap: "wrap" }}>
                  {/* Conditions */}
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", marginBottom: 8 }}>CONDITIONS</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {[...r.matched_conditions.map(c => ({ name: c, pass: true })), ...r.failed_conditions.map(c => ({ name: c, pass: false }))].map((c, i) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          {c.pass
                            ? <CheckCircle2 style={{ width: 12, height: 12, color: "var(--green)", flexShrink: 0 }} />
                            : <XCircle style={{ width: 12, height: 12, color: "var(--red)", flexShrink: 0, opacity: 0.6 }} />}
                          <span style={{ fontSize: 11, color: c.pass ? "var(--text-2)" : "var(--text-4)", fontFamily: "var(--font-body)" }}>{c.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Indicators */}
                  <div style={{ minWidth: 160 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", marginBottom: 8 }}>INDICATORS</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {[
                        { label: "RSI (14)", value: r.rsi.toFixed(1) },
                        { label: "EMA 10", value: `₹${r.ema_10.toLocaleString("en-IN")}` },
                        { label: "EMA 20", value: `₹${r.ema_20.toLocaleString("en-IN")}` },
                      ].map(row => (
                        <div key={row.label} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                          <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>{row.label}</span>
                          <span style={{ fontSize: 11, color: "var(--text-1)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>{row.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Risk/Reward */}
                  <div style={{ minWidth: 200 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", marginBottom: 8 }}>RISK / REWARD</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {[
                        { label: "Entry (LTP)", value: `₹${r.ltp.toLocaleString("en-IN")}`, color: "var(--blue)" },
                        { label: `Stop Loss (−${r.sl_pct.toFixed(1)}%)`, value: `₹${r.sl.toLocaleString("en-IN")}`, color: "var(--red)" },
                        { label: "TP1 (1:3 R:R)", value: `₹${r.tp1.toLocaleString("en-IN")}`, color: "var(--green)" },
                        { label: "TP2 (1:5 R:R)", value: `₹${r.tp2.toLocaleString("en-IN")}`, color: "var(--green)" },
                      ].map(row => (
                        <div key={row.label} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                          <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>{row.label}</span>
                          <span style={{ fontSize: 11, color: row.color, fontFamily: "var(--font-mono)", fontWeight: 700 }}>{row.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Strategy info */}
                  <div style={{ alignSelf: "flex-start" }}>
                    <div style={{
                      padding: "8px 12px", borderRadius: 10,
                      background: `${meta.color}14`, border: `1px solid ${meta.color}30`,
                      maxWidth: 220,
                    }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: meta.color, marginBottom: 4, display: "flex", alignItems: "center", gap: 5 }}>
                        {meta.icon} {meta.label}
                      </div>
                      <div style={{ fontSize: 10.5, color: "var(--text-3)", lineHeight: 1.5, fontFamily: "var(--font-body)" }}>{meta.desc}</div>
                    </div>
                  </div>
                </div>
              </motion.div>
            </td>
          </tr>
        )}
      </AnimatePresence>
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function ScreenerPage() {
  const [strategy, setStrategy] = useState<Strategy>("vcp");
  const [tab, setTab] = useState<"all" | "matched">("all");
  const [minConf, setMinConf] = useState(0);
  const [minPrice, setMinPrice] = useState(0);
  const [maxPrice, setMaxPrice] = useState(0);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [scanning, setScanning] = useState(false);

  const triggerScan = useTriggerScan();
  const qc = useQueryClient();

  const query = useScreener(
    strategy,
    tab === "matched" ? 100 : minConf,
    minPrice,
    maxPrice,
    symbolFilter,
  );
  const data = query.data as import("@/api/market-queries").ScreenerResponse | undefined;
  const isLoading = query.isLoading;
  const isFetching = query.isFetching;

  const results: ScreenerResult[] = data?.results ?? [];
  const strong = results.filter(r => r.confidence >= 70);
  const moderate = results.filter(r => r.confidence >= 45 && r.confidence < 70);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerScan(strategy);
      await new Promise(r => setTimeout(r, 2000));
      await qc.invalidateQueries({ queryKey: ["screener"] });
    } finally {
      setScanning(false);
    }
  };

  const meta = STRATEGY_META[strategy];

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header title="Screener" subtitle="SwingAlgo SEPA · VCP · IPO Base · Rocket Base" />

      <div style={{ padding: "20px 24px", maxWidth: 1400, margin: "0 auto" }}>
        {/* Page header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20, gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 26, fontWeight: 700, color: "var(--text-1)", margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
              <ScanSearch style={{ width: 24, height: 24, color: "var(--blue)" }} />
              Stock Screener
            </h1>
            <div style={{ fontSize: 12, color: "var(--text-3)", fontFamily: "var(--font-body)", marginTop: 4 }}>
              {data?.universe_size ?? 140}+ NSE stocks · SwingAlgo SEPA framework · {data?.last_scan ? `Last scan: ${data.last_scan}` : "Cache warming..."}
            </div>
          </div>

          <button
            onClick={handleScan}
            disabled={scanning || (data?.is_scanning ?? false)}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              padding: "9px 18px", borderRadius: 10,
              background: "var(--blue)", color: "#fff",
              border: "none", cursor: scanning ? "wait" : "pointer",
              fontFamily: "var(--font-body)", fontSize: 12.5, fontWeight: 700,
              opacity: (scanning || data?.is_scanning) ? 0.7 : 1,
              transition: "all 150ms",
            }}
          >
            {scanning || data?.is_scanning
              ? <Loader2 style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} />
              : <RefreshCw style={{ width: 14, height: 14 }} />}
            {scanning ? "Scanning..." : data?.is_scanning ? "Scan Running..." : "Run Scan"}
          </button>
        </div>

        {/* Strategy tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
          {(Object.keys(STRATEGY_META) as Strategy[]).map(s => {
            const m = STRATEGY_META[s];
            const active = strategy === s;
            return (
              <button
                key={s}
                onClick={() => setStrategy(s)}
                style={{
                  display: "flex", alignItems: "center", gap: 7,
                  padding: "8px 16px", borderRadius: 10,
                  background: active ? `${m.color}18` : "var(--surface)",
                  border: `1px solid ${active ? m.color + "55" : "var(--border)"}`,
                  color: active ? m.color : "var(--text-3)",
                  cursor: "pointer", fontFamily: "var(--font-body)",
                  fontSize: 12.5, fontWeight: active ? 700 : 500,
                  transition: "all 150ms",
                }}
              >
                {m.icon}
                {m.label}
              </button>
            );
          })}

          {/* Matched Only tab */}
          <button
            onClick={() => setTab(t => t === "matched" ? "all" : "matched")}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              padding: "8px 16px", borderRadius: 10,
              background: tab === "matched" ? "rgba(6,214,160,0.12)" : "var(--surface)",
              border: `1px solid ${tab === "matched" ? "rgba(6,214,160,0.35)" : "var(--border)"}`,
              color: tab === "matched" ? "var(--green)" : "var(--text-3)",
              cursor: "pointer", fontFamily: "var(--font-body)",
              fontSize: 12.5, fontWeight: tab === "matched" ? 700 : 500,
              marginLeft: "auto",
              transition: "all 150ms",
            }}
          >
            <CheckCircle2 style={{ width: 13, height: 13 }} />
            Matched Only
          </button>
        </div>

        {/* Filters bar */}
        <div style={{
          display: "flex", gap: 10, marginBottom: 16, alignItems: "center",
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 12, padding: "10px 14px", flexWrap: "wrap",
        }}>
          <Filter style={{ width: 13, height: 13, color: "var(--text-3)", flexShrink: 0 }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.06em" }}>FILTERS</span>

          {/* Confidence slider */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)", whiteSpace: "nowrap" }}>Conf ≥</span>
            <input
              type="range" min={0} max={100} step={5}
              value={minConf}
              onChange={e => setMinConf(Number(e.target.value))}
              style={{ width: 80, accentColor: "var(--blue)", cursor: "pointer" }}
            />
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--blue)", fontFamily: "var(--font-mono)", minWidth: 30 }}>{minConf}%</span>
          </div>

          <div style={{ width: 1, height: 20, background: "var(--border)" }} />

          {/* Price range */}
          <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>Price ₹</span>
          <input
            type="number" placeholder="Min"
            value={minPrice || ""}
            onChange={e => setMinPrice(Number(e.target.value) || 0)}
            style={{
              width: 70, background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 7, padding: "4px 8px", color: "var(--text-1)",
              fontFamily: "var(--font-mono)", fontSize: 11.5, outline: "none",
            }}
          />
          <span style={{ fontSize: 11, color: "var(--text-4)" }}>—</span>
          <input
            type="number" placeholder="Max"
            value={maxPrice || ""}
            onChange={e => setMaxPrice(Number(e.target.value) || 0)}
            style={{
              width: 70, background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 7, padding: "4px 8px", color: "var(--text-1)",
              fontFamily: "var(--font-mono)", fontSize: 11.5, outline: "none",
            }}
          />

          <div style={{ width: 1, height: 20, background: "var(--border)" }} />

          {/* Symbol search */}
          <input
            type="text" placeholder="Symbol…"
            value={symbolFilter}
            onChange={e => setSymbolFilter(e.target.value)}
            style={{
              width: 100, background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 7, padding: "4px 10px", color: "var(--text-1)",
              fontFamily: "var(--font-mono)", fontSize: 12, outline: "none",
            }}
          />

          <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
            {/* Legend */}
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span style={{ fontSize: 9.5, fontWeight: 700, color: "#06D6A0", background: "rgba(6,214,160,0.12)", border: "1px solid rgba(6,214,160,0.3)", padding: "2px 8px", borderRadius: 99 }}>≥70% Strong</span>
              <span style={{ fontSize: 9.5, fontWeight: 700, color: "#FFB017", background: "rgba(255,176,23,0.12)", border: "1px solid rgba(255,176,23,0.3)", padding: "2px 8px", borderRadius: 99 }}>45–69% Moderate</span>
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
          {[
            { label: "Total Results", value: String(data?.total ?? 0), color: "var(--blue)" },
            { label: "Strong Setups", value: String(strong.length), color: "#06D6A0" },
            { label: "Moderate", value: String(moderate.length), color: "#FFB017" },
            { label: "Strategy", value: meta.label, color: meta.color },
          ].map(stat => (
            <div key={stat.label} style={{
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "10px 16px", flex: 1, minWidth: 100,
            }}>
              <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)", letterSpacing: "0.06em", marginBottom: 4 }}>{stat.label}</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: stat.color, fontFamily: "var(--font-mono)" }}>{stat.value}</div>
            </div>
          ))}
        </div>

        {/* Results table */}
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 14, overflow: "hidden",
          borderTop: `3px solid ${meta.color}`,
        }}>
          {isLoading ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 80, gap: 16 }}>
              <Loader2 style={{ width: 32, height: 32, color: "var(--blue)", animation: "spin 1s linear infinite" }} />
              <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text-3)" }}>
                Scanning {data?.universe_size ?? 140}+ stocks for {meta.label} setups...
              </div>
              <div style={{ fontSize: 11, color: "var(--text-4)" }}>This may take 60–90 seconds on first load</div>
            </div>
          ) : results.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 80, gap: 12 }}>
              <div style={{ fontSize: 40 }}>🔍</div>
              <div style={{ fontFamily: "var(--font-body)", fontSize: 14, fontWeight: 600, color: "var(--text-2)" }}>
                {data?.is_scanning ? "Scan in progress..." : "No setups found"}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-4)", textAlign: "center", maxWidth: 320 }}>
                {data?.is_scanning
                  ? "Results will appear when the scan completes. This takes ~60 seconds."
                  : "Try lowering the confidence filter or clicking Run Scan to refresh."}
              </div>
              {!data?.is_scanning && (
                <button
                  onClick={handleScan}
                  style={{
                    marginTop: 8, padding: "8px 20px", borderRadius: 8,
                    background: "var(--blue)", color: "#fff", border: "none",
                    cursor: "pointer", fontFamily: "var(--font-body)",
                    fontSize: 12, fontWeight: 600,
                  }}
                >
                  Run Scan Now
                </button>
              )}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                    {["Symbol", "Price", "Confidence", "Conditions", "RSI", "Risk/Reward", ""].map(h => (
                      <th key={h} style={{
                        padding: "8px 14px", textAlign: "left",
                        fontSize: 9.5, fontWeight: 700, color: "var(--text-3)",
                        letterSpacing: "0.08em", fontFamily: "var(--font-body)",
                        textTransform: "uppercase", whiteSpace: "nowrap",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.map(r => (
                    <StockRow key={r.symbol} r={r} strategy={strategy} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Footer */}
          {results.length > 0 && (
            <div style={{ padding: "8px 14px", borderTop: "1px solid var(--border)", background: "var(--surface-2)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
                {results.length} results · {isFetching ? "Refreshing..." : "Auto-refreshes every 5 min"}
              </span>
              <span style={{ fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
                ⚠ Not financial advice. For educational use only.
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
