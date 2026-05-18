import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Send, Bot, User, Loader2, Sparkles } from "lucide-react";
import { api } from "@/api/client";

interface Message { role: "user" | "assistant"; content: string; sources?: string[]; }

const SUGGESTIONS = [
  "Analyse HDFC Bank Q4 results",
  "Latest FII/DII flows today",
  "Upcoming dividends this week",
  "Compare Infosys vs TCS valuation",
  "What are top gainers and why?",
];

function formatMessage(text: string) {
  const lines = text.split("\n");
  return lines.map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    const rendered = parts.map((part, j) =>
      part.startsWith("**") && part.endsWith("**")
        ? <strong key={j} style={{ color: "var(--text-1)", fontWeight: 700 }}>{part.slice(2, -2)}</strong>
        : part
    );
    const isListItem = line.startsWith("- ") || line.startsWith("• ");
    if (isListItem) {
      return (
        <div key={i} style={{ display: "flex", gap: 6, marginBottom: 3 }}>
          <span style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }}>•</span>
          <span>{rendered.map((p, _j) => typeof p === "string" ? p.slice(2) : p)}</span>
        </div>
      );
    }
    if (!line.trim()) return <div key={i} style={{ height: 6 }} />;
    return <div key={i} style={{ marginBottom: 2 }}>{rendered}</div>;
  });
}

