import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Search, Plus, TrendingUp, Zap } from "lucide-react";
import { searchNseStocks, type NseStock } from "@/lib/nse-stocks";
import { useAddPaperPosition, useAddLivePosition } from "@/api/pnl-queries";

interface Props {
  open: boolean;
  onClose: () => void;
  mode?: "paper" | "live";
}

const FIELD: React.CSSProperties = {
  width: "100%",
  background: "#0A0A12",
  border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: 8,
  padding: "8px 12px",
  color: "#FFFFFF",
  fontSize: 12,
  fontFamily: "JetBrains Mono, monospace",
  outline: "none",
  transition: "border-color 150ms",
};

export function AddPositionModal({ open, onClose, mode = "paper" }: Props) {
  const [query, setQuery] = useState("");
  const [selectedStock, setSelectedStock] = useState<NseStock | null>(null);
  const [suggestions, setSuggestions] = useState<NseStock[]>([]);
  const [showSug, setShowSug] = useState(false);
  const [quantity, setQuantity] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [buyDate, setBuyDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const paperMutation = useAddPaperPosition();
  const liveMutation = useAddLivePosition();
  const addMutation = mode === "live" ? liveMutation : paperMutation;

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 80);
      setQuery(""); setSelectedStock(null); setQuantity("");
      setBuyPrice(""); setNotes(""); setError("");
      setSuggestions([]); setShowSug(false);
    }
  }, [open]);

  const onQueryChange = (v: string) => {
    setQuery(v);
    setSelectedStock(null);
    if (v.length >= 1) {
      // Search by both symbol AND name — catches "IdeaForge" → IDEAFORGE
      const results = searchNseStocks(v, 8);
      setSuggestions(results);
      setShowSug(results.length > 0);
    } else {
      setSuggestions([]);
      setShowSug(false);
    }
  };

  const selectStock = (s: NseStock) => {
    setSelectedStock(s);
    setQuery(`${s.symbol} — ${s.name}`);
    setSuggestions([]);
    setShowSug(false);
  };

  const submit = async () => {
    setError("");
    const sym = selectedStock?.symbol ?? query.split("—")[0].trim().toUpperCase();
    const qty = parseInt(quantity, 10);
    const price = parseFloat(buyPrice);
    if (!sym) return setError("Search and select a stock");
    if (!qty || qty <= 0) return setError("Enter a valid quantity");
    if (!price || price <= 0) return setError("Enter a valid buy price");
    if (!buyDate) return setError("Select a buy date");
    try {
      await addMutation.mutateAsync({
        ticker: sym,
        quantity: qty,
        avg_buy_price: price,
        buy_date: buyDate,
        name: selectedStock?.name || sym,
        sector: selectedStock?.sector || "",
        notes,
      });
      onClose();
    } catch {
      setError("Failed to add position. Check if the API is running.");
    }
  };

  const totalCost = quantity && buyPrice
    ? (parseInt(quantity, 10) * parseFloat(buyPrice)).toLocaleString("en-IN", { maximumFractionDigits: 2 })
    : null;

  const isLive = mode === "live";

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40"
            style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(6px)" }}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            className="fixed z-50 top-1/2 left-1/2"
            style={{ transform: "translate(-50%, -50%)", width: "min(500px, 96vw)" }}
            initial={{ opacity: 0, scale: 0.92, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 20 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
          >
            <div style={{
              background: "#000000",
              border: `1px solid ${isLive ? "rgba(6,214,160,0.25)" : "rgba(91,127,255,0.25)"}`,
              borderRadius: 12,
              boxShadow: isLive
                ? "0 0 60px rgba(6,214,160,0.1), 0 24px 80px rgba(0,0,0,0.9)"
                : "0 0 60px rgba(91,127,255,0.1), 0 24px 80px rgba(0,0,0,0.9)",
              overflow: "hidden",
            }}>
              {/* Header */}
              <div style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "14px 18px",
                borderBottom: "1px solid rgba(255,255,255,0.06)",
                background: "rgba(13,22,36,0.8)",
              }}>
                {isLive
                  ? <Zap style={{ width: 13, height: 13, color: "#06D6A0" }} />
                  : <TrendingUp style={{ width: 13, height: 13, color: "#5B7FFF" }} />
                }
                <span style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: "0.14em",
                  color: isLive ? "#06D6A0" : "#5B7FFF",
                  fontFamily: "Space Grotesk, sans-serif",
                }}>
                  {isLive ? "ADD LIVE POSITION" : "ADD PAPER POSITION"}
                </span>
                <div style={{ flex: 1 }} />
                <button onClick={onClose} style={{ color: "#5C5C78", background: "none", border: "none", cursor: "pointer", padding: 4, borderRadius: 6 }}
                  onMouseEnter={e => (e.currentTarget.style.color = "#FFFFFF")}
                  onMouseLeave={e => (e.currentTarget.style.color = "#5C5C78")}>
                  <X style={{ width: 14, height: 14 }} />
                </button>
              </div>

              <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
                {/* Stock search */}
                <div>
                  <label style={{ fontSize: 10, fontWeight: 600, color: "#5C5C78", letterSpacing: "0.1em", display: "block", marginBottom: 6, fontFamily: "Space Grotesk, sans-serif" }}>
                    SEARCH STOCK — type symbol, name, or company
                  </label>
                  <div style={{ position: "relative" }}>
                    <Search style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", width: 12, height: 12, color: "#5C5C78", pointerEvents: "none" }} />
                    <input
                      ref={inputRef}
                      value={query}
                      onChange={e => onQueryChange(e.target.value)}
                      onFocus={() => suggestions.length > 0 && setShowSug(true)}
                      onKeyDown={e => e.key === "Escape" && setShowSug(false)}
                      placeholder='e.g. "IdeaForge", "RELIANCE", "Infosys"...'
                      style={{ ...FIELD, paddingLeft: 32 }}

                    />
                    <AnimatePresence>
                      {showSug && suggestions.length > 0 && (
                        <motion.div
                          initial={{ opacity: 0, y: -4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0 }}
                          style={{
                            position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 60,
                            background: "#000000", border: "1px solid rgba(91,127,255,0.2)",
                            borderRadius: 8, overflow: "hidden", boxShadow: "0 8px 32px rgba(0,0,0,0.9)",
                          }}
                        >
                          {suggestions.map(s => (
                            <button
                              key={s.symbol}
                              style={{
                                width: "100%", display: "flex", alignItems: "center", gap: 10,
                                padding: "9px 12px", background: "transparent", border: "none",
                                borderBottom: "1px solid rgba(255,255,255,0.06)", cursor: "pointer", textAlign: "left",
                              }}
                              onMouseEnter={e => (e.currentTarget.style.background = "rgba(91,127,255,0.07)")}
                              onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                              onMouseDown={ev => { ev.preventDefault(); selectStock(s); }}
                            >
                              <span style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 700, fontSize: 11, color: "#5B7FFF", minWidth: 90 }}>{s.symbol}</span>
                              <span style={{ fontSize: 11, color: "#A0A0BC", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                              <span style={{ fontSize: 9, color: "#5C5C78", background: "rgba(91,127,255,0.6)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10, padding: "1px 7px", whiteSpace: "nowrap" }}>{s.sector}</span>
                            </button>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                  {selectedStock && (
                    <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#06D6A0", display: "inline-block" }} />
                      <span style={{ fontSize: 11, color: "#A0A0BC" }}>{selectedStock.name}</span>
                      <span style={{ fontSize: 9, background: "rgba(91,127,255,0.08)", border: "1px solid rgba(91,127,255,0.15)", borderRadius: 10, padding: "1px 7px", color: "#5B7FFF" }}>{selectedStock.sector}</span>
                    </div>
                  )}
                </div>

                {/* Qty + Price */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 10, fontWeight: 600, color: "#5C5C78", letterSpacing: "0.1em", display: "block", marginBottom: 6, fontFamily: "Space Grotesk, sans-serif" }}>QUANTITY</label>
                    <input type="number" min="1" value={quantity} onChange={e => setQuantity(e.target.value)}
                      placeholder="e.g. 10" style={FIELD}
                      onFocus={e => (e.currentTarget.style.borderColor = "#5B7FFF")}
                      onBlur={e => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)")} />
                  </div>
                  <div>
                    <label style={{ fontSize: 10, fontWeight: 600, color: "#5C5C78", letterSpacing: "0.1em", display: "block", marginBottom: 6, fontFamily: "Space Grotesk, sans-serif" }}>BUY PRICE (₹)</label>
                    <input type="number" min="0.01" step="0.01" value={buyPrice} onChange={e => setBuyPrice(e.target.value)}
                      placeholder="e.g. 2850.00" style={FIELD}
                      onFocus={e => (e.currentTarget.style.borderColor = "#5B7FFF")}
                      onBlur={e => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)")} />
                  </div>
                </div>

                {/* Date + Notes */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 10, fontWeight: 600, color: "#5C5C78", letterSpacing: "0.1em", display: "block", marginBottom: 6, fontFamily: "Space Grotesk, sans-serif" }}>BUY DATE</label>
                    <input type="date" value={buyDate} max={new Date().toISOString().slice(0, 10)}
                      onChange={e => setBuyDate(e.target.value)} style={{ ...FIELD, colorScheme: "dark" }}
                      onFocus={e => (e.currentTarget.style.borderColor = "#5B7FFF")}
                      onBlur={e => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)")} />
                  </div>
                  <div>
                    <label style={{ fontSize: 10, fontWeight: 600, color: "#5C5C78", letterSpacing: "0.1em", display: "block", marginBottom: 6, fontFamily: "Space Grotesk, sans-serif" }}>NOTES</label>
                    <input value={notes} onChange={e => setNotes(e.target.value)}
                      placeholder="Target, SL, thesis..." style={FIELD}
                      onFocus={e => (e.currentTarget.style.borderColor = "#5B7FFF")}
                      onBlur={e => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)")} />
                  </div>
                </div>

                {/* Total cost */}
                {totalCost && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "10px 14px", borderRadius: 8,
                      background: "rgba(91,127,255,0.05)", border: "1px solid rgba(91,127,255,0.15)",
                    }}
                  >
                    <span style={{ fontSize: 10, color: "#5C5C78", letterSpacing: "0.1em", fontFamily: "Space Grotesk, sans-serif" }}>TOTAL CAPITAL DEPLOYED</span>
                    <span style={{ fontFamily: "JetBrains Mono, monospace", fontWeight: 700, fontSize: 14, color: "#5B7FFF" }}>₹{totalCost}</span>
                  </motion.div>
                )}

                {/* Error */}
                {error && (
                  <div style={{ fontSize: 11, color: "#FF4757", background: "rgba(255,71,87,0.08)", border: "1px solid rgba(255,71,87,0.2)", borderRadius: 6, padding: "8px 12px" }}>
                    {error}
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: "flex", gap: 10, paddingTop: 4 }}>
                  <button
                    onClick={onClose}
                    style={{
                      flex: 1, padding: "9px 0", borderRadius: 8, fontSize: 12,
                      background: "rgba(91,127,255,0.4)", border: "1px solid rgba(255,255,255,0.06)",
                      color: "#A0A0BC", cursor: "pointer", fontFamily: "Space Grotesk, sans-serif", fontWeight: 600,
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = "rgba(91,127,255,0.8)")}
                    onMouseLeave={e => (e.currentTarget.style.background = "rgba(91,127,255,0.4)")}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submit}
                    disabled={addMutation.isPending}
                    style={{
                      flex: 2, padding: "9px 0", borderRadius: 8, fontSize: 12,
                      background: isLive
                        ? "linear-gradient(135deg, rgba(6,214,160,0.2), rgba(6,214,160,0.05))"
                        : "linear-gradient(135deg, rgba(91,127,255,0.2), rgba(91,127,255,0.05))",
                      border: isLive ? "1px solid rgba(6,214,160,0.4)" : "1px solid rgba(91,127,255,0.4)",
                      color: isLive ? "#06D6A0" : "#5B7FFF",
                      cursor: addMutation.isPending ? "not-allowed" : "pointer",
                      fontFamily: "Space Grotesk, sans-serif", fontWeight: 700,
                      display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                      opacity: addMutation.isPending ? 0.6 : 1,
                    }}
                    onMouseEnter={e => !addMutation.isPending && (e.currentTarget.style.opacity = "0.85")}
                    onMouseLeave={e => (e.currentTarget.style.opacity = addMutation.isPending ? "0.6" : "1")}
                  >
                    {addMutation.isPending ? (
                      <span>Adding...</span>
                    ) : (
                      <>
                        <Plus style={{ width: 13, height: 13 }} />
                        <span>Add {isLive ? "Live" : "Paper"} Position</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
