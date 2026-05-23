import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, Trash2, Star, Zap, BarChart3,
  ChevronRight, Search, TrendingUp,
  Sparkles, Send, Loader2, X,
  Trophy, ThumbsUp, Minus,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import {
  useWatchlists, useWatchlistItems,
  useCreateWatchlist, useDeleteWatchlist,
  useAddWatchlistItem, useRemoveWatchlistItem,
  useAnalyseStock,
  type Watchlist, type WatchlistItem,
} from "@/api/watchlist-queries";

// ── Rating badge ──────────────────────────────────────────────────────────────
const RATING_CFG: Record<string, { color: string; bg: string; icon: React.ReactNode }> = {
  Excellent: { color: "#10b981", bg: "rgba(16,185,129,0.10)", icon: <Trophy style={{ width: 10, height: 10 }} /> },
  Great:     { color: "#34d399", bg: "rgba(52,211,153,0.08)", icon: <Star style={{ width: 10, height: 10 }} /> },
  Good:      { color: "#60a5fa", bg: "rgba(96,165,250,0.09)", icon: <ThumbsUp style={{ width: 10, height: 10 }} /> },
  Ok:        { color: "#f59e0b", bg: "rgba(245,158,11,0.08)", icon: <Minus style={{ width: 10, height: 10 }} /> },
};

function RatingBadge({ rating }: { rating: string | null }) {
  if (!rating) return null;
  const cfg = RATING_CFG[rating] ?? { color: "var(--text-3)", bg: "var(--surface-2)", icon: null };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "2px 7px", borderRadius: 10, fontSize: 9, fontWeight: 700,
      letterSpacing: "0.04em", textTransform: "uppercase",
      color: cfg.color, background: cfg.bg,
    }}>
      {cfg.icon}{rating}
    </span>
  );
}

// ── Color picker (minimal) ────────────────────────────────────────────────────
const PALETTE = ["#a78bfa", "#34d399", "#60a5fa", "#f59e0b", "#f87171", "#fb923c", "#e879f9", "#22d3ee"];

