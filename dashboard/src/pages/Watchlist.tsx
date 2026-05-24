import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, Trash2, Star, Zap, BarChart3,
  ChevronRight, Search, TrendingUp,
  Sparkles, Send, Loader2, X,
  Trophy, ThumbsUp, Minus, Filter,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import {
  useWatchlists, useWatchlistItems,
  useCreateWatchlist, useDeleteWatchlist,
  useAddWatchlistItem, useRemoveWatchlistItem,
  useAnalyseStock, useUniverseSearch,
  type Watchlist, type WatchlistItem,
} from "@/api/watchlist-queries";
import { useBatchPrices, useStockFundamentals } from "@/api/market-queries";

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
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0e1117", border: "1px solid rgba(167,139,250,0.3)",
          borderRadius: 16, padding: 28, width: 400,
          boxShadow: "0 32px 96px rgba(0,0,0,0.8), 0 0 0 1px rgba(167,139,250,0.08)",
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

// ── Universe stock picker modal ───────────────────────────────────────────────
function AddStockModal({ watchlistId, onClose }: { watchlistId: string; onClose: () => void }) {
  const [query, setQuery]       = useState("");
  const [debouncedQ, setDQ]     = useState("");
  const [selected, setSelected] = useState<{ symbol: string; company: string; sector: string; industry: string } | null>(null);
  const [notes, setNotes]       = useState("");
  const add = useAddWatchlistItem(watchlistId);
  const { data: results = [], isFetching } = useUniverseSearch(debouncedQ);
  const timerRef = useRef<number>(0);

  useEffect(() => {
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setDQ(query), 250);
    return () => window.clearTimeout(timerRef.current);
  }, [query]);

  const handleAdd = () => {
    if (!selected) return;
    add.mutate({
      symbol:   selected.symbol,
      ticker:   `${selected.symbol}.NS`,
      company:  selected.company,
      sector:   selected.sector,
      industry: selected.industry,
      notes:    notes.trim(),
    }, { onSuccess: () => onClose() });
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 100,
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        onClick={e => e.stopPropagation()}
        style={{
          background: "#0e1117", border: "1px solid rgba(0,255,135,0.25)",
          borderRadius: 16, padding: 24, width: 460,
          boxShadow: "0 32px 96px rgba(0,0,0,0.8), 0 0 0 1px rgba(0,255,135,0.08)",
          display: "flex", flexDirection: "column", gap: 16,
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-1)" }}>
            Add from Universe
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-4)", cursor: "pointer", display: "flex" }}>
            <X style={{ width: 16, height: 16 }} />
          </button>
        </div>

        {/* Search input */}
        <div style={{ position: "relative" }}>
          <Search style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", width: 13, height: 13, color: "var(--text-4)" }} />
          {isFetching && <Loader2 style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", width: 13, height: 13, color: "var(--accent)", animation: "spin 1s linear infinite" }} />}
          <input
            autoFocus
            value={query}
            onChange={e => { setQuery(e.target.value); setSelected(null); }}
            placeholder="Search symbol or company name…"
            style={{
              width: "100%", padding: "10px 12px 10px 32px", borderRadius: 10,
              background: "var(--surface-2)", border: "1px solid var(--border)",
              color: "var(--text-1)", fontSize: 13, outline: "none",
              fontFamily: "var(--font-body)", boxSizing: "border-box",
            }}
            onFocus={e => (e.currentTarget.style.borderColor = "var(--accent)")}
            onBlur={e  => (e.currentTarget.style.borderColor = "var(--border)")}
          />
        </div>

        {/* Results list */}
        <div style={{
          maxHeight: 260, overflowY: "auto", borderRadius: 10,
          border: "1px solid var(--border)", background: "var(--surface-2)",
        }}>
          {results.length === 0 && !isFetching && debouncedQ.length >= 1 ? (
            <div style={{ padding: "20px 16px", textAlign: "center", color: "var(--text-4)", fontSize: 12 }}>
              No stocks found for "{debouncedQ}"
            </div>
          ) : results.length === 0 && !debouncedQ ? (
            <div style={{ padding: "20px 16px", textAlign: "center", color: "var(--text-4)", fontSize: 12 }}>
              Type to search 2000+ NSE/BSE stocks
            </div>
          ) : (
            results.map(stock => {
              const isSel = selected?.symbol === stock.symbol;
              return (
                <div
                  key={stock.symbol}
                  onClick={() => setSelected(stock)}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 14px", cursor: "pointer", transition: "all 120ms",
                    background: isSel ? "rgba(0,255,135,0.08)" : "transparent",
                    borderLeft: `3px solid ${isSel ? "var(--accent)" : "transparent"}`,
                    borderBottom: "1px solid var(--surface-3)",
                  }}
                  onMouseEnter={e => { if (!isSel) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-3)"; }}
                  onMouseLeave={e => { if (!isSel) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-1)", fontFamily: "var(--font-mono)" }}>
                      {stock.symbol}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-3)", marginTop: 1 }}>
                      {stock.company}
                    </div>
                  </div>
                  {stock.industry || stock.sector ? (
                    <span style={{
                      fontSize: 9, fontWeight: 600, padding: "2px 7px", borderRadius: 5,
                      background: "var(--surface-1)", border: "1px solid var(--border)",
                      color: "var(--text-3)", letterSpacing: "0.04em",
                    }}>
                      {stock.industry || stock.sector}
                    </span>
                  ) : null}
                </div>
              );
            })
          )}
        </div>

        {/* Selected stock preview */}
        {selected && (
          <div style={{
            padding: "10px 14px", borderRadius: 10,
            background: "rgba(0,255,135,0.06)", border: "1px solid rgba(0,255,135,0.2)",
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", marginBottom: 2 }}>
              Selected: {selected.symbol}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-2)" }}>{selected.company}</div>
          </div>
        )}

        {/* Notes */}
        <div>
          <label style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", display: "block", marginBottom: 5, letterSpacing: "0.07em", textTransform: "uppercase" }}>
            Notes (optional)
          </label>
          <input
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Why you're watching this…"
            style={{
              width: "100%", padding: "9px 12px", borderRadius: 8, boxSizing: "border-box",
              background: "var(--surface-2)", border: "1px solid var(--border)",
              color: "var(--text-1)", fontSize: 12, outline: "none", fontFamily: "var(--font-body)",
            }}
          />
        </div>

        {/* Actions */}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{
            padding: "8px 18px", borderRadius: 8, border: "1px solid var(--border)",
            background: "transparent", color: "var(--text-2)", fontSize: 13, cursor: "pointer",
            fontFamily: "var(--font-body)",
          }}>Cancel</button>
          <button
            onClick={handleAdd}
            disabled={!selected || add.isPending}
            style={{
              padding: "8px 20px", borderRadius: 8, border: "none",
              background: selected ? "var(--accent)" : "var(--surface-3)",
              color: selected ? "#000" : "var(--text-4)", fontSize: 13, fontWeight: 700,
              cursor: selected ? "pointer" : "default", fontFamily: "var(--font-body)",
              transition: "all 150ms",
            }}
          >
            {add.isPending ? "Adding…" : "Add to Watchlist"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ── Chat message ──────────────────────────────────────────────────────────────
interface ChatMsg { role: "user" | "assistant"; content: string }

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let key = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    // Headings: ### ## #
    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const sz = level === 1 ? 14 : level === 2 ? 13 : 12;
      nodes.push(
        <div key={key++} style={{ fontWeight: 700, fontSize: sz, color: "var(--text-1)", marginTop: 10, marginBottom: 2 }}>
          {inlineMd(headingMatch[2])}
        </div>
      );
      continue;
    }
    // Bullet: - item or * item
    if (/^[-*]\s/.test(trimmed)) {
      nodes.push(
        <div key={key++} style={{ display: "flex", gap: 8, marginBottom: 3, paddingLeft: 4 }}>
          <span style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }}>•</span>
          <span style={{ fontSize: 13, lineHeight: 1.65, color: "var(--text-1)" }}>{inlineMd(trimmed.slice(2))}</span>
        </div>
      );
      continue;
    }
    // Empty line → spacer
    if (!trimmed) {
      nodes.push(<div key={key++} style={{ height: 6 }} />);
      continue;
    }
    // Normal line
    nodes.push(
      <div key={key++} style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 2, color: "var(--text-1)" }}>
        {inlineMd(line)}
      </div>
    );
  }
  return nodes;
}

