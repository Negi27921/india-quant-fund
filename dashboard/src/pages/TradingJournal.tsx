import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { NSE_STOCKS } from "@/lib/nse-stocks";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen, Plus, Trash2, TrendingUp, TrendingDown,
  DollarSign, Target, BarChart2, Brain, Send, Loader2,
  X, ChevronDown, ChevronUp, AlertCircle,
  User, RefreshCw, Award,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { StatCard } from "@/components/ui/StatCard";
import { api } from "@/api/client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Trade {
  id: string;
  stockName: string;
  buyPrice: number;
  quantity: number;
  entryDate: string;
  capitalUsed: number;
  tradeType: "Swing" | "Investment";
  status: "Open" | "Closed";
  sellPrice?: number;
  exitDate?: string;
  strategy?: string;
  notes?: string;
  plannedStopLoss?: number;
  plannedTarget?: number;
  emotionEntry?: string;
  emotionExit?: string;
  marketCondition?: string;
  ruleFollowed?: "Yes" | "No" | "Partial";
  createdAt: string;
}

interface Message { role: "user" | "assistant"; content: string; }

interface Metrics {
  totalInvested: number;
  realizedPnL: number;
  winRate: number;
  totalTrades: number;
  closedTrades: number;
  openTrades: number;
  avgProfit: number;
  avgLoss: number;
  profitFactor: number;
  bestTrade: number;
  worstTrade: number;
}

// ── Storage ───────────────────────────────────────────────────────────────────

const STORAGE_KEY = "op_journal_trades_v1";

// One-time migration: copy data from legacy key so no trades are lost
if (typeof window !== "undefined" && !localStorage.getItem(STORAGE_KEY) && localStorage.getItem("iqf_journal_trades_v1")) {
  localStorage.setItem(STORAGE_KEY, localStorage.getItem("iqf_journal_trades_v1")!);
  localStorage.removeItem("iqf_journal_trades_v1");
}

function loadTrades(): Trade[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Trade[]) : [];
  } catch { return []; }
}

function saveTrades(trades: Trade[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(trades));
}

// ── Metrics ───────────────────────────────────────────────────────────────────

function calcMetrics(trades: Trade[]): Metrics {
  const closed = trades.filter(t => t.status === "Closed" && t.sellPrice != null);
  const open = trades.filter(t => t.status === "Open");
  const pnls = closed.map(t => ((t.sellPrice! - t.buyPrice) / t.buyPrice) * 100 > 0
    ? (t.sellPrice! - t.buyPrice) * t.quantity
    : (t.sellPrice! - t.buyPrice) * t.quantity
  );
  const realizedPnL = pnls.reduce((a, b) => a + b, 0);
  const wins = pnls.filter(p => p > 0);
  const losses = pnls.filter(p => p < 0);
  const totalInvested = open.reduce((s, t) => s + t.capitalUsed, 0);
  const sumWins = wins.reduce((a, b) => a + b, 0);
  const sumLosses = Math.abs(losses.reduce((a, b) => a + b, 0));
  return {
    totalInvested,
    realizedPnL,
    winRate: closed.length ? (wins.length / closed.length) * 100 : 0,
    totalTrades: trades.length,
    closedTrades: closed.length,
    openTrades: open.length,
    avgProfit: wins.length ? sumWins / wins.length : 0,
    avgLoss: losses.length ? -sumLosses / losses.length : 0,
    profitFactor: sumLosses > 0 ? sumWins / sumLosses : wins.length > 0 ? Infinity : 0,
    bestTrade: pnls.length ? Math.max(...pnls) : 0,
    worstTrade: pnls.length ? Math.min(...pnls) : 0,
  };
}

// ── Formatting ────────────────────────────────────────────────────────────────