// ── Create watchlist modal ────────────────────────────────────────────────────
function CreateModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [color, setColor] = useState("#a78bfa");
  const create = useCreateWatchlist();

  const handleSubmit = () => {
    if (!name.trim()) return;
    create.mutate({ name: name.trim(), description: desc.trim(), color }, {
      onSuccess: () => onClose(),
    });
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        onClick={e => e.stopPropagation()}
        style={{
          background: "var(--surface-1)", border: "1px solid var(--border)",
          borderRadius: 16, padding: 28, width: 400, boxShadow: "0 24px 80px rgba(0,0,0,0.5)",
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-1)", marginBottom: 20 }}>
          New Watchlist
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", display: "block", marginBottom: 6, letterSpacing: "0.06em", textTransform: "uppercase" }}>Name</label>
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSubmit()}
            placeholder="e.g. Nifty 50 Watch"
            style={{
              width: "100%", padding: "9px 12px", borderRadius: 8,
              background: "var(--surface-2)", border: "1px solid var(--border)",
              color: "var(--text-1)", fontSize: 13, outline: "none",
              fontFamily: "var(--font-body)", boxSizing: "border-box",
            }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", display: "block", marginBottom: 6, letterSpacing: "0.06em", textTransform: "uppercase" }}>Description (optional)</label>
          <input
            value={desc}
            onChange={e => setDesc(e.target.value)}
            placeholder="What's this list for?"
            style={{
              width: "100%", padding: "9px 12px", borderRadius: 8,
              background: "var(--surface-2)", border: "1px solid var(--border)",
              color: "var(--text-1)", fontSize: 13, outline: "none",
              fontFamily: "var(--font-body)", boxSizing: "border-box",
            }}
          />
        </div>

        <div style={{ marginBottom: 22 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", display: "block", marginBottom: 8, letterSpacing: "0.06em", textTransform: "uppercase" }}>Color</label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {PALETTE.map(c => (
              <button key={c} onClick={() => setColor(c)} style={{
                width: 28, height: 28, borderRadius: "50%", background: c,
                border: `2px solid ${color === c ? "white" : "transparent"}`,
                cursor: "pointer", outline: "none",
                boxShadow: color === c ? `0 0 0 1px ${c}` : "none",
              }} />
            ))}
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{
            padding: "8px 18px", borderRadius: 8, border: "1px solid var(--border)",
            background: "transparent", color: "var(--text-2)", fontSize: 13,
            cursor: "pointer", fontFamily: "var(--font-body)",
          }}>Cancel</button>
          <button onClick={handleSubmit} disabled={!name.trim() || create.isPending} style={{
            padding: "8px 18px", borderRadius: 8, border: "none",
            background: color, color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: "pointer", fontFamily: "var(--font-body)", opacity: !name.trim() ? 0.5 : 1,
          }}>
            {create.isPending ? "Creating…" : "Create"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ── Add stock modal ───────────────────────────────────────────────────────────
function AddStockModal({ watchlistId, onClose }: { watchlistId: string; onClose: () => void }) {
  const [symbol, setSymbol] = useState("");
  const [company, setCompany] = useState("");
  const [notes, setNotes] = useState("");
  const add = useAddWatchlistItem(watchlistId);

  const handleSubmit = () => {
    const sym = symbol.trim().toUpperCase().replace(/\.NS$|\.BO$/i, "");
    if (!sym) return;
    add.mutate({ symbol: sym, ticker: `${sym}.NS`, company: company.trim(), notes: notes.trim() }, {
      onSuccess: () => onClose(),
    });
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        onClick={e => e.stopPropagation()}
        style={{
          background: "var(--surface-1)", border: "1px solid var(--border)",
          borderRadius: 16, padding: 28, width: 380, boxShadow: "0 24px 80px rgba(0,0,0,0.5)",
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-1)", marginBottom: 20 }}>
          Add Stock
        </div>

        {[
          { label: "Symbol (NSE)", value: symbol, set: setSymbol, placeholder: "e.g. RELIANCE", upper: true },
          { label: "Company (optional)", value: company, set: setCompany, placeholder: "Reliance Industries" },
          { label: "Notes (optional)", value: notes, set: setNotes, placeholder: "Why you're watching this…" },
        ].map(({ label, value, set, placeholder, upper }) => (
          <div key={label} style={{ marginBottom: 14 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", display: "block", marginBottom: 6, letterSpacing: "0.06em", textTransform: "uppercase" }}>{label}</label>
            <input
              value={value}
              onChange={e => set(upper ? e.target.value.toUpperCase() : e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSubmit()}
              placeholder={placeholder}
              style={{
                width: "100%", padding: "9px 12px", borderRadius: 8,
                background: "var(--surface-2)", border: "1px solid var(--border)",
                color: "var(--text-1)", fontSize: 13, outline: "none",
                fontFamily: "var(--font-body)", boxSizing: "border-box",
              }}
            />
          </div>
        ))}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 8 }}>
          <button onClick={onClose} style={{
            padding: "8px 18px", borderRadius: 8, border: "1px solid var(--border)",
            background: "transparent", color: "var(--text-2)", fontSize: 13, cursor: "pointer",
            fontFamily: "var(--font-body)",
          }}>Cancel</button>
          <button onClick={handleSubmit} disabled={!symbol.trim() || add.isPending} style={{
            padding: "8px 18px", borderRadius: 8, border: "none",
            background: "var(--accent)", color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: "pointer", fontFamily: "var(--font-body)", opacity: !symbol.trim() ? 0.5 : 1,
          }}>
            {add.isPending ? "Adding…" : "Add Stock"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ── Chat message ──────────────────────────────────────────────────────────────
interface ChatMsg { role: "user" | "assistant"; content: string }

function ChatBubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div style={{
      display: "flex", justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: 12,
    }}>
      <div style={{
        maxWidth: "88%",
        padding: "10px 14px",
        borderRadius: isUser ? "14px 14px 4px 14px" : "4px 14px 14px 14px",
        background: isUser ? "var(--accent)" : "var(--surface-2)",
        border: isUser ? "none" : "1px solid var(--border)",
        color: isUser ? "#fff" : "var(--text-1)",
        fontSize: 13, lineHeight: 1.7,
        fontFamily: "var(--font-body)",
        whiteSpace: "pre-wrap",
      }}>
        {msg.content}
      </div>
    </div>
  );
}

// ── AI Chat tab ───────────────────────────────────────────────────────────────
function AIChatTab({ symbol }: { symbol: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const analyse = useAnalyseStock();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Reset chat when stock changes
  useEffect(() => { setMessages([]); }, [symbol]);

  const sendMessage = useCallback(async () => {
    const q = input.trim();
    if (!q || analyse.isPending) return;
    const userMsg: ChatMsg = { role: "user", content: q };
    setMessages(prev => [...prev, userMsg]);
    setInput("");

    analyse.mutate(
      { symbol, question: q, history: messages.slice(-6) },
      {
        onSuccess: (data) => {
          setMessages(prev => [...prev, { role: "assistant", content: data.response }]);
        },
        onError: (err) => {
          setMessages(prev => [...prev, { role: "assistant", content: `Error: ${err.message}. Please try again.` }]);
        },
      },
    );
  }, [input, symbol, messages, analyse]);

  const SUGGESTIONS = [
    "Give me a comprehensive fundamental analysis",
    "What's the growth trajectory in last 4 quarters?",
    "Analyse the risk factors for this stock",
    "Compare margins vs sector peers",
    "Is the current valuation attractive?",
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 16px 8px" }}>
        {messages.length === 0 ? (
          <div style={{ padding: "24px 0" }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, marginBottom: 16,
              color: "var(--text-2)", fontSize: 14, fontWeight: 600,
            }}>
              <Sparkles style={{ width: 16, height: 16, color: "var(--accent)" }} />
              Ask DeepSeek R1 about {symbol}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => setInput(s)} style={{
                  textAlign: "left", padding: "9px 14px", borderRadius: 10,
                  background: "var(--surface-2)", border: "1px solid var(--border)",
                  color: "var(--text-2)", fontSize: 12, cursor: "pointer",
                  fontFamily: "var(--font-body)", transition: "all 150ms",
                }}
                  onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-1)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)"; }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => <ChatBubble key={i} msg={msg} />)
        )}
        {analyse.isPending && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-3)", fontSize: 12, marginBottom: 12 }}>
            <Loader2 style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} />
            DeepSeek R1 thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: "12px 16px", borderTop: "1px solid var(--border)",
        display: "flex", gap: 10, alignItems: "flex-end",
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder={`Ask about ${symbol}…`}
          rows={2}
          style={{
            flex: 1, resize: "none", padding: "9px 12px", borderRadius: 10,
            background: "var(--surface-2)", border: "1px solid var(--border)",
            color: "var(--text-1)", fontSize: 13, outline: "none",
            fontFamily: "var(--font-body)", lineHeight: 1.5,
          }}
        />
        <button
          onClick={sendMessage}
          disabled={!input.trim() || analyse.isPending}
          style={{
            width: 38, height: 38, borderRadius: 10, border: "none",
            background: input.trim() ? "var(--accent)" : "var(--surface-3)",
            color: input.trim() ? "#fff" : "var(--text-4)",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: input.trim() ? "pointer" : "default", transition: "all 150ms",
            flexShrink: 0,
          }}
        >
          {analyse.isPending
            ? <Loader2 style={{ width: 16, height: 16, animation: "spin 1s linear infinite" }} />
            : <Send style={{ width: 16, height: 16 }} />}
        </button>
      </div>
    </div>
  );
}