function inlineMd(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return <strong key={i} style={{ color: "var(--text-1)", fontWeight: 700 }}>{p.slice(2, -2)}</strong>;
    }
    return p;
  });
}

function ChatBubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div style={{
      display: "flex", justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: 12,
    }}>
      <div style={{
        maxWidth: "92%",
        padding: "10px 14px",
        borderRadius: isUser ? "14px 14px 4px 14px" : "4px 14px 14px 14px",
        background: isUser ? "var(--accent)" : "var(--surface-2)",
        border: isUser ? "none" : "1px solid var(--border)",
        color: isUser ? "#fff" : "var(--text-1)",
        fontFamily: "var(--font-body)",
      }}>
        {isUser
          ? <span style={{ fontSize: 13, lineHeight: 1.7 }}>{msg.content}</span>
          : <div>{renderMarkdown(msg.content)}</div>
        }
      </div>
    </div>
  );
}

// ── AI Chat tab ───────────────────────────────────────────────────────────────

// Pre-defined FAQs — label shown on button, question sent to AI
const FAQS: { label: string; question: string }[] = [
  { label: "Full analysis", question: "Give full analysis: thesis, fundamentals, technicals, trade structure with entry/stop/target." },
  { label: "Entry & targets", question: "What is the best 1:3 risk-reward setup for this stock? Give specific entry zone, stop-loss, TP1 and TP2 levels with reasoning." },
  { label: "FII/DII flow", question: "Analyse FII/DII trend and institutional positioning for this stock. Is smart money accumulating or distributing?" },
  { label: "Near-term catalyst", question: "Is there a near-term catalyst that can reprice this stock fast? Any upcoming earnings, policy, or sector trigger?" },
  { label: "Breakout level", question: "Where is the key breakout level for this stock? What price and volume conditions would confirm a breakout?" },
  { label: "Key risks", question: "What are the key risks, red flags, and invalidation levels I should watch for this stock?" },
];