function rupees(v: number) {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${sign}₹${(abs / 1e3).toFixed(1)}K`;
  return `${sign}₹${abs.toFixed(0)}`;
}

function tradePnL(t: Trade): { pnl: number; pct: number } | null {
  if (t.status !== "Closed" || t.sellPrice == null) return null;
  const pnl = (t.sellPrice - t.buyPrice) * t.quantity;
  const pct = ((t.sellPrice - t.buyPrice) / t.buyPrice) * 100;
  return { pnl, pct };
}

// ── Markdown renderer ─────────────────────────────────────────────────────────

function renderResponse(text: string) {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let tableRows: string[][] = [];
  let key = 0;

  const flush = () => {
    if (!tableRows.length) return;
    const data = tableRows.filter(r => !r.every(c => /^[-:\s]+$/.test(c)));
    if (data.length < 1) { tableRows = []; return; }
    const header = data[0];
    const body = data.slice(1);
    nodes.push(
      <div key={key++} style={{ overflowX: "auto", margin: "10px 0" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
          <thead>
            <tr>
              {header.map((h, i) => (
                <th key={i} style={{
                  padding: "6px 10px", textAlign: "left",
                  background: "var(--surface-2)", borderBottom: "1px solid var(--border)",
                  color: "var(--text-2)", fontWeight: 700, whiteSpace: "nowrap",
                  fontFamily: "var(--font-body)", fontSize: 10, letterSpacing: "0.06em",
                }}>{inline(h)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri} style={{ background: ri % 2 === 0 ? "transparent" : "var(--surface-2)" }}>
                {row.map((cell, ci) => (
                  <td key={ci} style={{
                    padding: "5px 10px", borderBottom: "1px solid var(--border)",
                    color: "var(--text-1)", fontSize: 11, fontFamily: "var(--font-body)",
                  }}>{inline(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
    tableRows = [];
  };

  const inline = (s: string): React.ReactNode => {
    const parts = s.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((p, i) =>
      p.startsWith("**") && p.endsWith("**")
        ? <strong key={i} style={{ color: "var(--text-1)", fontWeight: 700 }}>{p.slice(2, -2)}</strong>
        : p
    );
  };

  for (const line of lines) {
    if ((line.trimStart().startsWith("|") && line.includes("|", 1))) {
      const cells = line.split("|").filter((_, i, a) => i > 0 && i < a.length - 1).map(c => c.trim());
      if (cells.length) tableRows.push(cells);
      continue;
    }
    flush();

    if (!line.trim()) { nodes.push(<div key={key++} style={{ height: 8 }} />); continue; }

    if (line.startsWith("## ")) {
      nodes.push(
        <div key={key++} style={{
          fontSize: 13, fontWeight: 800, color: "var(--text-1)",
          marginTop: 18, marginBottom: 6, paddingBottom: 6,
          borderBottom: "1px solid var(--border)",
          fontFamily: "var(--font-body)",
        }}>{inline(line.slice(3))}</div>
      );
      continue;
    }
    if (line.startsWith("### ")) {
      nodes.push(
        <div key={key++} style={{
          fontSize: 11, fontWeight: 700, color: "var(--accent)",
          marginTop: 12, marginBottom: 4, fontFamily: "var(--font-body)",
          letterSpacing: "0.04em",
        }}>{inline(line.slice(4))}</div>
      );
      continue;
    }
    if (line.startsWith("- ") || line.startsWith("• ")) {
      const content = line.slice(2);
      nodes.push(
        <div key={key++} style={{ display: "flex", gap: 7, marginBottom: 3, paddingLeft: 4 }}>
          <span style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2, fontSize: 8 }}>●</span>
          <span style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.6 }}>{inline(content)}</span>
        </div>
      );
      continue;
    }
    nodes.push(
      <div key={key++} style={{ fontSize: 12, color: "var(--text-2)", lineHeight: 1.65, marginBottom: 3 }}>
        {inline(line)}
      </div>
    );
  }
  flush();
  return nodes;
}

// ── Field styles ──────────────────────────────────────────────────────────────

const FIELD: React.CSSProperties = {
  width: "100%",
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "8px 12px",
  color: "var(--text-1)",
  fontSize: 12,
  fontFamily: "var(--font-body)",
  outline: "none",
  boxSizing: "border-box",
};

const LABEL: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--text-3)",
  marginBottom: 4,
  display: "block",
};

// ── Add Trade Modal ───────────────────────────────────────────────────────────

interface ModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (t: Trade) => void;
  editing?: Trade | null;
}

const EMOTIONS = ["", "Confident", "Fearful", "Greedy", "Neutral", "Anxious", "Excited", "Regretful", "Relieved", "Satisfied", "Hesitant"];
const MARKET_CONDITIONS = ["", "Bullish", "Bearish", "Sideways", "Volatile", "Trending", "Range-bound", "News-driven"];

function AddTradeModal({ open, onClose, onSave, editing }: ModalProps) {
  const [stockName, setStockName]       = useState("");
  const [tradeType, setTradeType]       = useState<"Swing" | "Investment">("Swing");
  const [buyPrice, setBuyPrice]         = useState("");
  const [quantity, setQuantity]         = useState("");
  const [entryDate, setEntryDate]       = useState(() => new Date().toISOString().slice(0, 10));
  const [capitalUsed, setCapitalUsed]   = useState("");
  const [status, setStatus]             = useState<"Open" | "Closed">("Open");
  const [sellPrice, setSellPrice]       = useState("");
  const [exitDate, setExitDate]         = useState("");
  const [showAdv, setShowAdv]           = useState(false);
  const [strategy, setStrategy]         = useState("");
  const [notes, setNotes]               = useState("");
  const [stopLoss, setStopLoss]         = useState("");
  const [target, setTarget]             = useState("");
  const [emotionIn, setEmotionIn]       = useState("");
  const [emotionOut, setEmotionOut]     = useState("");
  const [mktCondition, setMktCondition] = useState("");
  const [ruleFollowed, setRuleFollowed] = useState<"Yes" | "No" | "Partial" | "">("");
  const [error, setError]               = useState("");
  const [showStockSuggestions, setShowStockSuggestions] = useState(false);
  const firstRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setTimeout(() => firstRef.current?.focus(), 60);
    if (editing) {
      setStockName(editing.stockName); setTradeType(editing.tradeType);
      setBuyPrice(String(editing.buyPrice)); setQuantity(String(editing.quantity));
      setEntryDate(editing.entryDate); setCapitalUsed(String(editing.capitalUsed));
      setStatus(editing.status); setSellPrice(editing.sellPrice ? String(editing.sellPrice) : "");
      setExitDate(editing.exitDate ?? ""); setStrategy(editing.strategy ?? "");
      setNotes(editing.notes ?? ""); setStopLoss(editing.plannedStopLoss ? String(editing.plannedStopLoss) : "");
      setTarget(editing.plannedTarget ? String(editing.plannedTarget) : "");
      setEmotionIn(editing.emotionEntry ?? ""); setEmotionOut(editing.emotionExit ?? "");
      setMktCondition(editing.marketCondition ?? ""); setRuleFollowed(editing.ruleFollowed ?? "");
    } else {
      setStockName(""); setTradeType("Swing"); setBuyPrice(""); setQuantity("");
      setEntryDate(new Date().toISOString().slice(0, 10)); setCapitalUsed("");
      setStatus("Open"); setSellPrice(""); setExitDate(""); setStrategy("");
      setNotes(""); setStopLoss(""); setTarget(""); setEmotionIn("");
      setEmotionOut(""); setMktCondition(""); setRuleFollowed("");
    }
    setError(""); setShowAdv(false);
  }, [open, editing]);

  // Auto-calculate capital from price × qty
  useEffect(() => {
    const p = parseFloat(buyPrice); const q = parseInt(quantity, 10);
    if (p > 0 && q > 0 && !editing) setCapitalUsed(String(Math.round(p * q)));
  }, [buyPrice, quantity, editing]);

  const submit = () => {
    setError("");
    if (!stockName.trim()) return setError("Stock name is required");
    const bp = parseFloat(buyPrice); if (!bp || bp <= 0) return setError("Valid buy price required");
    const qty = parseInt(quantity, 10); if (!qty || qty <= 0) return setError("Valid quantity required");
    if (!entryDate) return setError("Entry date is required");
    const cap = parseFloat(capitalUsed); if (!cap || cap <= 0) return setError("Capital used is required");
    if (status === "Closed") {
      const sp = parseFloat(sellPrice);
      if (!sp || sp <= 0) return setError("Sell price required for closed trade");
      if (!exitDate) return setError("Exit date required for closed trade");
    }

    const trade: Trade = {
      id: editing?.id ?? `t_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      stockName: stockName.trim().toUpperCase(),
      tradeType, buyPrice: bp, quantity: qty, entryDate, capitalUsed: cap,
      status,
      sellPrice: status === "Closed" ? parseFloat(sellPrice) : undefined,
      exitDate: status === "Closed" ? exitDate : undefined,
      strategy: strategy || undefined, notes: notes || undefined,
      plannedStopLoss: stopLoss ? parseFloat(stopLoss) : undefined,
      plannedTarget: target ? parseFloat(target) : undefined,
      emotionEntry: emotionIn || undefined, emotionExit: emotionOut || undefined,
      marketCondition: mktCondition || undefined,
      ruleFollowed: ruleFollowed || undefined,
      createdAt: editing?.createdAt ?? new Date().toISOString(),
    };
    onSave(trade);
    onClose();
  };

  if (!open) return null;

  const pillBtnStyle = (active: boolean, color = "var(--accent)"): React.CSSProperties => ({
    flex: 1, padding: "7px 0", borderRadius: 8, border: `1.5px solid ${active ? color : "var(--border)"}`,
    background: active ? `color-mix(in srgb, ${color} 12%, transparent)` : "transparent",
    color: active ? color : "var(--text-3)", fontSize: 11, fontWeight: active ? 700 : 500,
    cursor: "pointer", transition: "all 150ms", fontFamily: "var(--font-body)",
  });

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.55)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 16,
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.18 }}
        style={{
          background: "var(--card-bg)", border: "1px solid var(--border)",
          borderRadius: 16, padding: 24, width: "100%", maxWidth: 520,
          maxHeight: "90vh", overflowY: "auto",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 800, color: "var(--text-1)", fontFamily: "var(--font-body)" }}>
            {editing ? "Edit Trade" : "Log New Trade"}
          </div>
          <button onClick={onClose} style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-3)" }}>
            <X size={16} />
          </button>
        </div>

        {/* Trade Type */}
        <div style={{ marginBottom: 16 }}>
          <label style={LABEL}>Trade Type</label>
          <div style={{ display: "flex", gap: 8 }}>
            {(["Swing", "Investment"] as const).map(t => (
              <button key={t} onClick={() => setTradeType(t)} style={pillBtnStyle(tradeType === t)}>{t}</button>
            ))}
          </div>
        </div>

        {/* Stock / Price / Qty row */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
          <div>
            <label style={LABEL}>Stock Name *</label>
            <div style={{ position: "relative" }}>
              <input
                ref={firstRef}
                type="text"
                placeholder="Search stock (e.g. RELIANCE, INFY)..."
                value={stockName}
                onChange={e => { setStockName(e.target.value.toUpperCase()); setShowStockSuggestions(true); }}
                onFocus={() => setShowStockSuggestions(true)}
                onBlur={() => setTimeout(() => setShowStockSuggestions(false), 200)}
                style={FIELD}
              />
              {showStockSuggestions && stockName.length >= 1 && (() => {
                const q = stockName.toUpperCase();
                const matches = NSE_STOCKS.filter(s =>
                  s.symbol.includes(q) || s.name.toUpperCase().includes(q)
                ).slice(0, 10);
                if (!matches.length) return null;
                return (
                  <div style={{
                    position: "absolute", top: "100%", left: 0, right: 0, zIndex: 100,
                    background: "var(--surface)", border: "1px solid var(--border)",
                    borderRadius: 8, boxShadow: "var(--shadow-lg)", maxHeight: 220, overflowY: "auto",
                    marginTop: 2,
                  }}>
                    {matches.map(s => (
                      <div
                        key={s.symbol}
                        onMouseDown={() => { setStockName(s.symbol); setShowStockSuggestions(false); }}
                        style={{
                          padding: "8px 12px", cursor: "pointer", display: "flex", gap: 8, alignItems: "center",
                          borderBottom: "1px solid var(--border-2)",
                          transition: "background 100ms",
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                      >
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--accent)", minWidth: 80 }}>{s.symbol}</span>
                        <span style={{ fontSize: 11, color: "var(--text-3)", fontFamily: "var(--font-body)" }}>{s.name}</span>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          </div>
          <div>
            <label style={LABEL}>Buy Price *</label>
            <input type="number" value={buyPrice} onChange={e => setBuyPrice(e.target.value)}
              placeholder="₹" style={FIELD} />
          </div>
          <div>
            <label style={LABEL}>Quantity *</label>
            <input type="number" value={quantity} onChange={e => setQuantity(e.target.value)}
              placeholder="Qty" style={FIELD} />
          </div>
        </div>

        {/* Entry Date / Capital */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
          <div>
            <label style={LABEL}>Entry Date *</label>
            <input type="date" value={entryDate} onChange={e => setEntryDate(e.target.value)} style={FIELD} />
          </div>
          <div>
            <label style={LABEL}>Capital Used (₹) *</label>
            <input type="number" value={capitalUsed} onChange={e => setCapitalUsed(e.target.value)}
              placeholder="Auto from price×qty" style={FIELD} />
          </div>
        </div>

        {/* Status */}
        <div style={{ marginBottom: 16 }}>
          <label style={LABEL}>Trade Status</label>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => setStatus("Open")} style={pillBtnStyle(status === "Open", "var(--green)")}>⚪ Open</button>
            <button onClick={() => setStatus("Closed")} style={pillBtnStyle(status === "Closed", "var(--accent)")}>✓ Closed</button>
          </div>
        </div>

        {/* Closed fields */}
        <AnimatePresence>
          {status === "Closed" && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
                <div>
                  <label style={LABEL}>Sell Price *</label>
                  <input type="number" value={sellPrice} onChange={e => setSellPrice(e.target.value)}
                    placeholder="₹" style={FIELD} />
                </div>
                <div>
                  <label style={LABEL}>Exit Date *</label>
                  <input type="date" value={exitDate} onChange={e => setExitDate(e.target.value)} style={FIELD} />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Advanced toggle */}
        <button onClick={() => setShowAdv(v => !v)} style={{
          display: "flex", alignItems: "center", gap: 6, width: "100%",
          background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8,
          padding: "8px 12px", cursor: "pointer", color: "var(--text-3)", fontSize: 11,
          fontFamily: "var(--font-body)", fontWeight: 600, marginBottom: 14,
        }}>
          {showAdv ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          Context & Psychology (optional)
        </button>

        <AnimatePresence>
          {showAdv && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
                <div>
                  <label style={LABEL}>Planned Stop-Loss</label>
                  <input type="number" value={stopLoss} onChange={e => setStopLoss(e.target.value)} placeholder="₹" style={FIELD} />
                </div>
                <div>
                  <label style={LABEL}>Planned Target</label>
                  <input type="number" value={target} onChange={e => setTarget(e.target.value)} placeholder="₹" style={FIELD} />
                </div>
              </div>
              <div style={{ marginBottom: 10 }}>
                <label style={LABEL}>Strategy / Setup</label>
                <input value={strategy} onChange={e => setStrategy(e.target.value)}
                  placeholder="Breakout, Support bounce, Earnings play…" style={FIELD} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
                <div>
                  <label style={LABEL}>Emotion at Entry</label>
                  <select value={emotionIn} onChange={e => setEmotionIn(e.target.value)} style={FIELD}>
                    {EMOTIONS.map(e => <option key={e} value={e}>{e || "Select…"}</option>)}
                  </select>
                </div>
                <div>
                  <label style={LABEL}>Emotion at Exit</label>
                  <select value={emotionOut} onChange={e => setEmotionOut(e.target.value)} style={FIELD}>
                    {EMOTIONS.map(e => <option key={e} value={e}>{e || "Select…"}</option>)}
                  </select>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
                <div>
                  <label style={LABEL}>Market Condition</label>
                  <select value={mktCondition} onChange={e => setMktCondition(e.target.value)} style={FIELD}>
                    {MARKET_CONDITIONS.map(m => <option key={m} value={m}>{m || "Select…"}</option>)}
                  </select>
                </div>
                <div>
                  <label style={LABEL}>Rule Followed?</label>
                  <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    {(["Yes", "No", "Partial"] as const).map(r => (
                      <button key={r} onClick={() => setRuleFollowed(ruleFollowed === r ? "" : r)}
                        style={pillBtnStyle(ruleFollowed === r, r === "Yes" ? "var(--green)" : r === "No" ? "var(--red)" : "var(--amber)")}>
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={LABEL}>Notes</label>
                <textarea value={notes} onChange={e => setNotes(e.target.value)}
                  placeholder="Trade reasoning, lessons, what you observed…"
                  style={{ ...FIELD, minHeight: 72, resize: "vertical" as const }} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {error && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--red)", fontSize: 12, marginBottom: 12 }}>
            <AlertCircle size={13} /> {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onClose} style={{
            flex: 1, padding: "10px 0", borderRadius: 9999, border: "1px solid var(--border)",
            background: "transparent", color: "var(--text-2)", fontSize: 12, fontWeight: 600,
            cursor: "pointer", fontFamily: "var(--font-body)",
          }}>Cancel</button>
          <button onClick={submit} style={{
            flex: 2, padding: "10px 0", borderRadius: 9999, border: "none",
            background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 700,
            cursor: "pointer", fontFamily: "var(--font-body)",
            boxShadow: "0 4px 14px rgba(106,98,86,0.35)",
          }}>
            {editing ? "Save Changes" : "Log Trade"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ── Delete confirmation ───────────────────────────────────────────────────────

function DeleteConfirm({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div style={{
      position: "absolute", right: 0, top: "100%", zIndex: 10, marginTop: 4,
      background: "var(--card-bg)", border: "1px solid var(--border)",
      borderRadius: 10, padding: "12px 14px", width: 200,
      boxShadow: "0 8px 24px rgba(0,0,0,0.2)",
    }}>
      <div style={{ fontSize: 11, color: "var(--text-2)", marginBottom: 10 }}>Remove this trade?</div>
      <div style={{ display: "flex", gap: 6 }}>
        <button onClick={onCancel} style={{
          flex: 1, padding: "5px 0", borderRadius: 6, border: "1px solid var(--border)",
          background: "transparent", color: "var(--text-3)", fontSize: 11, cursor: "pointer",
        }}>Cancel</button>
        <button onClick={onConfirm} style={{
          flex: 1, padding: "5px 0", borderRadius: 6, border: "none",
          background: "var(--red)", color: "#fff", fontSize: 11, fontWeight: 700, cursor: "pointer",
        }}>Delete</button>
      </div>
    </div>
  );
}

// ── Quick prompts ─────────────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  { icon: "📊", label: "Full Analysis", msg: "Please provide a complete analysis of my trading journal with all sections: Portfolio Summary, Trade Log, Equity Curve Insight, Open Positions, Performance Analysis, Psychology Analysis, Pattern Recognition, Critical Mistakes, Action Plan, Risk Management, Coach's Verdict, and System Quality Check." },
  { icon: "🧠", label: "Psychology Check", msg: "Analyze only my trading psychology and behavioral patterns. What emotional mistakes am I making? Be brutally honest." },
  { icon: "⚠️", label: "Critical Mistakes", msg: "What are my most critical mistakes ranked by severity? What must I stop doing immediately?" },
  { icon: "🚀", label: "Action Plan", msg: "Give me a practical action plan: what to improve, scale, avoid, and track. Include a pre-trade checklist." },
  { icon: "🔬", label: "Edge Check", msg: "Do I have a real edge? Evaluate my system quality honestly based on actual results, expectancy, and repeatability. Do not be optimistic without evidence." },
];

// ── Equity Curve helpers ──────────────────────────────────────────────────────

function getNiceTicks(lo: number, hi: number, n: number): number[] {
  const span = hi - lo || 1;
  const rough = span / (n - 1);
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const nice = ([1, 2, 2.5, 5, 10].find(x => x * mag >= rough) ?? 10) * mag;
  const start = Math.ceil(lo / nice) * nice;
  const ticks: number[] = [];
  for (let v = start; v <= hi + nice * 0.01; v += nice)
    ticks.push(Math.round(v * 1e8) / 1e8);
  return ticks;
}

function fmtTick(v: number): string {
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e7) return `${s}${(a / 1e7).toFixed(1)}Cr`;
  if (a >= 1e5) return `${s}${(a / 1e5).toFixed(1)}L`;
  if (a >= 1e3) return `${s}${(a / 1e3).toFixed(0)}K`;
  return `${s}${a.toFixed(0)}`;
}

function MiniKpi({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div style={{ fontSize: 9, color: "var(--text-4)", fontWeight: 700, letterSpacing: "0.08em" }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 800, color: color ?? "var(--text-1)", fontFamily: "var(--font-mono)" }}>{value}</div>
    </div>
  );
}

function EquityCurve({ trades }: { trades: Trade[] }) {
  const [tip, setTip] = useState<{
    cx: number; cy: number; pnl: number; cum: number; symbol: string; date: string; pct: number;
  } | null>(null);

  const pts = useMemo(() => {
    const closed = [...trades]
      .filter(t => t.status === "Closed" && t.sellPrice != null && t.exitDate)
      .sort((a, b) => new Date(a.exitDate!).getTime() - new Date(b.exitDate!).getTime());
    let cum = 0;
    return closed.map(t => {
      const pnl = (t.sellPrice! - t.buyPrice) * t.quantity;
      const pct = ((t.sellPrice! - t.buyPrice) / t.buyPrice) * 100;
      cum += pnl;
      return { date: t.exitDate!, cum, pnl, symbol: t.stockName, pct };
    });
  }, [trades]);

  const monthly = useMemo(() => {
    const map = new Map<string, number>();
    for (const t of trades) {
      if (t.status !== "Closed" || !t.exitDate || t.sellPrice == null) continue;
      const d = new Date(t.exitDate);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      map.set(key, (map.get(key) ?? 0) + (t.sellPrice - t.buyPrice) * t.quantity);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([key, pnl]) => {
      const [y, m] = key.split("-").map(Number);
      const label = new Date(y, m - 1, 1).toLocaleString("en-IN", { month: "short", year: "2-digit" });
      return { key, label, pnl };
    });
  }, [trades]);

  if (pts.length === 0)
    return <div style={{ padding: 48, textAlign: "center", color: "var(--text-4)", fontSize: 13 }}>No closed trades to plot.</div>;

  // SVG layout constants
  const W = 900, H = 240, PL = 72, PR = 24, PT = 18, PB = 46;
  const iW = W - PL - PR, iH = H - PT - PB;

  const allCums = [0, ...pts.map(p => p.cum)];
  const minC = Math.min(...allCums), maxC = Math.max(...allCums);
  const pad = (maxC - minC || 100) * 0.08;
  const yLo = minC - pad, yHi = maxC + pad, ySpan = yHi - yLo;

  const xOf = (i: number) => PL + (i / pts.length) * iW;
  const yOf = (v: number) => PT + iH - ((v - yLo) / ySpan) * iH;
  const y0 = yOf(0);

  const svgPts = [{ x: PL, y: y0 }, ...pts.map((_, i) => ({ x: xOf(i + 1), y: yOf(pts[i].cum) }))];
  const lineD = svgPts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const fillD = `${lineD} L${svgPts[svgPts.length - 1].x.toFixed(1)},${y0.toFixed(1)} L${PL},${y0.toFixed(1)} Z`;

  const yTicks = getNiceTicks(yLo, yHi, 6);

  // X-axis month labels
  const xLabels: { x: number; text: string }[] = [];
  let lastMo = "";
  pts.forEach((p, i) => {
    const mo = p.date.slice(0, 7);
    if (mo !== lastMo) {
      const d = new Date(p.date);
      xLabels.push({ x: xOf(i + 1), text: d.toLocaleString("en-IN", { day: "numeric", month: "short" }) });
      lastMo = mo;
    }
  });

  // Max drawdown
  let peak = 0, mdd = 0;
  let ddStartI = 0, ddEndI = 0, curPeakI = 0;
  pts.forEach((p, i) => {
    if (p.cum > peak) { peak = p.cum; curPeakI = i + 1; }
    if (peak > 0) {
      const dd = (peak - p.cum) / peak;
      if (dd > mdd) { mdd = dd; ddStartI = curPeakI; ddEndI = i + 1; }
    }
  });

  // Stats
  const pnls = pts.map(p => p.pnl);
  const wins = pnls.filter(v => v > 0), losses = pnls.filter(v => v < 0);
  const sumW = wins.reduce((a, b) => a + b, 0);
  const sumL = Math.abs(losses.reduce((a, b) => a + b, 0));
  const avgWin = wins.length ? sumW / wins.length : 0;
  const avgLoss = losses.length ? sumL / losses.length : 0;
  const pf = sumL > 0 ? sumW / sumL : wins.length > 0 ? 99 : 0;
  const expectancy = pts.length ? (sumW - sumL) / pts.length : 0;
  const totalPnL = pts[pts.length - 1].cum;

  // Monthly bar chart constants
  const mW = 900, mH = 130, mPL = 72, mPR = 24, mPT = 12, mPB = 36;
  const miW = mW - mPL - mPR, miH = mH - mPT - mPB;
  const maxAbsM = Math.max(...monthly.map(m => Math.abs(m.pnl)), 1);
  const mBarW = Math.max(20, Math.min(60, Math.floor(miW / monthly.length) - 8));
  const mY0 = mPT + miH;

  return (
    <div style={{ overflowY: "auto", padding: "4px 0 24px" }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-1)" }}>Equity Curve</span>
          <span style={{ fontSize: 10, color: "var(--text-4)", marginLeft: 8 }}>FY 2026-27 · {pts.length} closed trades</span>
        </div>
        <div style={{ display: "flex", gap: 20 }}>
          <MiniKpi label="NET P&L"   value={fmtTick(totalPnL)}   color={totalPnL >= 0 ? "#10b981" : "#ef4444"} />
          <MiniKpi label="MAX DD"    value={`${(mdd * 100).toFixed(1)}%`} color={mdd > 0.15 ? "#ef4444" : mdd > 0.08 ? "#f59e0b" : "var(--text-2)"} />
          <MiniKpi label="WIN RATE"  value={`${wins.length}/${pts.length}`} color="var(--text-2)" />
        </div>
      </div>

      {/* Equity curve SVG */}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        <defs>
          <linearGradient id="ecUp" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.30" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="ecDn" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ef4444" stopOpacity="0.02" />
            <stop offset="100%" stopColor="#ef4444" stopOpacity="0.25" />
          </linearGradient>
          <clipPath id="ecClipAbove">
            <rect x={PL} y={PT} width={iW} height={Math.max(0, y0 - PT)} />
          </clipPath>
          <clipPath id="ecClipBelow">
            <rect x={PL} y={Math.max(PT, y0)} width={iW} height={Math.max(0, PT + iH - y0)} />
          </clipPath>
        </defs>

        {/* Grid lines + Y labels */}
        {yTicks.map(tick => (
          <g key={tick}>
            <line x1={PL} y1={yOf(tick)} x2={W - PR} y2={yOf(tick)} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
            <text x={PL - 8} y={yOf(tick)} textAnchor="end" dominantBaseline="middle"
              fill="rgba(255,255,255,0.28)" fontSize="10" fontFamily="monospace">
              {fmtTick(tick)}
            </text>
          </g>
        ))}

        {/* Zero baseline */}
        <line x1={PL} y1={y0} x2={W - PR} y2={y0} stroke="rgba(255,255,255,0.22)" strokeWidth="1" strokeDasharray="4 3" />

        {/* Max drawdown band */}
        {mdd > 0.005 && (
          <rect x={xOf(ddStartI)} y={PT} width={xOf(ddEndI) - xOf(ddStartI)} height={iH}
            fill="rgba(239,68,68,0.05)" />
        )}

        {/* Area fills */}
        <path d={fillD} fill="url(#ecUp)" clipPath="url(#ecClipAbove)" />
        <path d={fillD} fill="url(#ecDn)" clipPath="url(#ecClipBelow)" />

        {/* Main line */}
        <path d={lineD} fill="none" stroke="#10b981" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />

        {/* Trade dots */}
        {pts.map((p, i) => {
          const cx = xOf(i + 1), cy = yOf(p.cum);
          const isHov = tip?.symbol === p.symbol && tip?.date === p.date && Math.abs(tip.cx - cx) < 1;
          return (
            <circle key={i} cx={cx} cy={cy} r={isHov ? 5.5 : 3.5}
              fill={p.pnl >= 0 ? "#10b981" : "#ef4444"}
              stroke={p.pnl >= 0 ? "#022c22" : "#450a0a"} strokeWidth="1"
              style={{ cursor: "pointer" }}
              onMouseEnter={() => setTip({ cx, cy, pnl: p.pnl, cum: p.cum, symbol: p.symbol, date: p.date, pct: p.pct })}
              onMouseLeave={() => setTip(null)}
            />
          );
        })}

        {/* X-axis labels */}
        {xLabels.map((xl, i) => (
          <text key={i} x={xl.x} y={H - PB + 15} textAnchor="middle"
            fill="rgba(255,255,255,0.30)" fontSize="9.5" fontFamily="system-ui">{xl.text}</text>
        ))}

        {/* Tooltip */}
        {tip && (() => {
          const tx = Math.min(tip.cx + 12, W - 138);
          const ty = Math.max(PT + 2, tip.cy - 68);
          return (
            <g>
              <line x1={tip.cx} y1={PT} x2={tip.cx} y2={PT + iH} stroke="rgba(255,255,255,0.12)" strokeWidth="1" strokeDasharray="3 2" />
              <rect x={tx} y={ty} width={130} height={66} rx="6"
                fill="#0f172a" stroke="rgba(148,163,184,0.18)" strokeWidth="1" />
              <text x={tx + 9} y={ty + 16} fill="#e2e8f0" fontSize="11" fontWeight="700">{tip.symbol}</text>
              <text x={tx + 9} y={ty + 28} fill="#94a3b8" fontSize="9">{tip.date}</text>
              <text x={tx + 9} y={ty + 42}
                fill={tip.pnl >= 0 ? "#10b981" : "#ef4444"} fontSize="11" fontWeight="700">
                {tip.pnl >= 0 ? "+" : ""}₹{Math.abs(tip.pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })} ({tip.pct >= 0 ? "+" : ""}{tip.pct.toFixed(1)}%)
              </text>
              <text x={tx + 9} y={ty + 56} fill="#64748b" fontSize="9">
                Cum: {tip.cum >= 0 ? "+" : ""}₹{Math.abs(tip.cum).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </text>
            </g>
          );
        })()}
      </svg>

      {/* Stats strip */}
      <div style={{ display: "flex", gap: 8, margin: "12px 0 18px", flexWrap: "wrap" }}>
        {[
          { label: "Best Trade",    value: fmtTick(Math.max(...pnls)),  color: "#10b981" },
          { label: "Worst Trade",   value: fmtTick(Math.min(...pnls)),  color: "#ef4444" },
          { label: "Avg Win",       value: fmtTick(avgWin),            color: "#10b981" },
          { label: "Avg Loss",      value: fmtTick(-avgLoss),          color: "#ef4444" },
          { label: "Profit Factor", value: pf >= 99 ? "∞" : pf.toFixed(2), color: pf >= 2 ? "#10b981" : pf >= 1 ? "#f59e0b" : "#ef4444" },
          { label: "Expectancy",   value: fmtTick(expectancy),         color: expectancy >= 0 ? "#10b981" : "#ef4444" },
        ].map(s => (
          <div key={s.label} style={{
            flex: "1 1 120px", background: "var(--surface-2)",
            border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px",
          }}>
            <div style={{ fontSize: 9, color: "var(--text-4)", fontWeight: 700, letterSpacing: "0.08em", marginBottom: 3 }}>
              {s.label.toUpperCase()}
            </div>
            <div style={{ fontSize: 15, fontWeight: 800, color: s.color, fontFamily: "var(--font-mono)" }}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      {/* Monthly P&L bar chart */}
      {monthly.length > 0 && (
        <>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-2)", marginBottom: 6 }}>Monthly P&L</div>
          <svg viewBox={`0 0 ${mW} ${mH}`} style={{ width: "100%", height: "auto", display: "block" }}>
            {/* Baseline */}
            <line x1={mPL} y1={mY0} x2={mW - mPR} y2={mY0} stroke="rgba(255,255,255,0.15)" strokeWidth="1" />

            {monthly.map((m, i) => {
              const bx = mPL + (i / monthly.length) * miW + (miW / monthly.length - mBarW) / 2;
              const bh = Math.max(2, (Math.abs(m.pnl) / maxAbsM) * (miH - 14));
              const by = m.pnl >= 0 ? mY0 - bh : mY0;
              const barColor = m.pnl >= 0 ? "rgba(16,185,129,0.7)" : "rgba(239,68,68,0.7)";
              const labelY = m.pnl >= 0 ? by - 5 : by + bh + 13;
              return (
                <g key={m.key}>
                  <rect x={bx} y={by} width={mBarW} height={bh} fill={barColor} rx="3" />
                  <text x={bx + mBarW / 2} y={labelY} textAnchor="middle"
                    fill={m.pnl >= 0 ? "#10b981" : "#ef4444"} fontSize="9.5" fontWeight="700">
                    {fmtTick(m.pnl)}
                  </text>
                  <text x={bx + mBarW / 2} y={mY0 + 16} textAnchor="middle"
                    fill="rgba(255,255,255,0.35)" fontSize="10">{m.label}</text>
                </g>
              );
            })}
          </svg>
        </>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function TradingJournalPage() {
  const [trades, setTrades]             = useState<Trade[]>(loadTrades);
  const [activeTab, setActiveTab]       = useState<"log" | "equity" | "coach">("log");
  const [modalOpen, setModalOpen]       = useState(false);
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);
  const [deleteId, setDeleteId]         = useState<string | null>(null);
  const [messages, setMessages]         = useState<Message[]>([]);
  const [input, setInput]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [sortDesc, setSortDesc]         = useState(true);
  const [syncStatus, setSyncStatus]     = useState<"idle" | "syncing" | "synced" | "error">("idle");
  const [livePrices, setLivePrices]     = useState<Record<string, number | null>>({});
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  const metrics = calcMetrics(trades);
  const unrealizedPnL = trades
    .filter(t => t.status === "Open")
    .reduce((sum, t) => {
      const cmp = livePrices[t.stockName.trim().toUpperCase()];
      return cmp != null ? sum + (cmp - t.buyPrice) * t.quantity : sum;
    }, 0);

  // ── On mount: pull from backend DB, merge with localStorage ──
  useEffect(() => {
    setSyncStatus("syncing");
    api.get<Trade[]>("/journal/trades")
      .then(serverTrades => {
        if (!serverTrades?.length) { setSyncStatus("synced"); return; }
        // Merge: build map from localStorage, overwrite/add from server
        const localMap = new Map(loadTrades().map(t => [t.id, t]));
        for (const t of serverTrades) localMap.set(t.id, t);
        const merged = Array.from(localMap.values())
          .sort((a, b) => new Date(b.entryDate).getTime() - new Date(a.entryDate).getTime());
        setTrades(merged);
        saveTrades(merged);
        setSyncStatus("synced");
      })
      .catch(() => setSyncStatus("error"));
  }, []);

  // ── Fetch live prices for open trades ──
  const fetchLivePrices = useCallback((tradeList: Trade[]) => {
    const openSymbols = [...new Set(
      tradeList.filter(t => t.status === "Open").map(t => t.stockName.trim().toUpperCase())
    )];
    if (!openSymbols.length) return;
    api.get<Record<string, number | null>>(`/journal/prices?symbols=${openSymbols.join(",")}`)
      .then(prices => setLivePrices(prev => ({ ...prev, ...prices })))
      .catch(() => {/* price fetch failure is non-fatal */});
  }, []);

  useEffect(() => { fetchLivePrices(trades); }, [trades, fetchLivePrices]);

  const persistAndSet = useCallback((updated: Trade[]) => {
    setTrades(updated);
    saveTrades(updated);
  }, []);

  const onSave = useCallback((t: Trade) => {
    // 1. Optimistic local update
    const updated = editingTrade
      ? trades.map(x => x.id === t.id ? t : x)
      : [t, ...trades];
    persistAndSet(updated);
    setEditingTrade(null);
    // 2. Background sync to DB
    setSyncStatus("syncing");
    api.post<Trade>("/journal/trades", t)
      .then(() => setSyncStatus("synced"))
      .catch(() => setSyncStatus("error"));
  }, [trades, editingTrade, persistAndSet]);

  const onDelete = useCallback((id: string) => {
    // 1. Optimistic local update
    persistAndSet(trades.filter(t => t.id !== id));
    setDeleteId(null);
    // 2. Background sync to DB
    setSyncStatus("syncing");
    api.delete<{ ok: boolean }>(`/journal/trades/${encodeURIComponent(id)}`)
      .then(() => setSyncStatus("synced"))
      .catch(() => setSyncStatus("error"));
  }, [trades, persistAndSet]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  useEffect(() => {
    if (activeTab === "coach" && messages.length === 0) {
      setMessages([{
        role: "assistant",
        content: "**Welcome to your Trading Coach** 📒\n\nI'm your personal AI performance coach. Log your trades in the Journal tab, then come here for analysis.\n\n**What I can do:**\n- Full portfolio analysis with all metrics\n- Psychology and behavioral pattern detection\n- Critical mistake identification (blunt, ranked)\n- Actionable improvement plans\n- System quality and edge assessment\n\nUse the quick buttons above or ask me anything about your trades.",
      }]);
    }
  }, [activeTab, messages.length]);

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput("");
    const userMsg: Message = { role: "user", content: msg };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);
    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      const res = await api.post<{ response: string; trade_count: number }>("/journal/chat", {
        message: msg,
        history: history.slice(-6),
        trades: trades.slice(0, 150),  // pass localStorage trades so AI works even on fresh server
      });
      setMessages(prev => [...prev, { role: "assistant", content: res.response }]);
    } catch (err) {
      const isTimeout = String(err).includes("timeout") || String(err).includes("504");
      setMessages(prev => [...prev, {
        role: "assistant",
        content: isTimeout
          ? "The analysis timed out. Try asking for one section at a time (e.g. 'Show my Psychology Analysis' or 'What are my critical mistakes?')."
          : "Could not reach the AI. Please check your connection and try again.",
      }]);
    }
    setLoading(false);
  };

  const displayedTrades = [...trades].sort((a, b) =>
    sortDesc
      ? new Date(b.entryDate).getTime() - new Date(a.entryDate).getTime()
      : new Date(a.entryDate).getTime() - new Date(b.entryDate).getTime()
  );

  const pnlColor = (v: number) => v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-3)";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <Header title="Trading Journal" subtitle="Personal performance coach & trade log" />

      {/* ── Stat Cards ── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(6, 1fr)",
        gap: 14, padding: "20px 24px 0",
      }}>
        <StatCard
          label="Total Invested"
          value={<span style={{ fontSize: 22 }}>{rupees(metrics.totalInvested).replace("+", "").replace("-₹", "₹")}</span>}
          subValue="Current open positions"
          icon={<DollarSign size={14} />}
          delay={0}
        />
        <StatCard
          label="Realized P&L"
          value={<span style={{ fontSize: 22, color: pnlColor(metrics.realizedPnL) }}>
            {rupees(metrics.realizedPnL)}
          </span>}
          subValue={`${metrics.closedTrades} closed trades`}
          icon={metrics.realizedPnL >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          variant={metrics.realizedPnL > 0 ? "success" : metrics.realizedPnL < 0 ? "danger" : "default"}
          delay={0.05}
        />
        <StatCard
          label="Unrealized P&L"
          value={<span style={{ fontSize: 22, color: pnlColor(unrealizedPnL) }}>
            {Object.keys(livePrices).length > 0 ? rupees(unrealizedPnL) : "—"}
          </span>}
          subValue={`${metrics.openTrades} open positions`}
          icon={unrealizedPnL >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          variant={unrealizedPnL > 0 ? "success" : unrealizedPnL < 0 ? "danger" : "default"}
          delay={0.075}
        />
        <StatCard
          label="Win Rate"
          value={<span style={{ fontSize: 22 }}>{metrics.winRate.toFixed(1)}%</span>}
          subValue={`${Math.round((metrics.winRate / 100) * metrics.closedTrades)} wins of ${metrics.closedTrades}`}
          icon={<Award size={14} />}
          variant={metrics.winRate >= 60 ? "success" : metrics.winRate >= 40 ? "warning" : metrics.closedTrades > 0 ? "danger" : "default"}
          delay={0.1}
        />
        <StatCard
          label="Open Positions"
          value={<span style={{ fontSize: 22 }}>{metrics.openTrades}</span>}
          subValue="Active trades"
          icon={<Target size={14} />}
          delay={0.15}
        />
        <StatCard
          label="Total Trades"
          value={<span style={{ fontSize: 22 }}>{metrics.totalTrades}</span>}
          subValue={`Profit Factor: ${isFinite(metrics.profitFactor) ? metrics.profitFactor.toFixed(2) : metrics.closedTrades > 0 ? "∞" : "—"}`}
          icon={<BarChart2 size={14} />}
          delay={0.2}
        />
      </div>

      {/* ── Tab bar ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "16px 24px 0",
      }}>
        <div style={{ display: "flex", gap: 6 }}>
          {(["log", "equity", "coach"] as const).map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              padding: "7px 18px", borderRadius: 9999, border: "none", cursor: "pointer",
              background: activeTab === tab ? "var(--accent)" : "var(--surface-2)",
              color: activeTab === tab ? "#fff" : "var(--text-3)",
              fontSize: 12, fontWeight: activeTab === tab ? 700 : 500,
              fontFamily: "var(--font-body)", transition: "all 150ms",
            }}>
              {tab === "log" ? "📒 Trade Log" : tab === "equity" ? "📈 Equity Curve" : "🧠 AI Coach"}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Sync status indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{
              width: 6, height: 6, borderRadius: "50%",
              background: syncStatus === "synced" ? "var(--green)"
                : syncStatus === "syncing" ? "var(--amber)"
                : syncStatus === "error" ? "var(--red)"
                : "var(--text-4)",
              boxShadow: syncStatus === "synced" ? "0 0 5px var(--green)"
                : syncStatus === "syncing" ? "0 0 5px var(--amber)"
                : syncStatus === "error" ? "0 0 5px var(--red)" : "none",
              animation: syncStatus === "syncing" ? "pulse-dot 1s ease-in-out infinite" : "none",
            }} />
            <span style={{ fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-mono)", letterSpacing: "0.06em" }}>
              {syncStatus === "syncing" ? "SYNCING" : syncStatus === "synced" ? "SYNCED" : syncStatus === "error" ? "LOCAL" : ""}
            </span>
          </div>

          {activeTab === "log" && (
            <button onClick={() => { setEditingTrade(null); setModalOpen(true); }} style={{
              display: "flex", alignItems: "center", gap: 7, padding: "8px 18px",
              borderRadius: 9999, border: "none", background: "var(--accent)", color: "#fff",
              fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "var(--font-body)",
              boxShadow: "0 4px 14px rgba(106,98,86,0.3)",
            }}>
              <Plus size={13} /> Add Trade
            </button>
          )}
          {activeTab === "coach" && (
            <button onClick={() => { setMessages([]); }} style={{
              display: "flex", alignItems: "center", gap: 6, padding: "7px 14px",
              borderRadius: 9999, border: "1px solid var(--border)", background: "transparent",
              color: "var(--text-3)", fontSize: 11, cursor: "pointer", fontFamily: "var(--font-body)",
            }}>
              <RefreshCw size={11} /> Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Tab content ── */}
      <div style={{ flex: 1, minHeight: 0, padding: "14px 24px 24px", overflow: "hidden", display: "flex", flexDirection: "column" }}>

        {/* TRADE LOG */}
        {activeTab === "log" && (
          <motion.div key="log" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
            {trades.length === 0 ? (
              <div style={{
                display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                height: 280, gap: 12,
              }}>
                <BookOpen size={40} style={{ color: "var(--text-4)" }} />
                <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-2)" }}>No trades logged yet</div>
                <div style={{ fontSize: 12, color: "var(--text-4)", textAlign: "center", maxWidth: 300 }}>
                  Add your first trade to start tracking your performance.
                </div>
                <button onClick={() => setModalOpen(true)} style={{
                  marginTop: 8, padding: "10px 24px", borderRadius: 9999, border: "none",
                  background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 700,
                  cursor: "pointer", fontFamily: "var(--font-body)",
                }}>
                  <Plus size={13} style={{ marginRight: 6, verticalAlign: "middle" }} />
                  Log Your First Trade
                </button>
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    {["Date ↕", "Stock", "Type", "Status", "Buy ₹", "CMP ₹", "Sell ₹", "Qty", "Capital", "P&L", "P&L%", "Strategy", "Rule", ""].map((h, i) => (
                      <th key={i} onClick={h === "Date ↕" ? () => setSortDesc(v => !v) : undefined}
                        style={{
                          padding: "9px 12px", textAlign: "left",
                          fontSize: 9, fontWeight: 700, letterSpacing: "0.1em",
                          color: "var(--text-3)", borderBottom: "1px solid var(--border)",
                          cursor: h === "Date ↕" ? "pointer" : "default",
                          whiteSpace: "nowrap", userSelect: "none",
                          fontFamily: "var(--font-body)",
                        }}>
                        {h.toUpperCase()}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayedTrades.map((t, idx) => {
                    const cmp = t.status === "Open"
                      ? (livePrices[t.stockName.trim().toUpperCase()] ?? null)
                      : null;
                    const unrealized = cmp != null
                      ? { pnl: (cmp - t.buyPrice) * t.quantity, pct: ((cmp - t.buyPrice) / t.buyPrice) * 100 }
                      : null;
                    const result = t.status === "Closed" ? tradePnL(t) : unrealized;
                    const emoji = t.status === "Open"
                      ? (unrealized ? (unrealized.pnl >= 0 ? "🟢" : "🔴") : "⚪")
                      : (tradePnL(t) ? (tradePnL(t)!.pnl > 0 ? "🟢" : "🔴") : "⚪");
                    return (
                      <tr key={t.id} style={{
                        background: idx % 2 === 0 ? "transparent" : "var(--surface-2)",
                        transition: "background 120ms",
                      }}
                        onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = "var(--accent-dim)"}
                        onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = idx % 2 === 0 ? "transparent" : "var(--surface-2)"}
                      >
                        <td style={{ padding: "8px 12px", color: "var(--text-3)", whiteSpace: "nowrap", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                          {t.entryDate}
                        </td>
                        <td style={{ padding: "8px 12px", fontWeight: 700, color: "var(--text-1)", whiteSpace: "nowrap" }}>
                          {emoji} {t.stockName}
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          <span style={{
                            padding: "3px 8px", borderRadius: 9999, fontSize: 9, fontWeight: 700,
                            background: t.tradeType === "Swing" ? "rgba(106,98,86,0.1)" : "rgba(39,174,96,0.1)",
                            color: t.tradeType === "Swing" ? "var(--accent)" : "var(--green)",
                          }}>{t.tradeType}</span>
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          <span style={{
                            padding: "3px 8px", borderRadius: 9999, fontSize: 9, fontWeight: 700,
                            background: t.status === "Open" ? "rgba(255,176,23,0.1)" : "rgba(100,100,100,0.1)",
                            color: t.status === "Open" ? "var(--amber)" : "var(--text-3)",
                          }}>{t.status}</span>
                        </td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-2)" }}>
                          ₹{t.buyPrice.toLocaleString("en-IN")}
                        </td>
                        {/* CMP — live price for open, dash for closed */}
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "nowrap" }}>
                          {t.status === "Open"
                            ? cmp != null
                              ? <span style={{ color: cmp >= t.buyPrice ? "var(--green)" : "var(--red)", fontWeight: 700 }}>
                                  ₹{cmp.toLocaleString("en-IN")}
                                </span>
                              : <span style={{ color: "var(--text-4)", fontSize: 9 }}>loading…</span>
                            : <span style={{ color: "var(--text-4)" }}>—</span>}
                        </td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-2)" }}>
                          {t.sellPrice ? `₹${t.sellPrice.toLocaleString("en-IN")}` : "—"}
                        </td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-2)" }}>
                          {t.quantity.toLocaleString("en-IN")}
                        </td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-2)" }}>
                          {rupees(t.capitalUsed).replace("+", "")}
                        </td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                          color: result ? pnlColor(result.pnl) : "var(--text-4)" }}>
                          {result ? rupees(result.pnl) : "—"}
                        </td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                          color: result ? pnlColor(result.pct) : "var(--text-4)" }}>
                          {result ? `${result.pct >= 0 ? "+" : ""}${result.pct.toFixed(2)}%` : "—"}
                        </td>
                        <td style={{ padding: "8px 12px", color: "var(--text-3)", fontSize: 11, maxWidth: 120,
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {t.strategy ?? "—"}
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          {t.ruleFollowed ? (
                            <span style={{
                              padding: "2px 7px", borderRadius: 9999, fontSize: 9, fontWeight: 700,
                              background: t.ruleFollowed === "Yes" ? "rgba(39,174,96,0.12)" : t.ruleFollowed === "No" ? "rgba(231,76,60,0.12)" : "rgba(255,176,23,0.12)",
                              color: t.ruleFollowed === "Yes" ? "var(--green)" : t.ruleFollowed === "No" ? "var(--red)" : "var(--amber)",
                            }}>{t.ruleFollowed}</span>
                          ) : "—"}
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          <div style={{ display: "flex", gap: 4, position: "relative" }}>
                            <button onClick={() => { setEditingTrade(t); setModalOpen(true); }} style={{
                              width: 24, height: 24, borderRadius: 6, border: "1px solid var(--border)",
                              background: "transparent", color: "var(--text-3)", cursor: "pointer",
                              display: "flex", alignItems: "center", justifyContent: "center",
                            }} title="Edit">
                              <BookOpen size={11} />
                            </button>
                            <button onClick={() => setDeleteId(deleteId === t.id ? null : t.id)} style={{
                              width: 24, height: 24, borderRadius: 6, border: "1px solid var(--border)",
                              background: "transparent", color: "var(--text-3)", cursor: "pointer",
                              display: "flex", alignItems: "center", justifyContent: "center",
                            }} title="Delete">
                              <Trash2 size={11} />
                            </button>
                            {deleteId === t.id && (
                              <DeleteConfirm onConfirm={() => onDelete(t.id)} onCancel={() => setDeleteId(null)} />
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </motion.div>
        )}

        {/* EQUITY CURVE */}
        {activeTab === "equity" && (
          <motion.div key="equity" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
            <EquityCurve trades={trades} />
          </motion.div>
        )}

        {/* AI COACH */}
        {activeTab === "coach" && (
          <motion.div key="coach" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 12 }}>

            {/* Quick prompt buttons */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {QUICK_PROMPTS.map(q => (
                <button key={q.label} onClick={() => send(q.msg)} disabled={loading} style={{
                  display: "flex", alignItems: "center", gap: 6, padding: "6px 14px",
                  borderRadius: 9999, border: "1px solid var(--border)",
                  background: "var(--surface-2)", color: "var(--text-2)",
                  fontSize: 11, fontWeight: 600, cursor: "pointer",
                  fontFamily: "var(--font-body)", transition: "all 150ms",
                  opacity: loading ? 0.5 : 1,
                }}>
                  <span>{q.icon}</span> {q.label}
                </button>
              ))}
            </div>

            {/* Chat history */}
            <div style={{
              flex: 1, minHeight: 0, overflowY: "auto",
              background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 12,
            }}>
              {messages.map((m, i) => (
                <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start",
                  flexDirection: m.role === "user" ? "row-reverse" : "row" }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                    background: m.role === "user" ? "var(--accent)" : "var(--surface-3, var(--surface-2))",
                    border: "1px solid var(--border)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    {m.role === "user"
                      ? <User size={13} style={{ color: "#fff" }} />
                      : <Brain size={13} style={{ color: "var(--accent)" }} />}
                  </div>
                  <div style={{
                    maxWidth: "82%", padding: "10px 14px",
                    background: m.role === "user" ? "var(--accent-dim)" : "var(--card-bg)",
                    border: `1px solid ${m.role === "user" ? "var(--accent-border)" : "var(--border)"}`,
                    borderRadius: m.role === "user" ? "14px 4px 14px 14px" : "4px 14px 14px 14px",
                  }}>
                    {m.role === "assistant"
                      ? <div style={{ lineHeight: 1.65 }}>{renderResponse(m.content)}</div>
                      : <div style={{ fontSize: 12, color: "var(--text-1)", lineHeight: 1.6 }}>{m.content}</div>}
                  </div>
                </div>
              ))}
              {loading && (
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: "50%",
                    background: "var(--surface-2)", border: "1px solid var(--border)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <Brain size={13} style={{ color: "var(--accent)" }} />
                  </div>
                  <div style={{
                    padding: "12px 16px", background: "var(--card-bg)", border: "1px solid var(--border)",
                    borderRadius: "4px 14px 14px 14px", display: "flex", gap: 6, alignItems: "center",
                  }}>
                    <Loader2 size={13} style={{ color: "var(--accent)", animation: "spin 1s linear infinite" }} />
                    <span style={{ fontSize: 11, color: "var(--text-3)" }}>Analyzing your trades…</span>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div style={{
              display: "flex", gap: 10, alignItems: "center",
              background: "var(--card-bg)", border: "1px solid var(--border)",
              borderRadius: 12, padding: "10px 14px",
            }}>
              <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
                placeholder={trades.length === 0
                  ? "Log trades first, then ask for analysis…"
                  : "Ask about your performance, psychology, edge, action plan…"}
                disabled={loading}
                style={{
                  flex: 1, background: "transparent", border: "none", outline: "none",
                  color: "var(--text-1)", fontSize: 12, fontFamily: "var(--font-body)",
                }} />
              <button onClick={() => send()} disabled={!input.trim() || loading} style={{
                width: 32, height: 32, borderRadius: 9999, border: "none",
                background: input.trim() && !loading ? "var(--accent)" : "var(--surface-2)",
                color: input.trim() && !loading ? "#fff" : "var(--text-4)",
                cursor: input.trim() && !loading ? "pointer" : "default",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 150ms", flexShrink: 0,
              }}>
                {loading ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Send size={13} />}
              </button>
            </div>
          </motion.div>
        )}
      </div>

      {/* Modals */}
      <AnimatePresence>
        {modalOpen && (
          <AddTradeModal
            open={modalOpen}
            onClose={() => { setModalOpen(false); setEditingTrade(null); }}
            onSave={onSave}
            editing={editingTrade}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