export function ChatBot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{
        role: "assistant",
        content: "**Welcome to IQF Market Intelligence** ✦\n\nI'm your AI analyst for Indian markets. Ask me about:\n- Stock analysis & fundamentals\n- BSE/NSE filings interpretation\n- Corporate actions & dividends\n- FII/DII flows & market breadth\n- Quarterly results deep-dive\n\nWhat would you like to analyse?",
        sources: [],
      }]);
    }
  }, [open, messages.length]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 200);
  }, [open]);

  const send = async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || loading) return;
    setInput("");
    const userMsg: Message = { role: "user", content: msg };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);
    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      const res = await api.post<{ response: string; sources: string[]; symbol: string | null }>(
        "/chat/message",
        { message: msg, history }
      );
      setMessages(prev => [...prev, { role: "assistant", content: res.response, sources: res.sources ?? [] }]);
    } catch (err) {
      const isTimeout = String(err).includes("timeout") || String(err).includes("abort");
      setMessages(prev => [...prev, {
        role: "assistant",
        content: isTimeout
          ? "Request timed out — the AI is warming up. Please try again in a moment."
          : "Unable to reach the AI backend. Please try again.",
        sources: [],
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Floating button */}
      <motion.button
        onClick={() => setOpen(true)}
        style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 100,
          width: 52, height: 52, borderRadius: "50%",
          background: "linear-gradient(135deg, var(--accent), var(--amber))",
          border: "none", cursor: "pointer", display: open ? "none" : "flex",
          alignItems: "center", justifyContent: "center",
          boxShadow: "0 4px 24px rgba(106,98,86,0.5)",
        }}
        whileHover={{ scale: 1.1, boxShadow: "0 6px 32px rgba(106,98,86,0.7)" }}
        whileTap={{ scale: 0.95 }}
        title="AI Market Assistant"
      >
        <Sparkles style={{ width: 22, height: 22, color: "#fff" }} />
      </motion.button>

      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 400, damping: 32 }}
            style={{
              position: "fixed", bottom: 24, right: 24, zIndex: 100,
              width: "min(420px, calc(100vw - 32px))",
              height: "min(600px, calc(100vh - 48px))",
              display: "flex", flexDirection: "column",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 20,
              boxShadow: "0 24px 80px rgba(0,0,0,0.5), 0 0 0 1px var(--accent-border)",
              overflow: "hidden",
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderBottom: "1px solid var(--border)", background: "var(--surface-2)", flexShrink: 0 }}>
              <div style={{ width: 32, height: 32, borderRadius: 10, background: "linear-gradient(135deg, var(--accent), var(--amber))", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Sparkles style={{ width: 16, height: 16, color: "#fff" }} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: "var(--font-body)", fontSize: 13, fontWeight: 700, color: "var(--text-1)" }}>IQF Market Intelligence</div>
                <div style={{ fontFamily: "var(--font-body)", fontSize: 10, color: "var(--green)", display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--green)", display: "inline-block" }} />
                  AI Analyst · NSE · BSE · Filings
                </div>
              </div>
              <button onClick={() => setOpen(false)} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-3)", padding: 4, borderRadius: 8 }}>
                <X style={{ width: 16, height: 16 }} />
              </button>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
              {messages.map((m, i) => (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", flexDirection: m.role === "user" ? "row-reverse" : "row" }}>
                  <div style={{ width: 26, height: 26, borderRadius: "50%", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: m.role === "user" ? "var(--accent-dim)" : "linear-gradient(135deg, var(--accent), var(--amber))" }}>
                    {m.role === "user" ? <User style={{ width: 13, height: 13, color: "var(--accent)" }} /> : <Bot style={{ width: 13, height: 13, color: "#fff" }} />}
                  </div>
                  <div style={{ maxWidth: "80%", background: m.role === "user" ? "var(--accent-dim)" : "var(--surface-2)", border: `1px solid ${m.role === "user" ? "var(--accent-border)" : "var(--border)"}`, borderRadius: m.role === "user" ? "14px 4px 14px 14px" : "4px 14px 14px 14px", padding: "9px 12px", fontFamily: "var(--font-body)", fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.55 }}>
                    {formatMessage(m.content)}
                    {m.sources && m.sources.length > 0 && (
                      <div style={{ marginTop: 8, paddingTop: 6, borderTop: "1px solid var(--border)", display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {m.sources.map((s, j) => <span key={j} style={{ fontSize: 9, background: "var(--surface-3)", color: "var(--text-3)", padding: "1px 6px", borderRadius: 4, fontWeight: 600 }}>{s}</span>)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <div style={{ width: 26, height: 26, borderRadius: "50%", background: "linear-gradient(135deg, var(--accent), var(--amber))", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <Bot style={{ width: 13, height: 13, color: "#fff" }} />
                  </div>
                  <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "4px 14px 14px 14px", padding: "10px 14px", display: "flex", gap: 4, alignItems: "center" }}>
                    {[0, 1, 2].map(i => (
                      <motion.span
                        key={i}
                        style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--accent)", display: "block" }}
                        animate={{ opacity: [0.3, 1, 0.3] }}
                        transition={{ duration: 1, delay: i * 0.2, repeat: Infinity }}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Suggestions (only when no user messages yet) */}
            {messages.length <= 1 && (
              <div style={{ padding: "6px 14px", display: "flex", gap: 5, flexWrap: "wrap", borderTop: "1px solid var(--border-2)", flexShrink: 0 }}>
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    style={{ fontSize: 10.5, padding: "4px 10px", borderRadius: 99, background: "var(--accent-dim)", border: "1px solid var(--accent-border)", color: "var(--accent)", cursor: "pointer", fontFamily: "var(--font-body)", fontWeight: 600, transition: "all 120ms" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "var(--accent)"; e.currentTarget.style.color = "#fff"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "var(--accent-dim)"; e.currentTarget.style.color = "var(--accent)"; }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* Input */}
            <div style={{ padding: "10px 12px", borderTop: "1px solid var(--border)", display: "flex", gap: 8, alignItems: "center", flexShrink: 0, background: "var(--surface-2)" }}>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
                placeholder="Ask about any stock, filing, result..."
                style={{ flex: 1, background: "var(--surface-3)", border: "1px solid var(--border)", borderRadius: 10, padding: "8px 12px", color: "var(--text-1)", fontFamily: "var(--font-body)", fontSize: 12.5, outline: "none" }}
                onFocus={e => (e.currentTarget.style.borderColor = "var(--accent-border)")}
                onBlur={e => (e.currentTarget.style.borderColor = "var(--border)")}
              />
              <button
                onClick={() => send()}
                disabled={!input.trim() || loading}
                style={{ width: 36, height: 36, borderRadius: 10, background: input.trim() && !loading ? "var(--accent)" : "var(--surface-3)", border: "1px solid var(--border)", cursor: input.trim() && !loading ? "pointer" : "default", display: "flex", alignItems: "center", justifyContent: "center", transition: "all 150ms" }}
              >
                {loading
                  ? <Loader2 style={{ width: 15, height: 15, color: "var(--text-3)", animation: "spin 1s linear infinite" }} />
                  : <Send style={{ width: 15, height: 15, color: input.trim() ? "#fff" : "var(--text-3)" }} />
                }
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