function AIChatTab({ symbol }: { symbol: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const analyse = useAnalyseStock();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Reset chat when stock changes — do NOT auto-send analysis
  useEffect(() => { setMessages([]); setInput(""); }, [symbol]);

  const sendQuestion = useCallback((question: string) => {
    if (!question.trim() || analyse.isPending) return;
    const userMsg: ChatMsg = { role: "user", content: question };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    analyse.mutate(
      { symbol, question, history: messages.slice(-6) },
      {
        onSuccess: (data) => {
          setMessages(prev => [...prev, { role: "assistant", content: data.response }]);
        },
        onError: (err) => {
          setMessages(prev => [...prev, { role: "assistant", content: `Error: ${err.message}. Please try again.` }]);
        },
      },
    );
  }, [symbol, messages, analyse]);

  const sendMessage = useCallback(() => sendQuestion(input.trim()), [input, sendQuestion]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* Messages / FAQ home */}
      <div style={{ flex: 1, overflowY: "auto", padding: "14px 16px 8px" }}>
        {messages.length === 0 ? (
          <div>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, marginBottom: 4,
              color: "var(--text-2)", fontSize: 13, fontWeight: 700,
            }}>
              <Sparkles style={{ width: 14, height: 14, color: "var(--accent)" }} />
              AI Analysis · {symbol}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-4)", marginBottom: 14, fontFamily: "var(--font-body)" }}>
              Pick a question or type your own below
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {FAQS.map(faq => (
                <button
                  key={faq.label}
                  onClick={() => sendQuestion(faq.question)}
                  disabled={analyse.isPending}
                  style={{
                    textAlign: "left", padding: "9px 14px", borderRadius: 10,
                    background: "var(--surface-2)", border: "1px solid var(--border)",
                    color: "var(--text-2)", fontSize: 12, cursor: "pointer",
                    fontFamily: "var(--font-body)", transition: "all 150ms",
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
                  }}
                  onMouseEnter={e => {
                    const el = e.currentTarget as HTMLButtonElement;
                    el.style.borderColor = "var(--accent)";
                    el.style.color = "var(--text-1)";
                    el.style.background = "var(--accent-dim)";
                  }}
                  onMouseLeave={e => {
                    const el = e.currentTarget as HTMLButtonElement;
                    el.style.borderColor = "var(--border)";
                    el.style.color = "var(--text-2)";
                    el.style.background = "var(--surface-2)";
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{faq.label}</span>
                  <Send style={{ width: 11, height: 11, flexShrink: 0, opacity: 0.5 }} />
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
            Analysing…
          </div>
        )}
        {messages.length > 0 && !analyse.isPending && (
          <button
            onClick={() => setMessages([])}
            style={{ fontSize: 10, color: "var(--text-4)", background: "none", border: "none", cursor: "pointer", padding: "4px 0", marginBottom: 4 }}
          >
            ← Back to questions
          </button>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: "10px 14px", borderTop: "1px solid var(--border)",
        display: "flex", gap: 8, alignItems: "flex-end",
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder={`Ask about ${symbol}…`}
          rows={2}
          style={{
            flex: 1, resize: "none", padding: "8px 11px", borderRadius: 10,
            background: "var(--surface-2)", border: "1px solid var(--border)",
            color: "var(--text-1)", fontSize: 12, outline: "none",
            fontFamily: "var(--font-body)", lineHeight: 1.5,
          }}
        />
        <button
          onClick={sendMessage}
          disabled={!input.trim() || analyse.isPending}
          style={{
            width: 36, height: 36, borderRadius: 9, border: "none",
            background: input.trim() ? "var(--accent)" : "var(--surface-3)",
            color: input.trim() ? "#fff" : "var(--text-4)",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: input.trim() ? "pointer" : "default", transition: "all 150ms",
            flexShrink: 0,
          }}
        >
          {analyse.isPending
            ? <Loader2 style={{ width: 15, height: 15, animation: "spin 1s linear infinite" }} />
            : <Send style={{ width: 15, height: 15 }} />}
        </button>
      </div>
    </div>
  );
}

// ── Fundamentals tab ──────────────────────────────────────────────────────────
function FundamentalsTab({ item }: { item: WatchlistItem }) {
  const symbol = item.symbol;
  const { data: f, isLoading } = useStockFundamentals(symbol);

  function FRow({ label, value, highlight }: { label: string; value: React.ReactNode; highlight?: boolean }) {
    return (
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "8px 0", borderBottom: "1px solid var(--border-2)",
      }}>
        <span style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 12, color: highlight ? "var(--accent)" : "var(--text-1)", fontWeight: 700, fontFamily: "var(--font-mono)", textAlign: "right" }}>
          {value}
        </span>
      </div>
    );
  }

  function Section({ title }: { title: string }) {
    return (
      <div style={{ fontSize: 9.5, fontWeight: 700, color: "var(--text-4)", letterSpacing: "0.1em", textTransform: "uppercase", marginTop: 18, marginBottom: 6 }}>
        {title}
      </div>
    );
  }

  const na = "—";
  const pct = (v: number | undefined) => (v != null && v !== 0) ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : na;
  const num = (v: number | undefined, dec = 1) => (v != null && v !== 0) ? v.toFixed(dec) : na;
  const inr = (v: number | undefined) => (v != null && v !== 0) ? `₹${v.toLocaleString("en-IN")}` : na;

  return (
    <div style={{ padding: "14px 16px", overflowY: "auto", maxHeight: "calc(100vh - 240px)" }}>

      {/* Header: result context from watchlist row */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        {item.result_rating && <RatingBadge rating={item.result_rating} />}
        {item.sector && (
          <span style={{ fontSize: 9, fontWeight: 600, color: "var(--text-3)", background: "var(--surface-2)", border: "1px solid var(--border)", padding: "2px 7px", borderRadius: 4 }}>
            {item.sector}
          </span>
        )}
        {item.industry && item.industry !== item.sector && (
          <span style={{ fontSize: 9, fontWeight: 600, color: "var(--text-4)", background: "var(--surface-2)", border: "1px solid var(--border)", padding: "2px 7px", borderRadius: 4 }}>
            {item.industry}
          </span>
        )}
      </div>

      {isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 24, borderRadius: 4 }} />
          ))}
        </div>
      ) : f && !f.error ? (
        <>
          <Section title="Valuation" />
          <FRow label="Market Cap" value={f.market_cap_cr >= 1000 ? `₹${(f.market_cap_cr / 1000).toFixed(1)}K Cr` : `₹${f.market_cap_cr.toFixed(0)} Cr`} />
          <FRow label="P/E (TTM)" value={num(f.pe)} highlight />
          <FRow label="Forward P/E" value={num(f.forward_pe)} />
          <FRow label="P/B" value={num(f.pb)} />
          <FRow label="EV/EBITDA" value={num(f.ev_ebitda)} />
          <FRow label="Beta" value={num(f.beta, 2)} />

          <Section title="Earnings & Growth" />
          <FRow label="EPS (TTM)" value={inr(f.eps_ttm)} highlight />
          <FRow label="EPS (Forward)" value={inr(f.eps_forward)} />
          <FRow label="Revenue Growth (YoY)" value={pct(f.revenue_growth)} />
          <FRow label="Earnings Growth (YoY)" value={pct(f.earnings_growth)} />

          <Section title="Profitability" />
          <FRow label="ROE" value={pct(f.roe)} highlight />
          <FRow label="ROA" value={pct(f.roa)} />
          <FRow label="Operating Margin" value={pct(f.op_margin)} />
          <FRow label="Profit Margin" value={pct(f.profit_margin)} />

          <Section title="Balance Sheet" />
          <FRow label="Debt / Equity" value={num(f.debt_to_equity, 2)} />
          <FRow label="Current Ratio" value={num(f.current_ratio, 2)} />
          <FRow label="Book Value / Share" value={inr(f.book_value)} />

          <Section title="Market Data" />
          <FRow label="52W High" value={inr(f.week_high_52)} />
          <FRow label="52W Low" value={inr(f.week_low_52)} />
          <FRow label="Dividend Yield" value={pct(f.dividend_yield)} />
          <FRow label="Shares Outstanding" value={f.shares_cr ? `${f.shares_cr.toFixed(1)} Cr` : na} />

          <div style={{ marginTop: 6, fontSize: 9, color: "var(--text-4)", fontFamily: "var(--font-body)" }}>
            Source: yfinance · {f.ticker_used}
          </div>
        </>
      ) : (
        <>
          <Section title="From System" />
          <FRow label="Symbol" value={symbol} />
          <FRow label="Result Rating" value={item.result_rating ? <RatingBadge rating={item.result_rating} /> : na} />
          <FRow label="Result Date" value={item.result_date || na} />
          <FRow label="Result Day High" value={item.result_high ? inr(item.result_high) : na} />
          <FRow label="Avg Volume (20d)" value={item.result_volume_avg?.toLocaleString("en-IN") ?? na} />
          <FRow label="Added" value={new Date(item.added_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} />
        </>
      )}

      <a
        href={`https://www.screener.in/company/${symbol}/`}
        target="_blank" rel="noopener noreferrer"
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          marginTop: 14, padding: "8px 14px", borderRadius: 8,
          background: "var(--surface-2)", border: "1px solid var(--border)",
          color: "var(--accent)", fontSize: 12, fontWeight: 600,
          textDecoration: "none",
        }}
      >
        <Search style={{ width: 12, height: 12 }} />
        Full detail on Screener.in
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

