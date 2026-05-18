import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Fuse from "fuse.js";
import { Search, Clock, TrendingUp, X, Command } from "lucide-react";
import { NSE_STOCKS, type NseStock } from "@/lib/nse-stocks";

// Fuse.js instance for fuzzy search across all NSE stocks
const fuse = new Fuse(NSE_STOCKS, {
  keys: [
    { name: "symbol", weight: 0.6 },
    { name: "name",   weight: 0.35 },
    { name: "sector", weight: 0.05 },
  ],
  threshold: 0.35,
  minMatchCharLength: 1,
  includeScore: true,
});

const POPULAR = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BAJFINANCE", "MARUTI", "TITAN", "WIPRO", "SBIN"];

const RECENT_KEY = "op-recent-searches";

function getRecent(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]"); } catch { return []; }
}
function addRecent(symbol: string): void {
  try {
    const prev = getRecent().filter(s => s !== symbol);
    localStorage.setItem(RECENT_KEY, JSON.stringify([symbol, ...prev].slice(0, 8)));
  } catch {}
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (symbol: string, name?: string) => void;
}

export function GlobalSearch({ open, onClose, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<NseStock[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [recent, setRecent] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIdx(0);
      setRecent(getRecent());
      setTimeout(() => inputRef.current?.focus(), 60);
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const hits = fuse.search(query.trim(), { limit: 12 });
    setResults(hits.map(h => h.item));
    setActiveIdx(0);
  }, [query]);

  const handleSelect = useCallback((stock: NseStock) => {
    addRecent(stock.symbol);
    setRecent(getRecent());
    onSelect(stock.symbol, stock.name);
    onClose();
  }, [onSelect, onClose]);

  const handleSelectSymbol = useCallback((sym: string) => {
    const stock = NSE_STOCKS.find(s => s.symbol === sym);
    if (stock) handleSelect(stock);
    else {
      addRecent(sym);
      onSelect(sym);
      onClose();
    }
  }, [handleSelect, onSelect, onClose]);

  // Keyboard nav
  useEffect(() => {
    if (!open) return;
    const items = results.length > 0 ? results : [];
    const total = items.length;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, total - 1)); return; }
      if (e.key === "ArrowUp")   { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); return; }
      if (e.key === "Enter" && items[activeIdx]) { handleSelect(items[activeIdx]); return; }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, results, activeIdx, handleSelect, onClose]);

  const showEmpty = query.length >= 1 && results.length === 0;
  const showRecent = !query && recent.length > 0;
  const showPopular = !query;

  const sectorColor: Record<string, string> = {
    IT: "var(--accent)", Banking: "#27AE60", Finance: "#F39C12",
    FMCG: "#FBBF24", Healthcare: "#E74C3C", Auto: "#FB923C",
    Energy: "#F97316", Metals: "#94A3B8", Materials: "#84CC16",
    Chemicals: "#2DD4BF", Industrials: "#60A5FA", Telecom: "#C084FC",
    Consumer: "#FB7185", Defence: "#F59E0B", "Real Estate": "var(--accent)",
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50"
            style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(6px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            className="fixed z-50 top-[12vh] left-1/2"
            style={{ width: "min(620px, 95vw)", transform: "translateX(-50%)" }}
            initial={{ opacity: 0, y: -20, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 500, damping: 40 }}
          >
            <div
              className="overflow-hidden"
              style={{
                background: "var(--surface)",
                border: "1px solid rgba(106,98,86,0.2)",
                borderRadius: 12,
                boxShadow: "0 0 0 1px rgba(106,98,86,0.08), 0 32px 80px rgba(0,0,0,0.2)",
              }}
            >
              {/* Input */}
              <div className="flex items-center gap-3 px-4 py-3.5" style={{ borderBottom: "1px solid var(--border)" }}>
                <Search style={{ width: 16, height: 16, color: "var(--accent)", flexShrink: 0 }} />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={e => setQuery(e.target.value.toUpperCase())}
                  placeholder="Search stocks — RELIANCE, HDFC, Infosys..."
                  className="flex-1 bg-transparent outline-none font-mono"
                  style={{ fontSize: "14px", color: "var(--text-1)", caretColor: "var(--accent)" }}
                />
                {query && (
                  <button onClick={() => setQuery("")} style={{ color: "var(--text-3)" }}
                    onMouseEnter={e => (e.currentTarget.style.color = "var(--text-1)")}
                    onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}>
                    <X style={{ width: 14, height: 14 }} />
                  </button>
                )}
                <kbd className="hidden sm:flex items-center gap-1 px-1.5 py-0.5 rounded"
                  style={{ fontSize: "10px", color: "var(--text-3)", background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  ESC
                </kbd>
              </div>

              {/* Results */}
              <div style={{ maxHeight: "60vh", overflowY: "auto" }}>
                {/* Search results */}
                {results.length > 0 && (
                  <div className="py-1">
                    {results.map((stock, i) => (
                      <motion.button
                        key={stock.symbol}
                        className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-all"
                        style={{
                          background: i === activeIdx ? "rgba(106,98,86,0.08)" : "transparent",
                          borderLeft: i === activeIdx ? "2px solid #3279F9" : "2px solid transparent",
                        }}
                        onMouseEnter={() => setActiveIdx(i)}
                        onClick={() => handleSelect(stock)}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.02 }}
                      >
                        <div
                          className="flex items-center justify-center w-8 h-8 rounded-lg shrink-0 font-mono font-bold"
                          style={{
                            background: `${sectorColor[stock.sector] ?? "var(--accent)"}15`,
                            color: sectorColor[stock.sector] ?? "var(--accent)",
                            fontSize: "9px",
                            letterSpacing: "0.05em",
                          }}
                        >
                          {stock.symbol.slice(0, 3)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold" style={{ fontSize: "13px", color: "var(--text-1)" }}>
                              {stock.symbol}
                            </span>
                            <span
                              className="px-1.5 py-0.5 rounded"
                              style={{ fontSize: "8px", color: sectorColor[stock.sector] ?? "var(--accent)",
                                background: `${sectorColor[stock.sector] ?? "var(--accent)"}15`,
                                border: `1px solid ${sectorColor[stock.sector] ?? "var(--accent)"}30`,
                                letterSpacing: "0.08em", fontWeight: 700 }}
                            >
                              {stock.sector}
                            </span>
                          </div>
                          <div className="truncate mt-0.5" style={{ fontSize: "11px", color: "#A0A0BC" }}>{stock.name}</div>
                        </div>
                        <span style={{ fontSize: "9px", color: "var(--text-4)" }}>NSE</span>
                      </motion.button>
                    ))}
                  </div>
                )}

                {/* No results */}
                {showEmpty && (
                  <div className="py-10 text-center">
                    <div style={{ fontSize: "24px", marginBottom: 8 }}>🔍</div>
                    <div style={{ fontSize: "12px", color: "var(--text-3)" }}>No stocks found for "{query}"</div>
                    <div style={{ fontSize: "10px", color: "var(--text-4)", marginTop: 4 }}>Try a different spelling or symbol</div>
                  </div>
                )}

                {/* Recent + Popular */}
                {showPopular && (
                  <div className="p-4 space-y-4">
                    {showRecent && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <Clock style={{ width: 11, height: 11, color: "var(--text-3)" }} />
                          <span style={{ fontSize: "10px", color: "var(--text-3)", letterSpacing: "0.1em", fontWeight: 700 }}>RECENT</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {recent.map(sym => (
                            <button
                              key={sym}
                              onClick={() => handleSelectSymbol(sym)}
                              className="font-mono font-semibold px-2.5 py-1 rounded-lg transition-all"
                              style={{ fontSize: "11px", background: "rgba(106,98,86,0.6)", color: "var(--text-1)",
                                border: "1px solid var(--border)" }}
                              onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(106,98,86,0.3)"; e.currentTarget.style.color = "var(--accent)"; }}
                              onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text-1)"; }}
                            >
                              {sym}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <TrendingUp style={{ width: 11, height: 11, color: "var(--text-3)" }} />
                        <span style={{ fontSize: "10px", color: "var(--text-3)", letterSpacing: "0.1em", fontWeight: 700 }}>POPULAR</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {POPULAR.map(sym => (
                          <button
                            key={sym}
                            onClick={() => handleSelectSymbol(sym)}
                            className="font-mono font-semibold px-2.5 py-1 rounded-lg transition-all"
                            style={{ fontSize: "11px", background: "rgba(106,98,86,0.06)", color: "var(--accent)",
                              border: "1px solid rgba(106,98,86,0.15)" }}
                            onMouseEnter={e => { e.currentTarget.style.background = "rgba(106,98,86,0.12)"; }}
                            onMouseLeave={e => { e.currentTarget.style.background = "rgba(106,98,86,0.06)"; }}
                          >
                            {sym}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div
                className="flex items-center justify-between px-4 py-2 shrink-0"
                style={{ borderTop: "1px solid var(--border)", background: "var(--surface-2)" }}
              >
                <div className="flex items-center gap-3" style={{ fontSize: "10px", color: "var(--text-4)" }}>
                  <span>↑↓ navigate</span>
                  <span>↵ select</span>
                  <span>ESC close</span>
                </div>
                <div className="flex items-center gap-1.5" style={{ fontSize: "10px", color: "var(--text-4)" }}>
                  <Command style={{ width: 10, height: 10 }} />
                  <span>K to open</span>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
