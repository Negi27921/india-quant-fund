import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ScanSearch, RefreshCw, CheckCircle2, XCircle, TrendingUp, TrendingDown, ChevronDown, ChevronUp, Filter, Loader2, Rocket, Layers, Zap, ArrowUpRight, GitMerge, BarChart3, Globe, ExternalLink, Star, BookOpen, TrendingUp as PnlIcon, Calendar } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { useScreener, useTriggerScan, type ScreenerResult } from "@/api/market-queries";
import { useQueryClient } from "@tanstack/react-query";

// ── Paper Trade Types ─────────────────────────────────────────────────────────
interface PaperTrade {
  id: string;
  symbol: string;
  strategy: Strategy;
  entry_price: number;
  entry_time: string;   // ISO string
  entry_date: string;   // YYYY-MM-DD
  sl: number;
  tp1: number;
  tp2: number;
  sl_pct: number;
  confidence: number;
  current_price: number;
  last_updated: string;
  status: "open" | "sl_hit" | "tp1_hit" | "tp2_hit";
  exit_price?: number;
  exit_time?: string;
  pnl_pct?: number;
}

const PAPER_KEY = "iqf_paper_trades";

function loadPaperTrades(): PaperTrade[] {
  try { return JSON.parse(localStorage.getItem(PAPER_KEY) || "[]"); } catch { return []; }
}

function savePaperTrades(trades: PaperTrade[]) {
  localStorage.setItem(PAPER_KEY, JSON.stringify(trades));
}

function autoRecordTrade(r: ScreenerResult, strategy: Strategy): PaperTrade | null {
  const existing = loadPaperTrades();
  const alreadyOpen = existing.some(t => t.symbol === r.symbol && t.strategy === strategy && t.status === "open");
  if (alreadyOpen) return null;
  const now = new Date();
  const trade: PaperTrade = {
    id: `${r.symbol}_${strategy}_${now.getTime()}`,
    symbol: r.symbol,
    strategy,
    entry_price: r.ltp,
    entry_time: now.toISOString(),
    entry_date: now.toISOString().slice(0, 10),
    sl: r.sl,
    tp1: r.tp1,
    tp2: r.tp2,
    sl_pct: r.sl_pct,
    confidence: r.confidence,
    current_price: r.ltp,
    last_updated: now.toISOString(),
    status: "open",
  };
  savePaperTrades([trade, ...existing]);
  return trade;
}

function updatePaperPrices(results: ScreenerResult[]) {
  const trades = loadPaperTrades();
  let changed = false;
  const priceMap: Record<string, number> = {};
  results.forEach(r => { priceMap[r.symbol] = r.ltp; });
  const updated = trades.map(t => {
    if (t.status !== "open") return t;
    const price = priceMap[t.symbol];
    if (!price || price === t.current_price) return t;
    changed = true;
    let status: PaperTrade["status"] = "open";
    let exit_price: number | undefined;
    let exit_time: string | undefined;
    let pnl_pct: number | undefined;
    if (price <= t.sl) {
      status = "sl_hit"; exit_price = t.sl; exit_time = new Date().toISOString();
      pnl_pct = ((t.sl - t.entry_price) / t.entry_price) * 100;
    } else if (price >= t.tp2) {
      status = "tp2_hit"; exit_price = t.tp2; exit_time = new Date().toISOString();
      pnl_pct = ((t.tp2 - t.entry_price) / t.entry_price) * 100;
    } else if (price >= t.tp1) {
      status = "tp1_hit";
    }
    return { ...t, current_price: price, last_updated: new Date().toISOString(), status, exit_price, exit_time, pnl_pct };
  });
  if (changed) savePaperTrades(updated);
  return updated;
}

// ── Types ─────────────────────────────────────────────────────────────────────
type Strategy = "vcp" | "ipo_base" | "rocket_base" | "breakout" | "rsi_reversal" | "golden_cross" | "multibagger";
type Universe = "nifty500" | "full";