function StockDetailPane({ item, watchlistName }: { item: WatchlistItem; watchlistName?: string }) {
  const [tab, setTab] = useState<TabType>("fundamentals");

  const [livePrice, setLivePrice] = useState<{
    cmp: number | null; change: number | null; pct_change: number | null;
    week_high_52: number | null; week_low_52: number | null;
    volume: number | null; delivery_pct: number | null; vwap: number | null;
  } | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);

  useEffect(() => {
    setPriceLoading(true);
    setLivePrice(null);
    fetch(`/api/market/price/${item.symbol}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setLivePrice(d); })
      .catch(() => {})
      .finally(() => setPriceLoading(false));
  }, [item.symbol]);

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
        padding: "12px 20px 0",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        {/* Breadcrumb */}
        {watchlistName && (
          <div style={{
            display: "flex", alignItems: "center", gap: 5, marginBottom: 10,
            fontSize: 10, color: "var(--text-4)", fontFamily: "var(--font-body)", fontWeight: 600,
          }}>
            <span style={{ letterSpacing: "0.06em", textTransform: "uppercase" }}>{watchlistName}</span>
            <ChevronRight style={{ width: 10, height: 10 }} />
            <span style={{ color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700 }}>{item.symbol}</span>
          </div>
        )}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.02em", fontFamily: "var(--font-heading)" }}>
              {item.symbol}
            </div>
            {item.company && (
              <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 1 }}>{item.company}</div>
            )}
            <div style={{ display: "flex", gap: 5, marginTop: 5, flexWrap: "wrap" }}>
              {item.sector && <span style={{ fontSize: 9, fontWeight: 600, color: "var(--text-4)", background: "var(--surface-2)", border: "1px solid var(--border)", padding: "1px 6px", borderRadius: 4 }}>{item.sector}</span>}
              {item.industry && item.industry !== item.sector && <span style={{ fontSize: 9, fontWeight: 600, color: "var(--text-4)", background: "var(--surface-2)", border: "1px solid var(--border)", padding: "1px 6px", borderRadius: 4 }}>{item.industry}</span>}
            </div>
          </div>
          <RatingBadge rating={item.result_rating} />
        </div>

        {/* Live price banner */}
        <div style={{
          padding: "12px 16px",
          background: "var(--surface-2)",
          borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "center", flexWrap: "wrap", gap: 16,
        }}>
          {priceLoading ? (
            <span style={{ fontSize: 12, color: "var(--text-4)" }}>Fetching live price…</span>
          ) : livePrice?.cmp ? (
            <>
              <div>
                <span style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--text-1)" }}>
                  ₹{livePrice.cmp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </span>
                {livePrice.pct_change != null && (
                  <span style={{
                    marginLeft: 10, fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono)",
                    color: livePrice.pct_change >= 0 ? "#10b981" : "#f87171",
                  }}>
                    {livePrice.pct_change >= 0 ? "▲" : "▼"} {Math.abs(livePrice.pct_change).toFixed(2)}%
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                {livePrice.week_high_52 && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 9, color: "var(--text-4)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>52W High</div>
                    <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "#10b981", fontWeight: 700 }}>₹{livePrice.week_high_52.toLocaleString("en-IN")}</div>
                  </div>
                )}
                {livePrice.week_low_52 && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 9, color: "var(--text-4)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>52W Low</div>
                    <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "#f87171", fontWeight: 700 }}>₹{livePrice.week_low_52.toLocaleString("en-IN")}</div>
                  </div>
                )}
                {livePrice.vwap && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 9, color: "var(--text-4)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>VWAP</div>
                    <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-2)", fontWeight: 700 }}>₹{livePrice.vwap.toLocaleString("en-IN")}</div>
                  </div>
                )}
                {livePrice.volume != null && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 9, color: "var(--text-4)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>Volume</div>
                    <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-2)", fontWeight: 700 }}>
                      {livePrice.volume >= 1e6
                        ? `${(livePrice.volume / 1e6).toFixed(1)}M`
                        : livePrice.volume >= 1e3
                        ? `${(livePrice.volume / 1e3).toFixed(0)}K`
                        : livePrice.volume}
                    </div>
                  </div>
                )}
                {livePrice.delivery_pct != null && (
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 9, color: "var(--text-4)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>Delivery%</div>
                    <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--accent)", fontWeight: 700 }}>{Number(livePrice.delivery_pct).toFixed(1)}%</div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <span style={{ fontSize: 12, color: "var(--text-4)" }}>{item.symbol} · Price unavailable (market closed)</span>
          )}
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
  item, isSelected, onSelect, onRemove, cmp,
}: {
  item: WatchlistItem;
  isSelected: boolean;
  onSelect: () => void;
  onRemove: () => void;
  cmp?: { cmp: number; pct_change: number } | null;
}) {
  const sectorLabel = item.industry || item.sector || null;
  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", cursor: "pointer",
        background: isSelected ? "rgba(96,165,250,0.10)" : "transparent",
        borderLeft: `3px solid ${isSelected ? "var(--accent)" : "transparent"}`,
        borderRight: `3px solid ${isSelected ? "var(--accent)" : "transparent"}`,
        borderBottom: "1px solid var(--surface-2)",
        transition: "all 150ms",
        boxShadow: isSelected ? "inset 0 0 0 1px rgba(96,165,250,0.18)" : "none",
      }}
      onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-2)"; }}
      onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: isSelected ? "var(--accent)" : "var(--text-1)", fontFamily: "var(--font-mono)" }}>
            {item.symbol}
          </span>
          {item.result_rating && <RatingBadge rating={item.result_rating} />}
          {item.breakout_date && (
            <span style={{ fontSize: 9, color: "#10b981", fontWeight: 700, letterSpacing: "0.05em" }}>⚡</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          {item.company && (
            <span style={{ fontSize: 10, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 110 }}>
              {item.company}
            </span>
          )}
          {sectorLabel && (
            <span style={{
              fontSize: 8.5, color: "var(--text-4)", background: "var(--surface-2)",
              borderRadius: 3, padding: "1px 4px", whiteSpace: "nowrap",
              border: "1px solid var(--border)", flexShrink: 0,
            }}>
              {sectorLabel}
            </span>
          )}
        </div>
      </div>

      {/* CMP */}
      <div style={{ textAlign: "right", marginRight: 8, flexShrink: 0 }}>
        {cmp ? (
          <>
            <div style={{ fontSize: 12, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text-1)" }}>
              ₹{cmp.cmp.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </div>
            <div style={{
              fontSize: 9.5, fontWeight: 700, fontFamily: "var(--font-mono)",
              color: cmp.pct_change >= 0 ? "#10b981" : "#f87171",
            }}>
              {cmp.pct_change >= 0 ? "▲" : "▼"}{Math.abs(cmp.pct_change).toFixed(1)}%
            </div>
          </>
        ) : (
          <div style={{ fontSize: 10, color: "var(--text-4)" }}>—</div>
        )}
      </div>

      <button
        onClick={e => { e.stopPropagation(); onRemove(); }}
        style={{
          width: 22, height: 22, borderRadius: 4, border: "none",
          background: "transparent", color: "var(--text-4)", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, transition: "all 150ms",
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = "#f87171"; }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = "var(--text-4)"; }}
      >
        <X style={{ width: 11, height: 11 }} />
      </button>
    </div>
  );
}

// ── Industry filter dropdown ──────────────────────────────────────────────────
function IndustryFilterBar({
  items,
  activeFilter,
  onFilter,
}: {
  items: WatchlistItem[];
  activeFilter: string | null;
  onFilter: (f: string | null) => void;
}) {
  const industries = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      const label = item.industry || item.sector || "";
      if (label) counts.set(label, (counts.get(label) ?? 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [items]);

  if (industries.length === 0) return null;

  return (
    <div style={{
      padding: "7px 14px 6px",
      borderBottom: "1px solid var(--border)",
      background: "var(--surface-1)",
      display: "flex", alignItems: "center", gap: 8,
    }}>
      <Filter style={{ width: 11, height: 11, color: "var(--text-4)", flexShrink: 0 }} />
      <select
        value={activeFilter ?? ""}
        onChange={e => onFilter(e.target.value || null)}
        style={{
          flex: 1, padding: "5px 8px", borderRadius: 7, fontSize: 11, fontWeight: 600,
          background: "var(--surface-2)", border: `1px solid ${activeFilter ? "var(--accent-border)" : "var(--border)"}`,
          color: activeFilter ? "var(--accent)" : "var(--text-2)",
          outline: "none", cursor: "pointer", fontFamily: "var(--font-body)",
          appearance: "none", WebkitAppearance: "none",
        }}
      >
        <option value="">All Industries ({items.length})</option>
        {industries.map(([ind, count]) => (
          <option key={ind} value={ind}>{ind} ({count})</option>
        ))}
      </select>
      {activeFilter && (
        <button
          onClick={() => onFilter(null)}
          style={{
            background: "none", border: "none", color: "var(--text-4)",
            cursor: "pointer", display: "flex", padding: 2, flexShrink: 0,
          }}
          title="Clear filter"
        >
          <X style={{ width: 12, height: 12 }} />
        </button>
      )}
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

  // Batch CMP — fetch for up to 100 visible stocks
  const priceSymbols = useMemo(
    () => filtered.slice(0, 100).map(i => i.symbol),
    [filtered],
  );
  const { data: prices = {} } = useBatchPrices(priceSymbols);

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
              cmp={prices[item.symbol] ?? null}
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
            <StockDetailPane item={selectedItem} watchlistName={selectedWl?.name} />
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