// ── Fundamentals tab ──────────────────────────────────────────────────────────
function FundamentalsTab({ item }: { item: WatchlistItem }) {
  const symbol = item.symbol;

  const rows = [
    { label: "Symbol", value: symbol },
    { label: "Ticker", value: item.ticker || `${symbol}.NS` },
    { label: "Company", value: item.company || "—" },
    ...(item.sector ? [{ label: "Sector", value: item.sector }] : []),
    ...(item.industry ? [{ label: "Industry", value: item.industry }] : []),
    { label: "Rating", value: item.result_rating ? <RatingBadge rating={item.result_rating} /> : "—" },
    { label: "Result Date", value: item.result_date || "—" },
    { label: "Result Day High", value: item.result_high ? `₹${item.result_high.toLocaleString("en-IN")}` : "—" },
    { label: "Avg Volume (20d)", value: item.result_volume_avg ? item.result_volume_avg.toLocaleString("en-IN") : "—" },
    { label: "Breakout", value: item.breakout_date ? `✅ ${item.breakout_date}` : "Not yet" },
    { label: "Added", value: new Date(item.added_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) },
    { label: "Added Reason", value: item.added_reason || "manual" },
    { label: "Notes", value: item.notes || "—" },
  ];

  return (
    <div style={{ padding: "16px" }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 14 }}>
        Stock Details
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {rows.map(({ label, value }) => (
          <div key={label} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "9px 0", borderBottom: "1px solid var(--surface-2)",
          }}>
            <span style={{ fontSize: 12, color: "var(--text-3)", fontWeight: 500 }}>{label}</span>
            <span style={{ fontSize: 12, color: "var(--text-1)", fontWeight: 600, textAlign: "right", maxWidth: "60%" }}>
              {typeof value === "string" ? value : value}
            </span>
          </div>
        ))}
      </div>

      {/* Quick link to NSE */}
      <a
        href={`https://www.nseindia.com/get-quotes/equity?symbol=${symbol}`}
        target="_blank" rel="noopener noreferrer"
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          marginTop: 16, padding: "8px 14px", borderRadius: 8,
          background: "var(--surface-2)", border: "1px solid var(--border)",
          color: "var(--accent)", fontSize: 12, fontWeight: 600,
          textDecoration: "none", transition: "all 150ms",
        }}
      >
        <TrendingUp style={{ width: 13, height: 13 }} />
        View on NSE
      </a>
    </div>
  );
}