const STRATEGY_META: Record<Strategy, { label: string; icon: React.ReactNode; color: string; desc: string; badge?: string }> = {
  multibagger: {
    label: "Multibagger",
    icon: <Star style={{ width: 14, height: 14 }} />,
    color: "#f59e0b",
    badge: "⚡ CUSTOM",
    desc: "Engineered from 16 actual FY25-26 multi-baggers. EMA stack + RSI 55-78 + deep correction re-entry + volume surge + SMA200 slope. Defence · Power · Infra theme.",
  },
  vcp: {
    label: "VCP",
    icon: <Layers style={{ width: 14, height: 14 }} />,
    color: "var(--accent)",
    desc: "Volatility Contraction Pattern — 4-wave tightening with declining volume",
  },
  ipo_base: {
    label: "IPO Base",
    icon: <Zap style={{ width: 14, height: 14 }} />,
    color: "var(--green)",
    desc: "Tight base after a strong leg-up, EMA support, volume drying up",
  },
  rocket_base: {
    label: "Rocket Base",
    icon: <Rocket style={{ width: 14, height: 14 }} />,
    color: "var(--amber)",
    desc: "80%+ momentum move, now consolidating ≤20% from peak",
  },
  breakout: {
    label: "Breakout",
    icon: <ArrowUpRight style={{ width: 14, height: 14 }} />,
    color: "#a78bfa",
    desc: "Near 52W high (<3%), volume surge 1.8×, RSI 50–75 momentum zone",
  },
  rsi_reversal: {
    label: "RSI Reversal",
    icon: <BarChart3 style={{ width: 14, height: 14 }} />,
    color: "#2dd4bf",
    desc: "RSI recovered from oversold (<35) with volume confirmation",
  },
  golden_cross: {
    label: "Golden Cross",
    icon: <GitMerge style={{ width: 14, height: 14 }} />,
    color: "#fbbf24",
    desc: "EMA20 > EMA50 fresh cross, price above SMA200, volume surge",
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function confBadge(conf: number): { label: string; color: string; bg: string; border: string } {
  if (conf >= 70) return { label: "Strong", color: "var(--green)", bg: "var(--green-dim)", border: "rgba(34,197,94,0.3)" };
  if (conf >= 45) return { label: "Moderate", color: "var(--amber)", bg: "var(--amber-dim)", border: "rgba(249,115,22,0.3)" };
  return { label: "Weak", color: "var(--text-3)", bg: "var(--surface-3)", border: "var(--border)" };
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

const rowVariants = {
  hidden: { opacity: 0, x: -10 },
  visible: (i: number) => ({
    opacity: 1, x: 0,
    transition: { delay: Math.min(i * 0.04, 0.6), duration: 0.22, ease: "easeOut" },
  }),
};

// ── Expandable row ────────────────────────────────────────────────────────────
function StockRow({ r, strategy, index }: { r: ScreenerResult; strategy: Strategy; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const badge = confBadge(r.confidence);
  const meta = STRATEGY_META[strategy];

  return (
    <>
      <motion.tr
        custom={index}
        variants={rowVariants}
        initial="hidden"
        animate="visible"
        onClick={() => setExpanded(x => !x)}
        style={{
          borderBottom: "1px solid var(--border)",
          cursor: "pointer",
          background: expanded ? "var(--surface-2)" : "transparent",
          transition: "background 120ms",
        }}
        onMouseEnter={e => !expanded && ((e.currentTarget as HTMLElement).style.background = "var(--card-hover)")}
        onMouseLeave={e => !expanded && ((e.currentTarget as HTMLElement).style.background = "transparent")}
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
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--green)", background: "rgba(39,174,96,0.1)", border: "1px solid rgba(39,174,96,0.25)", padding: "1px 7px", borderRadius: 99 }}>
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

        {/* Chart / TradingView */}
        <td style={{ padding: "10px 12px", textAlign: "right" }} onClick={e => e.stopPropagation()}>
          <a
            href={`https://www.tradingview.com/chart/?symbol=NSE:${r.symbol}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              padding: "4px 9px", borderRadius: 5,
              background: "var(--accent-dim)", border: "1px solid var(--accent-border)",
              color: "var(--accent)", fontSize: 9.5, fontWeight: 700,
              fontFamily: "var(--font-body)", textDecoration: "none",
              letterSpacing: "0.05em",
              transition: "all 120ms",
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLAnchorElement).style.background = "rgba(0,229,53,0.18)";
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLAnchorElement).style.background = "var(--accent-dim)";
            }}
          >
            <ExternalLink style={{ width: 10, height: 10 }} />
            TV
          </a>
        </td>

        {/* Expand */}
        <td style={{ padding: "10px 10px", textAlign: "right" }}>
          {expanded ? <ChevronUp style={{ width: 14, height: 14, color: "var(--text-3)" }} /> : <ChevronDown style={{ width: 14, height: 14, color: "var(--text-4)" }} />}
        </td>
      </motion.tr>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <tr style={{ background: "var(--surface-2)" }}>
            <td colSpan={8} style={{ padding: 0, borderBottom: "1px solid var(--border)" }}>
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
                        { label: "Entry (LTP)", value: `₹${r.ltp.toLocaleString("en-IN")}`, color: "var(--accent)" },
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

// ── Strategy P&L Breakdown card ───────────────────────────────────────────────
function StratPnlCard({
  strategyKey, trades, active, onToggle,
}: {
  strategyKey: string;
  trades: PaperTrade[];
  active: boolean;
  onToggle: () => void;
}) {
  const meta = STRATEGY_META[strategyKey as Strategy];
  const color = meta?.color ?? "var(--accent)";
  const closed = trades.filter(t => t.status !== "open" && t.pnl_pct != null);
  const open   = trades.filter(t => t.status === "open");
  const won    = closed.filter(t => (t.pnl_pct ?? 0) > 0).length;
  const totalPnl = closed.reduce((s, t) => s + (t.pnl_pct ?? 0), 0);
  const openPnl  = open.reduce((s, t) => s + ((t.current_price - t.entry_price) / t.entry_price) * 100, 0);
  const winRate  = closed.length > 0 ? (won / closed.length) * 100 : 0;

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.97 }}
      onClick={onToggle}
      style={{
        cursor: "pointer", borderRadius: 12, padding: "12px 16px",
        background: active ? `${color}14` : "var(--surface)",
        border: `1px solid ${active ? color + "55" : "var(--border)"}`,
        boxShadow: active ? `0 0 16px ${color}22` : "none",
        transition: "all 160ms",
        borderTop: `3px solid ${color}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <span style={{ color, fontSize: 13 }}>{meta?.icon}</span>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-body)" }}>{meta?.label ?? strategyKey}</span>
        {active && <span style={{ fontSize: 8, fontWeight: 800, background: color, color: "#000", padding: "1px 5px", borderRadius: 4, marginLeft: "auto" }}>FILTER ON</span>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px" }}>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.06em" }}>CLOSED P&L</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: totalPnl >= 0 ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)" }}>
            {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(1)}%
          </div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.06em" }}>OPEN P&L</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: openPnl >= 0 ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)" }}>
            {openPnl >= 0 ? "+" : ""}{openPnl.toFixed(1)}%
          </div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.06em" }}>WIN RATE</div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-mono)" }}>
            {closed.length > 0 ? `${winRate.toFixed(0)}%` : "—"}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-3)", letterSpacing: "0.06em" }}>TRADES</div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-mono)" }}>
            {open.length}✦ / {closed.length}✓
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ── Paper Trade Row ───────────────────────────────────────────────────────────
function PaperTradeRow({ trade }: { trade: PaperTrade }) {
  const pnlPct = trade.status === "open"
    ? ((trade.current_price - trade.entry_price) / trade.entry_price) * 100
    : (trade.pnl_pct ?? 0);
  const pnlColor = pnlPct > 0 ? "var(--green)" : pnlPct < 0 ? "var(--red)" : "var(--text-3)";

  const statusBadge = {
    open:    { label: "OPEN",    color: "var(--accent)",  bg: "var(--accent-dim)", border: "var(--accent-border)" },
    sl_hit:  { label: "SL HIT",  color: "var(--red)",    bg: "var(--red-dim)",    border: "rgba(248,113,113,0.3)" },
    tp1_hit: { label: "TP1 ✓",   color: "var(--green)",  bg: "var(--green-dim)",  border: "rgba(52,211,153,0.3)" },
    tp2_hit: { label: "TP2 ✓✓",  color: "var(--green)",  bg: "var(--green-dim)",  border: "rgba(52,211,153,0.3)" },
  }[trade.status];

  const meta = STRATEGY_META[trade.strategy];

  return (
    <tr style={{ borderBottom: "1px solid var(--border)", transition: "background 100ms" }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--card-hover)")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      <td style={{ padding: "8px 14px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, fontWeight: 700, color: "var(--text-1)" }}>{trade.symbol}</div>
        <div style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)", marginTop: 1 }}>
          {new Date(trade.entry_time).toLocaleString("en-IN", { dateStyle: "short", timeStyle: "short" })}
        </div>
      </td>
      <td style={{ padding: "8px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ color: meta?.color ?? "var(--accent)", fontSize: 11 }}>{meta?.icon}</span>
          <span style={{ fontSize: 11, color: "var(--text-2)", fontFamily: "var(--font-body)" }}>{meta?.label ?? trade.strategy}</span>
        </div>
      </td>
      <td style={{ padding: "8px 14px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-2)" }}>
          ₹{trade.entry_price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </td>
      <td style={{ padding: "8px 14px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, color: pnlColor }}>
          ₹{trade.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        {trade.status === "open" && (
          <div style={{ fontSize: 10, color: pnlColor, fontFamily: "var(--font-mono)", display: "flex", alignItems: "center", gap: 2 }}>
            {pnlPct > 0 ? <TrendingUp style={{ width: 9, height: 9 }} /> : pnlPct < 0 ? <TrendingDown style={{ width: 9, height: 9 }} /> : null}
            {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
          </div>
        )}
      </td>
      <td style={{ padding: "8px 14px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: pnlColor }}>
          {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
        </div>
      </td>
      <td style={{ padding: "8px 14px" }}>
        <div style={{ fontSize: 10, color: "var(--red)", fontFamily: "var(--font-mono)" }}>SL ₹{trade.sl.toLocaleString("en-IN")}</div>
        <div style={{ fontSize: 10, color: "var(--green)", fontFamily: "var(--font-mono)" }}>TP1 ₹{trade.tp1.toLocaleString("en-IN")}</div>
      </td>
      <td style={{ padding: "8px 14px" }}>
        <span style={{
          fontSize: 9, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
          background: statusBadge.bg, color: statusBadge.color,
          border: `1px solid ${statusBadge.border}`,
          fontFamily: "var(--font-body)", letterSpacing: "0.05em",
        }}>
          {statusBadge.label}
        </span>
        {trade.confidence >= 70 && (
          <div style={{ fontSize: 8, color: "var(--green)", marginTop: 2, fontFamily: "var(--font-body)" }}>STRONG</div>
        )}
      </td>
    </tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function ScreenerPage() {
  const [strategy, setStrategy] = useState<Strategy>("vcp");
  const [tab, setTab] = useState<"screener" | "trades">("screener");
  const [universe, setUniverse] = useState<Universe>("full");
  const [minConf, setMinConf] = useState(0);
  const [minPrice, setMinPrice] = useState(0);
  const [maxPrice, setMaxPrice] = useState(0);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [scanning, setScanning] = useState(false);
  const [stratPnlFilter, setStratPnlFilter] = useState<string | null>(null);

  // Paper trade state
  const [paperTrades, setPaperTrades] = useState<PaperTrade[]>(loadPaperTrades);
  const [ptFromDate, setPtFromDate] = useState("");
  const [ptToDate, setPtToDate] = useState("");
  const [ptStatusFilter, setPtStatusFilter] = useState<"all" | "open" | "closed">("all");

  const triggerScan = useTriggerScan();
  const qc = useQueryClient();

  const query = useScreener(
    strategy,
    minConf,
    minPrice,
    maxPrice,
    symbolFilter,
    universe,
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
      await triggerScan(strategy, universe);
      await new Promise(r => setTimeout(r, 2000));
      await qc.invalidateQueries({ queryKey: ["screener"] });
    } finally {
      setScanning(false);
    }
  };

  // Auto-trigger scan on mount if last_scan is null or >30 min old
  useEffect(() => {
    if (data === undefined) return;
    const shouldScan = !data.last_scan || (() => {
      const lastScanTime = new Date(data.last_scan).getTime();
      return Date.now() - lastScanTime > 30 * 60 * 1000;
    })();
    if (shouldScan && !data.is_scanning && !scanning) {
      handleScan();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.last_scan, data?.is_scanning]);

  // Poll every 8s while a scan is running so results appear as soon as ready
  useEffect(() => {
    if (!data?.is_scanning) return;
    const id = setInterval(() => {
      qc.invalidateQueries({ queryKey: ["screener"] });
    }, 8_000);
    return () => clearInterval(id);
  }, [data?.is_scanning, qc]);

  // Auto-record high-confidence screener results as paper trades
  const autoRecord = useCallback(() => {
    if (!results.length) return;
    const highConf = results.filter(r => r.confidence >= 70);
    let updated = false;
    highConf.forEach(r => {
      const recorded = autoRecordTrade(r, strategy);
      if (recorded) updated = true;
    });
    // Also update prices for existing open paper trades
    const newTrades = updatePaperPrices(results);
    if (updated || newTrades.some((t, i) => t.current_price !== paperTrades[i]?.current_price)) {
      setPaperTrades(loadPaperTrades());
    }
  }, [results, strategy]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { autoRecord(); }, [autoRecord]);

  // Group paper trades by strategy for P&L breakdown
  const tradesByStrategy = (Object.keys(STRATEGY_META) as Strategy[]).reduce<Record<string, PaperTrade[]>>((acc, s) => {
    acc[s] = paperTrades.filter(t => t.strategy === s);
    return acc;
  }, {});

  // Filtered paper trades for trade log
  const filteredPaperTrades = paperTrades.filter(t => {
    if (stratPnlFilter && t.strategy !== stratPnlFilter) return false;
    if (ptStatusFilter === "open" && t.status !== "open") return false;
    if (ptStatusFilter === "closed" && t.status === "open") return false;
    if (ptFromDate && t.entry_date < ptFromDate) return false;
    if (ptToDate && t.entry_date > ptToDate) return false;
    return true;
  });

  const meta = STRATEGY_META[strategy];

  return (
    <div style={{ background: "var(--bg)", minHeight: "100vh" }}>
      <Header title="Screener" />

      <div style={{ padding: "20px 24px", maxWidth: 1400, margin: "0 auto" }}>
        {/* Page header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20, gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 26, fontWeight: 700, color: "var(--text-1)", margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
              <ScanSearch style={{ width: 24, height: 24, color: "var(--accent)" }} />
              Stock Screener
            </h1>
            <div style={{ fontSize: 11.5, color: "var(--text-3)", fontFamily: "var(--font-body)", marginTop: 4 }}>
              Universe: <span style={{ color: "var(--accent)", fontWeight: 700 }}>{data?.universe_size ?? (universe === "full" ? 2137 : 503)}</span> NSE stocks
              {data?.is_scanning && data?.scanned != null && data.scanned > 0 ? (
                <> · <span style={{ color: "var(--amber)", fontWeight: 600 }}>
                  Scanning: {data.scanned}/{data.universe_size ?? (universe === "full" ? 2137 : 503)} stocks
                </span>
                {data.total > 0 && <> · <span style={{ color: "var(--green)", fontWeight: 600 }}>{data.total} found so far</span></>}
                </>
              ) : data?.total != null ? (
                <> · {data.total} results
                  {" · "}<span style={{ color: "var(--green)", fontWeight: 600 }}>{strong.length} Strong</span>
                  {" · "}<span style={{ color: "var(--amber)", fontWeight: 600 }}>{moderate.length} Moderate</span>
                </>
              ) : null}
              {!data?.is_scanning && (data?.last_scan ? <> · Last scan: {data.last_scan}</> : <> · <span style={{ color: "var(--amber)" }}>Scan in progress — results stream as each 100-stock batch completes</span></>)}
            </div>
          </div>

          <button
            onClick={handleScan}
            disabled={scanning || (data?.is_scanning ?? false)}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              padding: "9px 18px", borderRadius: 10,
              background: "var(--accent)", color: "#fff",
              border: "none", cursor: scanning ? "wait" : "pointer",
              fontFamily: "var(--font-body)", fontSize: 12.5, fontWeight: 700,
              opacity: (scanning || data?.is_scanning) ? 0.7 : 1,
              transition: "all 150ms",
            }}
          >
            {scanning || data?.is_scanning
              ? <Loader2 style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} />
              : <RefreshCw style={{ width: 14, height: 14 }} />}
            {scanning ? "Scanning..." : data?.is_scanning ? "Scan Running..." : "Refresh Scan"}
          </button>
        </div>

        {/* Strategy tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
          {(Object.keys(STRATEGY_META) as Strategy[]).map(s => {
            const m = STRATEGY_META[s];
            const active = strategy === s;
            const isMultibagger = s === "multibagger";
            return (
              <motion.button
                key={s}
                onClick={() => setStrategy(s)}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                style={{
                  display: "flex", alignItems: "center", gap: 7,
                  padding: isMultibagger ? "8px 18px" : "8px 16px",
                  borderRadius: 10,
                  background: active
                    ? isMultibagger ? `linear-gradient(135deg, #f59e0b28, #d97706 18)` : `${m.color}18`
                    : isMultibagger ? "linear-gradient(135deg, #f59e0b10, #78350f08)" : "var(--surface)",
                  border: `1px solid ${active ? m.color + "77" : isMultibagger ? "#f59e0b44" : "var(--border)"}`,
                  color: active ? m.color : isMultibagger ? "#f59e0b" : "var(--text-3)",
                  cursor: "pointer", fontFamily: "var(--font-body)",
                  fontSize: 12.5, fontWeight: active || isMultibagger ? 700 : 500,
                  transition: "all 150ms",
                  boxShadow: active && isMultibagger ? "0 0 16px #f59e0b33" : "none",
                  position: "relative",
                }}
              >
                {m.icon}
                {m.label}
                {isMultibagger && (
                  <span style={{
                    fontSize: 8, fontWeight: 800, letterSpacing: "0.08em",
                    background: "linear-gradient(90deg,#f59e0b,#d97706)",
                    color: "#000", padding: "1px 5px", borderRadius: 4, marginLeft: 2,
                  }}>
                    CUSTOM
                  </span>
                )}
              </motion.button>
            );
          })}

          {/* Tab switcher */}
          <div style={{ marginLeft: "auto", display: "flex", gap: 4, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 3 }}>
            {([
              { id: "screener", label: "Screener", icon: <ScanSearch style={{ width: 12, height: 12 }} /> },
              { id: "trades",   label: `Trades ${paperTrades.length > 0 ? `(${paperTrades.length})` : ""}`, icon: <BookOpen style={{ width: 12, height: 12 }} /> },
            ] as { id: "screener" | "trades"; label: string; icon: React.ReactNode }[]).map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "6px 14px", borderRadius: 7, cursor: "pointer",
                  background: tab === t.id ? "var(--accent)" : "transparent",
                  color: tab === t.id ? "#fff" : "var(--text-3)",
                  border: "none", fontFamily: "var(--font-body)",
                  fontSize: 12, fontWeight: tab === t.id ? 700 : 500,
                  transition: "all 150ms",
                }}
              >
                {t.icon} {t.label}
              </button>
            ))}
          </div>

          {/* Universe selector */}
          <button
            onClick={() => setUniverse(u => u === "nifty500" ? "full" : "nifty500")}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              padding: "8px 14px", borderRadius: 10,
              background: universe === "full" ? "var(--accent-dim)" : "var(--surface)",
              border: `1px solid ${universe === "full" ? "var(--accent-border)" : "var(--border)"}`,
              color: universe === "full" ? "var(--accent)" : "var(--text-3)",
              cursor: "pointer", fontFamily: "var(--font-body)",
              fontSize: 11.5, fontWeight: universe === "full" ? 700 : 500,
              transition: "all 150ms",
            }}
            title={universe === "full" ? "Scanning all 2,137 NSE stocks (15-20 min first scan)" : "Switch to Nifty 500 (503 stocks, faster)"}
          >
            <Globe style={{ width: 12, height: 12 }} />
            {universe === "full" ? "All NSE · 2,137" : "Nifty 500 · 503"}
          </button>
        </div>

        {/* Multibagger info banner */}
        <AnimatePresence>
          {strategy === "multibagger" && (
            <motion.div
              initial={{ opacity: 0, y: -8, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -8, height: 0 }}
              transition={{ duration: 0.22 }}
              style={{
                marginBottom: 16, padding: "14px 18px",
                background: "linear-gradient(135deg, #f59e0b0d, #92400e06)",
                border: "1px solid #f59e0b40", borderRadius: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <Star style={{ width: 15, height: 15, color: "#f59e0b" }} />
                <span style={{ fontSize: 11, fontWeight: 800, color: "#f59e0b", letterSpacing: "0.08em" }}>
                  CUSTOM MULTIBAGGER SCREENER — Built from Your Actual FY2025-26 Winners
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 24px" }}>
                {[
                  { label: "Technical DNA", value: "EMA9>20>50 · RSI 55–78 · SMA200 slope ↑ · 90d low recovery ≥15%", src: "Price analysis of 16 stocks" },
                  { label: "Revenue Accel Proxy", value: "90d momentum > ½ × 180d momentum — stock pricing in order wins before announcements", src: "Concall research: GVT&D +58% rev, NETWEB +141% rev, TDPOWER +27%" },
                  { label: "Institutional Accum.", value: "5-day avg volume > 20-day avg volume — mirrors post-rating-upgrade/concall buying", src: "CRISIL upgrades: Netweb A→, TD Power Positive, CG Power AAA, Paras Positive" },
                  { label: "Volume Re-entry", value: "Recent 3d vol ≥ 1.5× 20d avg — same signal seen at every re-entry point", src: "Vol ratio ranged 1.44×–6.81× across all 16 winners" },
                  { label: "Policy Sectors", value: "Defence · Power T&D · Railways · AI/Data Centres · EV Electronics · Smart Cities", src: "₹9L Cr T&D · Kavach ₹50k Cr · IndiaAI ₹10k Cr · Op. Sindoor emergency procurement" },
                  { label: "Not Extended", value: "Price within 20% of EMA50 — entry zone before parabolic move, not chasing", src: "Mean entry was 27% below 52W high — they corrected before exploding" },
                ].map(row => (
                  <div key={row.label} style={{ borderLeft: "2px solid #f59e0b33", paddingLeft: 10 }}>
                    <div style={{ fontSize: 9.5, fontWeight: 800, color: "#f59e0b", letterSpacing: "0.06em", marginBottom: 2 }}>{row.label}</div>
                    <div style={{ fontSize: 10.5, color: "var(--text-2)", fontFamily: "var(--font-body)", lineHeight: 1.5, marginBottom: 2 }}>{row.value}</div>
                    <div style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)", fontStyle: "italic" }}>Source: {row.src}</div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

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
              style={{ width: 80, accentColor: "var(--accent)", cursor: "pointer" }}
            />
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--accent)", fontFamily: "var(--font-mono)", minWidth: 30 }}>{minConf}%</span>
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
              <span style={{ fontSize: 9.5, fontWeight: 700, color: "#27AE60", background: "rgba(39,174,96,0.12)", border: "1px solid rgba(39,174,96,0.3)", padding: "2px 8px", borderRadius: 99 }}>≥70% Strong</span>
              <span style={{ fontSize: 9.5, fontWeight: 700, color: "#FFB017", background: "rgba(255,176,23,0.12)", border: "1px solid rgba(255,176,23,0.3)", padding: "2px 8px", borderRadius: 99 }}>45–69% Moderate</span>
            </div>
          </div>
        </div>

        {tab === "screener" && <>
        {/* Stats row */}
        <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
          {[
            { label: "Total Results", value: String(data?.total ?? 0), color: "var(--accent)" },
            { label: "Strong Setups", value: String(strong.length), color: "#27AE60" },
            { label: "Moderate", value: String(moderate.length), color: "#FFB017" },
            { label: "Strategy", value: meta.label, color: meta.color },
          ].map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.07, duration: 0.25 }}
              style={{
                background: "var(--surface)", border: "1px solid var(--border)",
                borderRadius: 10, padding: "10px 16px", flex: 1, minWidth: 100,
              }}
            >
              <div style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)", letterSpacing: "0.06em", marginBottom: 4 }}>{stat.label}</div>
              <motion.div
                key={stat.value}
                initial={{ opacity: 0, scale: 0.85 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.2 }}
                style={{ fontSize: 20, fontWeight: 800, color: stat.color, fontFamily: "var(--font-mono)" }}
              >
                {stat.value}
              </motion.div>
            </motion.div>
          ))}
        </div>

        {/* Results table */}
        <div style={{
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: 14, overflow: "hidden",
          borderTop: `3px solid ${meta.color}`,
        }}>
          {/* Scan-in-progress banner — shown above stale results */}
          <AnimatePresence>
            {(scanning || data?.is_scanning) && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "10px 16px",
                  background: "var(--accent-dim)",
                  borderBottom: "1px solid var(--accent-border)",
                }}
              >
                <Loader2 style={{ width: 14, height: 14, color: "var(--accent)", animation: "spin 1s linear infinite", flexShrink: 0 }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)", fontFamily: "var(--font-body)" }}>
                  Scan in progress — showing last results
                </span>
              </motion.div>
            )}
          </AnimatePresence>

          {isLoading ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 80, gap: 16 }}
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
              >
                <Loader2 style={{ width: 32, height: 32, color: "var(--accent)" }} />
              </motion.div>
              <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text-3)" }}>
                Loading cached results...
              </div>
            </motion.div>
          ) : results.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 80, gap: 12 }}>
              <div style={{ fontSize: 40 }}>🔍</div>
              <div style={{ fontFamily: "var(--font-body)", fontSize: 14, fontWeight: 600, color: "var(--text-2)" }}>
                {data?.is_scanning ? "First scan in progress..." : "No setups found"}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-4)", textAlign: "center", maxWidth: 320 }}>
                {data?.is_scanning
                  ? "Results will appear here as soon as the scan completes (~20–60s)."
                  : "Try lowering the confidence filter or click Refresh Scan."}
              </div>
              {!data?.is_scanning && (
                <button
                  onClick={handleScan}
                  style={{
                    marginTop: 8, padding: "8px 20px", borderRadius: 8,
                    background: "var(--accent)", color: "#fff", border: "none",
                    cursor: "pointer", fontFamily: "var(--font-body)",
                    fontSize: 12, fontWeight: 600,
                  }}
                >
                  Refresh Scan
                </button>
              )}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
                    {["Symbol", "Price", "Confidence", "Conditions", "RSI", "Risk/Reward", "", ""].map(h => (
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
                  {results.map((r, i) => (
                    <StockRow key={r.symbol} r={r} strategy={strategy} index={i} />
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
        </>}

        {/* ── Paper Trades Tab ─────────────────────────────────────────────────── */}
        {tab === "trades" && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
            {/* Strategy P&L Breakdown cards — clickable filters */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <PnlIcon style={{ width: 14, height: 14, color: "var(--accent)" }} />
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-body)", letterSpacing: "0.04em" }}>
                  STRATEGY P&L BREAKDOWN
                </span>
                <span style={{ fontSize: 10, color: "var(--text-3)" }}>· click to filter</span>
                {stratPnlFilter && (
                  <button onClick={() => setStratPnlFilter(null)}
                    style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-3)", background: "none", border: "none", cursor: "pointer" }}>
                    Clear filter ✕
                  </button>
                )}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10 }}>
                {(Object.keys(STRATEGY_META) as Strategy[]).map(s => (
                  <StratPnlCard
                    key={s}
                    strategyKey={s}
                    trades={tradesByStrategy[s] ?? []}
                    active={stratPnlFilter === s}
                    onToggle={() => setStratPnlFilter(prev => prev === s ? null : s)}
                  />
                ))}
              </div>
            </div>

            {/* Paper Trade Log */}
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, overflow: "hidden" }}>
              {/* Header + filters */}
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <BookOpen style={{ width: 14, height: 14, color: "var(--accent)" }} />
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-body)" }}>
                  Paper Trade Log
                </span>
                <span style={{ fontSize: 10, background: "var(--accent-dim)", color: "var(--accent)", padding: "1px 8px", borderRadius: 99, fontWeight: 700 }}>
                  {filteredPaperTrades.length} trades
                </span>

                <div style={{ display: "flex", alignItems: "center", gap: 5, marginLeft: 8 }}>
                  <Calendar style={{ width: 10, height: 10, color: "var(--text-3)" }} />
                  {[
                    { label: "From", value: ptFromDate, onChange: setPtFromDate },
                    { label: "To",   value: ptToDate,   onChange: setPtToDate },
                  ].map(f => (
                    <input key={f.label} type="date" value={f.value}
                      onChange={e => f.onChange(e.target.value)}
                      title={f.label}
                      style={{
                        background: "var(--surface-2)", border: "1px solid var(--border)",
                        borderRadius: 4, padding: "2px 6px", color: "var(--text-1)",
                        fontFamily: "var(--font-mono)", fontSize: 10, outline: "none",
                        colorScheme: "dark",
                      }}
                    />
                  ))}
                  {(ptFromDate || ptToDate) && (
                    <button onClick={() => { setPtFromDate(""); setPtToDate(""); }}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-4)", fontSize: 10 }}>✕</button>
                  )}
                </div>

                <div style={{ display: "flex", gap: 4 }}>
                  {(["all", "open", "closed"] as const).map(s => (
                    <button key={s} onClick={() => setPtStatusFilter(s)}
                      style={{
                        fontSize: 10, padding: "3px 10px", borderRadius: 6, cursor: "pointer",
                        background: ptStatusFilter === s ? "var(--accent-dim)" : "var(--surface-2)",
                        color: ptStatusFilter === s ? "var(--accent)" : "var(--text-3)",
                        border: `1px solid ${ptStatusFilter === s ? "var(--accent-border)" : "var(--border)"}`,
                        fontFamily: "var(--font-body)", fontWeight: 600,
                      }}>
                      {s.charAt(0).toUpperCase() + s.slice(1)}
                    </button>
                  ))}
                </div>

                {paperTrades.length > 0 && (
                  <button
                    onClick={() => { savePaperTrades([]); setPaperTrades([]); }}
                    style={{ marginLeft: "auto", fontSize: 10, color: "var(--red)", background: "none", border: "none", cursor: "pointer" }}
                  >
                    Clear All
                  </button>
                )}
              </div>

              {filteredPaperTrades.length === 0 ? (
                <div style={{ padding: 60, textAlign: "center" }}>
                  <div style={{ fontSize: 36, marginBottom: 12 }}>📋</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-2)", fontFamily: "var(--font-body)", marginBottom: 6 }}>
                    No paper trades yet
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-body)", maxWidth: 320, margin: "0 auto" }}>
                    High-confidence screener results (≥70%) are automatically recorded as paper trades at scan price. Run a scan to get started.
                  </div>
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                        {["Symbol · Entry Time", "Strategy", "Entry ₹", "CMP · Change", "P&L %", "SL / TP1", "Status"].map(h => (
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
                      {filteredPaperTrades.map(t => <PaperTradeRow key={t.id} trade={t} />)}
                    </tbody>
                  </table>
                </div>
              )}

              <div style={{ padding: "8px 14px", borderTop: "1px solid var(--border)", background: "var(--surface-2)", display: "flex", gap: 16, alignItems: "center" }}>
                {(() => {
                  const closed = paperTrades.filter(t => t.status !== "open" && t.pnl_pct != null);
                  const open   = paperTrades.filter(t => t.status === "open");
                  const totalPnl = closed.reduce((s, t) => s + (t.pnl_pct ?? 0), 0);
                  const winRate  = closed.length > 0 ? (closed.filter(t => (t.pnl_pct ?? 0) > 0).length / closed.length) * 100 : 0;
                  return (
                    <>
                      <span style={{ fontSize: 10, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>
                        Open: <b style={{ color: "var(--accent)" }}>{open.length}</b> &nbsp;
                        Closed: <b style={{ color: "var(--text-1)" }}>{closed.length}</b> &nbsp;
                        Closed P&L: <b style={{ color: totalPnl >= 0 ? "var(--green)" : "var(--red)" }}>{totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(1)}%</b> &nbsp;
                        Win Rate: <b style={{ color: "var(--text-1)" }}>{closed.length > 0 ? `${winRate.toFixed(0)}%` : "—"}</b>
                      </span>
                      <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
                        ⚠ Paper trades — educational only. Auto-recorded at screener scan time.
                      </span>
                    </>
                  );
                })()}
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
