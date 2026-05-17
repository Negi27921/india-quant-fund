import { useState, useRef, useEffect, useCallback } from "react";
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

const STORAGE_KEY = "iqf_journal_trades_v1";

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
            <input ref={firstRef} value={stockName} onChange={e => setStockName(e.target.value.toUpperCase())}
              placeholder="e.g. RELIANCE" style={FIELD} />
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
            boxShadow: "0 4px 14px rgba(50,121,249,0.35)",
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

// ── Main Page ─────────────────────────────────────────────────────────────────

export function TradingJournalPage() {
  const [trades, setTrades]             = useState<Trade[]>(loadTrades);
  const [activeTab, setActiveTab]       = useState<"log" | "coach">("log");
  const [modalOpen, setModalOpen]       = useState(false);
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);
  const [deleteId, setDeleteId]         = useState<string | null>(null);
  const [messages, setMessages]         = useState<Message[]>([]);
  const [input, setInput]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [sortDesc, setSortDesc]         = useState(true);
  const [syncStatus, setSyncStatus]     = useState<"idle" | "syncing" | "synced" | "error">("idle");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  const metrics = calcMetrics(trades);

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
      // No trades passed — backend reads from DB directly for accurate analysis
      const res = await api.post<{ response: string; trade_count: number }>("/journal/chat", {
        message: msg,
        history: history.slice(-6),
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
        gridTemplateColumns: "repeat(5, 1fr)",
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
          {(["log", "coach"] as const).map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              padding: "7px 18px", borderRadius: 9999, border: "none", cursor: "pointer",
              background: activeTab === tab ? "var(--accent)" : "var(--surface-2)",
              color: activeTab === tab ? "#fff" : "var(--text-3)",
              fontSize: 12, fontWeight: activeTab === tab ? 700 : 500,
              fontFamily: "var(--font-body)", transition: "all 150ms",
            }}>
              {tab === "log" ? "📒 Trade Log" : "🧠 AI Coach"}
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
              boxShadow: "0 4px 14px rgba(50,121,249,0.3)",
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
                    {["Date ↕", "Stock", "Type", "Status", "Buy ₹", "Sell ₹", "Qty", "Capital", "P&L", "P&L%", "Strategy", "Rule", ""].map((h, i) => (
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
                    const result = tradePnL(t);
                    const emoji = t.status === "Open" ? "⚪" : result ? (result.pnl > 0 ? "🟢" : "🔴") : "⚪";
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
                            background: t.tradeType === "Swing" ? "rgba(50,121,249,0.1)" : "rgba(39,174,96,0.1)",
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