// ── Technical tab ─────────────────────────────────────────────────────────────
function TechnicalTab({ item }: { item: WatchlistItem }) {
  const symbol = item.symbol;
  const tradingViewUrl = `https://www.tradingview.com/chart/?symbol=NSE%3A${symbol}`;
  const screenerUrl = `https://www.screener.in/company/${symbol}/`;

  const hasResultHigh = item.result_high != null;
  const isBreakout = !!item.breakout_date;

  return (
    <div style={{ padding: "16px" }}>
      {/* Breakout status card */}
      <div style={{
        padding: "14px 16px", borderRadius: 12, marginBottom: 16,
        background: isBreakout ? "rgba(16,185,129,0.08)" : "rgba(96,165,250,0.06)",
        border: `1px solid ${isBreakout ? "rgba(16,185,129,0.24)" : "rgba(96,165,250,0.18)"}`,
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: isBreakout ? "#10b981" : "#60a5fa", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 6 }}>
          {isBreakout ? "✅ Breakout Confirmed" : "⏳ Watching for Breakout"}
        </div>
        {hasResultHigh && (
          <div style={{ fontSize: 13, color: "var(--text-1)", fontWeight: 600 }}>
            Result day high: <span style={{ fontFamily: "var(--font-mono)" }}>₹{item.result_high!.toLocaleString("en-IN")}</span>
          </div>
        )}
        {isBreakout && (
          <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 4 }}>
            Broke out on {item.breakout_date} with 1.5× volume
          </div>
        )}
        {!isBreakout && hasResultHigh && (
          <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 4 }}>
            Alert triggers when price &gt; ₹{item.result_high!.toLocaleString("en-IN")} on 1.5× avg volume
          </div>
        )}
      </div>

      {/* External chart links */}
      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-3)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
        Charts & Analysis
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {[
          { label: "TradingView Chart", url: tradingViewUrl, icon: <BarChart3 style={{ width: 13, height: 13 }} /> },
          { label: "Screener.in Fundamentals", url: screenerUrl, icon: <Search style={{ width: 13, height: 13 }} /> },
          { label: "NSE Quote", url: `https://www.nseindia.com/get-quotes/equity?symbol=${symbol}`, icon: <TrendingUp style={{ width: 13, height: 13 }} /> },
          { label: "BSE Filing History", url: `https://www.bseindia.com/stock-share-price/${symbol}/`, icon: <Zap style={{ width: 13, height: 13 }} /> },
        ].map(({ label, url, icon }) => (
          <a key={label} href={url} target="_blank" rel="noopener noreferrer" style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 14px", borderRadius: 10,
            background: "var(--surface-2)", border: "1px solid var(--border)",
            color: "var(--text-1)", fontSize: 12, textDecoration: "none",
            transition: "all 150ms",
          }}
            onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--accent)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--border)"; }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent)" }}>
              {icon}
              <span style={{ color: "var(--text-1)" }}>{label}</span>
            </span>
            <ChevronRight style={{ width: 13, height: 13, color: "var(--text-4)" }} />
          </a>
        ))}
      </div>
    </div>
  );
}

