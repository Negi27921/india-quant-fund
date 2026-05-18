import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ExternalLink } from "lucide-react";

interface ChartDrawerProps {
  symbol: string | null;
  name?: string;
  onClose: () => void;
}

const TV_INDEX_MAP: Record<string, string> = {
  "^NSEI": "NSE:NIFTY", "^NSEBANK": "NSE:BANKNIFTY",
  "^BSESN": "BSE:SENSEX", "^NSEMDCP50": "NSE:MIDCPNIFTY", "^CNXIT": "NSE:NIFTYIT",
};

function toTVSymbol(raw: string): string {
  const clean = raw.replace(".NS", "").replace(".BO", "").toUpperCase();
  return TV_INDEX_MAP[clean] ?? TV_INDEX_MAP["^" + clean] ?? `NSE:${clean}`;
}

const TIMEFRAMES = [
  { label: "5m",  interval: "5"  },
  { label: "15m", interval: "15" },
  { label: "1h",  interval: "60" },
  { label: "1D",  interval: "D"  },
  { label: "1W",  interval: "W"  },
  { label: "1M",  interval: "M"  },
] as const;

type TF = typeof TIMEFRAMES[number];

export function ChartDrawer({ symbol, name, onClose }: ChartDrawerProps) {
  const [tf, setTf] = useState<TF>(TIMEFRAMES[3]);

  const cleanSymbol = symbol ? symbol.replace(".NS", "").replace(".BO", "").toUpperCase() : "";
  const displaySymbol = cleanSymbol.replace(/^\^/, "");
  const tvSymbol = symbol ? toTVSymbol(symbol) : "";

  // Detect theme
  const isDark = document.documentElement.dataset.theme === "dark";
  const theme = isDark ? "dark" : "light";

  const iframeUrl = tvSymbol
    ? `https://www.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tvSymbol)}&interval=${tf.interval}&theme=${theme}&style=1&timezone=Asia%2FKolkata&withdateranges=1&showpopupbutton=1&locale=en&hide_side_toolbar=0`
    : "";

  return (
    <AnimatePresence>
      {symbol && (
        <>
          <motion.div
            className="fixed inset-0 z-40"
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          <motion.div
            className="fixed top-0 right-0 bottom-0 z-50 flex flex-col"
            style={{
              width: "min(820px, 90vw)",
              background: "var(--surface)",
              borderLeft: "1px solid var(--border)",
              boxShadow: "var(--shadow-lg)",
            }}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 340, damping: 38 }}
          >
            {/* Header */}
            <div
              className="flex items-center gap-3 px-5 py-3 shrink-0"
              style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3">
                  <span style={{ fontSize: "18px", fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-1)", letterSpacing: "0.04em" }}>
                    {displaySymbol}
                  </span>
                  <span style={{ fontSize: "11px", fontFamily: "var(--font-mono)", color: "var(--text-3)", background: "var(--surface-3)", padding: "2px 8px", borderRadius: 6 }}>
                    {tvSymbol}
                  </span>
                </div>
                {name && <div style={{ fontSize: "11px", color: "var(--text-3)", marginTop: 2, fontFamily: "var(--font-body)" }}>{name}</div>}
              </div>

              <div className="flex items-center gap-1">
                <a
                  href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 rounded flex items-center gap-1 transition-colors"
                  style={{ fontSize: "9px", color: "var(--text-3)", letterSpacing: "0.08em", textDecoration: "none" }}
                  onMouseEnter={e => (e.currentTarget.style.color = "var(--accent)")}
                  onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
                  title="Open in TradingView"
                >
                  <ExternalLink style={{ width: 12, height: 12 }} />
                  <span className="hidden sm:inline">TV</span>
                </a>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-lg transition-colors"
                  style={{ color: "var(--text-3)", background: "none", border: "none", cursor: "pointer" }}
                  onMouseEnter={e => (e.currentTarget.style.color = "var(--text-1)")}
                  onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
                >
                  <X style={{ width: 16, height: 16 }} />
                </button>
              </div>
            </div>

            {/* Timeframe selector */}
            <div
              className="flex items-center gap-1 px-4 py-2 shrink-0"
              style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
            >
              {TIMEFRAMES.map(t => (
                <button
                  key={t.label}
                  onClick={() => setTf(t)}
                  style={{
                    fontSize: "11px",
                    fontFamily: "var(--font-mono)",
                    fontWeight: tf.label === t.label ? 700 : 500,
                    padding: "4px 12px",
                    borderRadius: 6,
                    background: tf.label === t.label ? "var(--accent-dim)" : "transparent",
                    color: tf.label === t.label ? "var(--accent)" : "var(--text-3)",
                    border: `1px solid ${tf.label === t.label ? "var(--accent-border)" : "transparent"}`,
                    cursor: "pointer",
                    transition: "all 150ms",
                  }}
                  onMouseEnter={e => { if (tf.label !== t.label) { e.currentTarget.style.color = "var(--text-1)"; e.currentTarget.style.background = "var(--surface-3)"; } }}
                  onMouseLeave={e => { if (tf.label !== t.label) { e.currentTarget.style.color = "var(--text-3)"; e.currentTarget.style.background = "transparent"; } }}
                >
                  {t.label}
                </button>
              ))}
              <div className="flex-1" />
              <span style={{ fontSize: "9px", color: "var(--text-4)", letterSpacing: "0.1em", fontFamily: "var(--font-body)" }}>NSE · TRADINGVIEW</span>
            </div>

            {/* TradingView chart iframe */}
            <div className="flex-1 relative overflow-hidden">
              {iframeUrl && (
                <iframe
                  key={tvSymbol + tf.label}
                  src={iframeUrl}
                  width="100%"
                  height="100%"
                  frameBorder="0"
                  allowTransparency
                  title={`${displaySymbol} chart`}
                  style={{ display: "block", border: "none" }}
                />
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