// ── Stock detail pane ─────────────────────────────────────────────────────────
type TabType = "fundamentals" | "technical" | "ai";

function StockDetailPane({ item }: { item: WatchlistItem }) {
  const [tab, setTab] = useState<TabType>("fundamentals");

  const TABS: { id: TabType; label: string; icon: React.ReactNode }[] = [
    { id: "fundamentals", label: "Fundamentals", icon: <BarChart3 style={{ width: 13, height: 13 }} /> },
    { id: "technical",   label: "Technical",    icon: <TrendingUp style={{ width: 13, height: 13 }} /> },
    { id: "ai",          label: "AI Chat",       icon: <Sparkles style={{ width: 13, height: 13 }} /> },
  ];

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100%",
      background: "var(--surface-1)", minHeight: 0,
    }}>
      {/* Header */}
      <div style={{
        padding: "16px 20px 0",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.02em", fontFamily: "var(--font-heading)" }}>
              {item.symbol}
            </div>
            {item.company && (
              <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{item.company}</div>
            )}
          </div>
          <RatingBadge rating={item.result_rating} />
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 2 }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 14px", borderRadius: "8px 8px 0 0",
              border: "none", cursor: "pointer",
              background: tab === t.id ? "var(--surface-2)" : "transparent",
              color: tab === t.id ? "var(--accent)" : "var(--text-3)",
              fontSize: 12, fontWeight: tab === t.id ? 700 : 500,
              fontFamily: "var(--font-body)", transition: "all 150ms",
              borderBottom: tab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
            }}>
              {t.icon}{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={tab + item.symbol}
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            style={{ height: "100%" }}
          >
            {tab === "fundamentals" && <FundamentalsTab item={item} />}
            {tab === "technical"    && <TechnicalTab    item={item} />}
            {tab === "ai"           && <AIChatTab       symbol={item.symbol} />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

// ── Left sidebar: watchlist list ──────────────────────────────────────────────
function WatchlistSidebar({
  lists,
  selectedId,
  onSelect,
  onNew,
  onDelete,
}: {
  lists: Watchlist[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div style={{
      width: 220, flexShrink: 0, borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column", background: "var(--sidebar-bg)",
    }}>
      <div style={{
        padding: "16px 14px 10px",
        borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontSize: 11, fontWeight: 800, color: "var(--text-3)", letterSpacing: "0.10em", textTransform: "uppercase" }}>
          Watchlists
        </span>
        <button
          onClick={onNew}
          title="New watchlist"
          style={{
            width: 26, height: 26, borderRadius: 6, border: "1px solid var(--border)",
            background: "transparent", color: "var(--text-3)", cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            transition: "all 150ms",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--accent)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-3)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)"; }}
        >
          <Plus style={{ width: 13, height: 13 }} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "8px 8px" }}>
        {lists.map(wl => {
          const isSelected = wl.id === selectedId;
          return (
            <div
              key={wl.id}
              onClick={() => onSelect(wl.id)}
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "8px 10px", borderRadius: 8, cursor: "pointer",
                background: isSelected ? "var(--accent-dim)" : "transparent",
                border: `1px solid ${isSelected ? "var(--accent-border)" : "transparent"}`,
                marginBottom: 2, transition: "all 150ms",
              }}
              onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-2)"; }}
              onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: wl.color, flexShrink: 0,
                  boxShadow: isSelected ? `0 0 8px ${wl.color}` : "none",
                }} />
                <div style={{ minWidth: 0 }}>
                  <div style={{
                    fontSize: 12, fontWeight: isSelected ? 700 : 500,
                    color: isSelected ? "var(--text-1)" : "var(--text-2)",
                    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                  }}>
                    {wl.name}
                  </div>
                  {wl.type === "auto_results" && (
                    <div style={{ fontSize: 9, color: wl.color, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Auto</div>
                  )}
                  {wl.type === "quarterly_results" && (
                    <div style={{ fontSize: 9, color: wl.color, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Qtrly</div>
                  )}
                  {wl.type === "universe" && (
                    <div style={{ fontSize: 9, color: wl.color, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Live</div>
                  )}
                </div>
              </div>
              {wl.type === "manual" && !["aaaaaaaa-0000-0000-0000-000000000001","bbbbbbbb-0000-0000-0000-000000000001"].includes(wl.id) && (
                <button
                  onClick={e => { e.stopPropagation(); onDelete(wl.id); }}
                  style={{
                    width: 22, height: 22, borderRadius: 4, border: "none",
                    background: "transparent", color: "var(--text-4)", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    transition: "all 150ms", flexShrink: 0,
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "#f87171"; (e.currentTarget as HTMLButtonElement).style.background = "rgba(248,113,113,0.1)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-4)"; (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                >
                  <Trash2 style={{ width: 11, height: 11 }} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Stock row ─────────────────────────────────────────────────────────────────
function StockRow({
  item, isSelected, onSelect, onRemove,
}: {
  item: WatchlistItem;
  isSelected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const sectorLabel = item.industry || item.sector || null;
  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", cursor: "pointer",
        background: isSelected ? "var(--accent-dim)" : "transparent",
        borderLeft: `3px solid ${isSelected ? "var(--accent)" : "transparent"}`,
        borderBottom: "1px solid var(--surface-2)",
        transition: "all 150ms",
      }}
      onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-2)"; }}
      onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-mono)" }}>
            {item.symbol}
          </span>
          {item.result_rating && <RatingBadge rating={item.result_rating} />}
          {item.breakout_date && (
            <span style={{ fontSize: 9, color: "#10b981", fontWeight: 700, letterSpacing: "0.05em" }}>⚡ BREAKOUT</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {item.company && (
            <span style={{ fontSize: 11, color: "var(--text-3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 130 }}>
              {item.company}
            </span>
          )}
          {sectorLabel && (
            <span style={{
              fontSize: 9, color: "var(--text-4)", background: "var(--surface-2)",
              borderRadius: 4, padding: "1px 5px", whiteSpace: "nowrap",
              border: "1px solid var(--border)", flexShrink: 0,
            }}>
              {sectorLabel}
            </span>
          )}
        </div>
      </div>
      <button
        onClick={e => { e.stopPropagation(); onRemove(); }}
        style={{
          width: 24, height: 24, borderRadius: 4, border: "none",
          background: "transparent", color: "var(--text-4)", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, transition: "all 150ms",
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "#f87171"; }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-4)"; }}
      >
        <X style={{ width: 12, height: 12 }} />
      </button>
    </div>
  );
}

// ── Middle pane: stock list ───────────────────────────────────────────────────
function IndustryFilterBar({
  items,
  activeFilter,
  onFilter,
}: {
  items: WatchlistItem[];
  activeFilter: string | null;
  onFilter: (f: string | null) => void;
}) {
  // Collect unique industries/sectors
  const industries = useMemo(() => {
    const set = new Set<string>();
    for (const item of items) {
      if (item.industry) set.add(item.industry);
      else if (item.sector) set.add(item.sector);
    }
    return Array.from(set).sort();
  }, [items]);

  if (industries.length === 0) return null;

  return (
    <div style={{
      display: "flex", gap: 5, flexWrap: "wrap",
      padding: "8px 14px 6px",
      borderBottom: "1px solid var(--border)",
      background: "var(--surface-1)",
    }}>
      <button
        onClick={() => onFilter(null)}
        style={{
          padding: "3px 9px", borderRadius: 10, fontSize: 10, fontWeight: 700,
          cursor: "pointer", border: "none", transition: "all 120ms",
          background: activeFilter === null ? "var(--accent)" : "var(--surface-2)",
          color: activeFilter === null ? "#fff" : "var(--text-3)",
          fontFamily: "var(--font-body)",
        }}
      >
        All
      </button>
      {industries.map(ind => (
        <button
          key={ind}
          onClick={() => onFilter(activeFilter === ind ? null : ind)}
          style={{
            padding: "3px 9px", borderRadius: 10, fontSize: 10, fontWeight: 600,
            cursor: "pointer", border: "1px solid var(--border)", transition: "all 120ms",
            background: activeFilter === ind ? "rgba(167,139,250,0.15)" : "transparent",
            color: activeFilter === ind ? "var(--accent)" : "var(--text-3)",
            fontFamily: "var(--font-body)",
            borderColor: activeFilter === ind ? "var(--accent-border)" : "var(--border)",
          }}
        >
          {ind}
        </button>
      ))}
    </div>
  );
}

function StockListPane({
  watchlist, items, selectedSymbol, onSelectItem, onAddStock,
}: {
  watchlist: Watchlist | null;
  items: WatchlistItem[];
  selectedSymbol: string | null;
  onSelectItem: (item: WatchlistItem) => void;
  onAddStock: () => void;
}) {
  const remove = useRemoveWatchlistItem(watchlist?.id ?? "");
  const [search, setSearch] = useState("");
  const [industryFilter, setIndustryFilter] = useState<string | null>(null);

  // Reset filter when watchlist changes
  useEffect(() => { setIndustryFilter(null); setSearch(""); }, [watchlist?.id]);

  const filtered = useMemo(() => items.filter(i => {
    const matchSearch = !search || i.symbol.toLowerCase().includes(search.toLowerCase()) ||
      (i.company || "").toLowerCase().includes(search.toLowerCase());
    const matchIndustry = !industryFilter ||
      i.industry === industryFilter || i.sector === industryFilter;
    return matchSearch && matchIndustry;
  }), [items, search, industryFilter]);

  if (!watchlist) {
    return (
      <div style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        color: "var(--text-4)", fontSize: 13, borderRight: "1px solid var(--border)",
      }}>
        Select a watchlist
      </div>
    );
  }

  const canAdd = watchlist.type === "manual" && !["aaaaaaaa-0000-0000-0000-000000000001","bbbbbbbb-0000-0000-0000-000000000001"].includes(watchlist.id);

  return (
    <div style={{
      width: 280, flexShrink: 0, borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      {/* List header */}
      <div style={{
        padding: "12px 14px 10px", borderBottom: "1px solid var(--border)",
        display: "flex", flexDirection: "column", gap: 8, flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 9, height: 9, borderRadius: "50%", background: watchlist.color, boxShadow: `0 0 8px ${watchlist.color}` }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-1)" }}>{watchlist.name}</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>
              {industryFilter ? `${filtered.length}/${items.length}` : items.length} stocks
              {industryFilter && <span style={{ color: "var(--accent)", marginLeft: 4 }}>· {industryFilter}</span>}
            </div>
          </div>
          {canAdd && (
            <button
              onClick={onAddStock}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "6px 10px", borderRadius: 8,
                border: "1px solid var(--border)", background: "transparent",
                color: "var(--text-2)", fontSize: 11, cursor: "pointer",
                fontFamily: "var(--font-body)", fontWeight: 600,
                transition: "all 150ms",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--accent)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)"; }}
            >
              <Plus style={{ width: 11, height: 11 }} />Add
            </button>
          )}
        </div>

        {/* Search */}
        <div style={{ position: "relative" }}>
          <Search style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", width: 12, height: 12, color: "var(--text-4)" }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search stocks…"
            style={{
              width: "100%", padding: "7px 10px 7px 28px", borderRadius: 8,
              background: "var(--surface-2)", border: "1px solid var(--border)",
              color: "var(--text-1)", fontSize: 12, outline: "none",
              fontFamily: "var(--font-body)", boxSizing: "border-box",
            }}
          />
        </div>
      </div>

      {/* Industry filter chips */}
      <IndustryFilterBar
        items={items}
        activeFilter={industryFilter}
        onFilter={setIndustryFilter}
      />

      {/* Stock list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.length === 0 ? (
          <div style={{
            padding: "32px 16px", textAlign: "center",
            color: "var(--text-4)", fontSize: 12,
          }}>
            {items.length === 0
              ? watchlist.type === "universe"
                ? "Universe Agent runs daily at 6:30 AM IST.\nAll BSE/NSE stocks > ₹1000 Cr market cap\nwill populate here automatically."
                : watchlist.type === "auto_results"
                  ? "Auto-populated from BSE results.\nGood / Great / Excellent rated stocks\nwill appear here after pipeline runs."
                  : watchlist.type === "quarterly_results"
                    ? "Auto-created for this quarter's results.\nStocks will appear as BSE filings are processed."
                    : "No stocks yet.\nClick + Add to start watching."
              : "No matching stocks"}
          </div>
        ) : (
          filtered.map(item => (
            <StockRow
              key={item.id}
              item={item}
              isSelected={selectedSymbol === item.symbol}
              onSelect={() => onSelectItem(item)}
              onRemove={() => remove.mutate(item.symbol)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function WatchlistPage() {
  const { data: lists = [], isLoading } = useWatchlists();
  const [selectedWlId, setSelectedWlId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<WatchlistItem | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAddStock, setShowAddStock] = useState(false);
  const deleteWl = useDeleteWatchlist();

  const { data: items = [] } = useWatchlistItems(selectedWlId);

  const selectedWl = lists.find(w => w.id === selectedWlId) ?? null;

  // Auto-select Results Radar on first load
  useEffect(() => {
    if (lists.length > 0 && !selectedWlId) {
      const auto = lists.find(w => w.type === "auto_results");
      setSelectedWlId(auto?.id ?? lists[0].id);
    }
  }, [lists, selectedWlId]);

  // Deselect item when switching list
  const handleSelectList = (id: string) => {
    setSelectedWlId(id);
    setSelectedItem(null);
  };

  const handleDeleteWl = (id: string) => {
    if (!confirm("Delete this watchlist and all its stocks?")) return;
    deleteWl.mutate(id, {
      onSuccess: () => {
        if (selectedWlId === id) {
          setSelectedWlId(lists.find(w => w.id !== id)?.id ?? null);
          setSelectedItem(null);
        }
      },
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <Header title="Watchlist" subtitle="Track, analyse, and get AI insights on your stocks" />

      <div style={{ flex: 1, display: "flex", overflow: "hidden", minHeight: 0 }}>
        {/* Left: watchlist sidebar */}
        {isLoading ? (
          <div style={{ width: 220, borderRight: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Loader2 style={{ width: 18, height: 18, animation: "spin 1s linear infinite", color: "var(--text-4)" }} />
          </div>
        ) : (
          <WatchlistSidebar
            lists={lists}
            selectedId={selectedWlId}
            onSelect={handleSelectList}
            onNew={() => setShowCreateModal(true)}
            onDelete={handleDeleteWl}
          />
        )}

        {/* Middle: stock list */}
        <StockListPane
          watchlist={selectedWl}
          items={items}
          selectedSymbol={selectedItem?.symbol ?? null}
          onSelectItem={setSelectedItem}
          onAddStock={() => setShowAddStock(true)}
        />

        {/* Right: detail pane */}
        <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", minWidth: 0 }}>
          {selectedItem ? (
            <StockDetailPane item={selectedItem} />
          ) : (
            <div style={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              color: "var(--text-4)", gap: 12,
            }}>
              <Sparkles style={{ width: 40, height: 40, opacity: 0.3 }} />
              <div style={{ fontSize: 14, fontWeight: 600 }}>Select a stock to analyse</div>
              <div style={{ fontSize: 12 }}>Fundamentals · Technical · AI Chat</div>
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      <AnimatePresence>
        {showCreateModal && <CreateModal onClose={() => setShowCreateModal(false)} />}
        {showAddStock && selectedWlId && (
          <AddStockModal watchlistId={selectedWlId} onClose={() => setShowAddStock(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}
