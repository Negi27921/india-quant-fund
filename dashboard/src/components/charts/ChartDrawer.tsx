import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { createChart, ColorType, CandlestickStyleOptions, DeepPartial } from "lightweight-charts";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

interface OHLCVPoint {
  time: string | number;
  open: number; high: number; low: number; close: number; volume: number;
}

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

function toYFTicker(raw: string): string {
  if (!raw) return "";
  const s = raw.trim().toUpperCase();
  if (s.startsWith("^")) return s;
  if (s.endsWith(".NS") || s.endsWith(".BO")) return s;
  return `${s.replace(/\.(NS|BO)$/i, "")}.NS`;
}

const TIMEFRAMES = [
  { label: "5m",  period: "5d",  interval: "5m"  },
  { label: "15m", period: "5d",  interval: "15m" },
  { label: "1h",  period: "30d", interval: "1h"  },
  { label: "1D",  period: "3mo", interval: "1d"  },
  { label: "1W",  period: "1y",  interval: "1wk" },
  { label: "1M",  period: "2y",  interval: "1mo" },
] as const;

type TF = typeof TIMEFRAMES[number];

// ── Inner chart component ──────────────────────────────────────────────────────
function StockChart({ yfTicker, period, interval }: { yfTicker: string; period: string; interval: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, error, refetch } = useQuery<OHLCVPoint[]>({
    queryKey: ["chart-ohlcv", yfTicker, period, interval],
    queryFn: () =>
      api.get<OHLCVPoint[]>(`/market/history/${encodeURIComponent(yfTicker)}?period=${period}&interval=${interval}`),
    staleTime: 2 * 60_000,
    retry: 1,
    enabled: !!yfTicker,
  });

  useEffect(() => {
    if (!containerRef.current || !data || data.length < 2) return;

    const isDark = document.documentElement.dataset.theme !== "light";
    const textColor   = isDark ? "rgba(255,255,255,0.45)" : "rgba(0,0,0,0.5)";
    const gridColor   = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)";
    const bgColor     = isDark ? "#08080f" : "#ffffff";

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      rightPriceScale: {
        borderColor: gridColor,
        textColor,
        scaleMargins: { top: 0.06, bottom: 0.14 },
      },
      timeScale: {
        borderColor: gridColor,
        fixLeftEdge: true,
        fixRightEdge: true,
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        horzLine: { color: "rgba(167,139,250,0.5)", width: 1, style: 2 },
        vertLine: { color: "rgba(167,139,250,0.5)", width: 1, style: 2 },
      },
      handleScroll: true,
      handleScale: true,
    });

    const candleOpts: DeepPartial<CandlestickStyleOptions> = {
      upColor:         "#10b981",
      downColor:       "#f87171",
      borderUpColor:   "#10b981",
      borderDownColor: "#f87171",
      wickUpColor:     "#10b981",
      wickDownColor:   "#f87171",
    };
    const candleSeries = chart.addCandlestickSeries(candleOpts);

    type CandleTick = { time: string | number; open: number; high: number; low: number; close: number };
    const candleData: CandleTick[] = data.map(d => ({
      time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
    }));
    candleSeries.setData(candleData as Parameters<typeof candleSeries.setData>[0]);

    // Volume bars on separate scale
    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      borderVisible: false,
    });
    type VolTick = { time: string | number; value: number; color: string };
    const volData: VolTick[] = data.map(d => ({
      time: d.time,
      value: d.volume,
      color: d.close >= d.open ? "rgba(16,185,129,0.28)" : "rgba(248,113,113,0.28)",
    }));
    volSeries.setData(volData as Parameters<typeof volSeries.setData>[0]);

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    });
    ro.observe(containerRef.current);

    return () => { ro.disconnect(); chart.remove(); };
  }, [data]);

  if (isLoading) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, background: "#08080f" }}>
        <Loader2 style={{ width: 32, height: 32, color: "#a78bfa", animation: "spin 1s linear infinite" }} />
        <span style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", fontFamily: "var(--font-body)", letterSpacing: "0.04em" }}>
          Fetching OHLCV data…
        </span>
      </div>
    );
  }

  if (error || !data || data.length < 2) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, background: "#08080f" }}>
        <span style={{ fontSize: 36 }}>📊</span>
        <span style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", fontFamily: "var(--font-body)", textAlign: "center", maxWidth: 300 }}>
          Chart data unavailable for this timeframe. Try a higher interval (1D, 1W) or check the symbol.
        </span>
        <button
          onClick={() => refetch()}
          style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "8px 18px", borderRadius: 8, cursor: "pointer",
            background: "rgba(167,139,250,0.15)", border: "1px solid rgba(167,139,250,0.3)",
            color: "#a78bfa", fontSize: 12, fontWeight: 600, fontFamily: "var(--font-body)",
          }}
        >
          <RefreshCw style={{ width: 12, height: 12 }} /> Retry
        </button>
      </div>
    );
  }

  return <div ref={containerRef} style={{ flex: 1, width: "100%", minHeight: 0 }} />;
}

// ── Drawer ─────────────────────────────────────────────────────────────────────
export function ChartDrawer({ symbol, name, onClose }: ChartDrawerProps) {
  const [tf, setTf] = useState<TF>(TIMEFRAMES[3]); // 1D default

  const cleanSymbol   = symbol ? symbol.replace(".NS", "").replace(".BO", "").replace(/^\^/, "").toUpperCase() : "";
  const displaySymbol = cleanSymbol;
  const tvSymbol      = symbol ? toTVSymbol(symbol) : "";
  const yfTicker      = symbol ? toYFTicker(symbol) : "";

  return (
    <AnimatePresence>
      {symbol && (
        <>
          {/* Overlay */}
          <motion.div
            className="fixed inset-0 z-40"
            style={{ background: "rgba(0,0,0,0.72)", backdropFilter: "blur(4px)" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Drawer panel */}
          <motion.div
            className="fixed top-0 right-0 bottom-0 z-50 flex flex-col"
            style={{
              width: "min(900px, 92vw)",
              background: "#08080f",
              borderLeft: "1px solid rgba(167,139,250,0.22)",
              boxShadow: "-24px 0 80px rgba(0,0,0,0.75), -1px 0 0 rgba(167,139,250,0.15)",
            }}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 340, damping: 38 }}
          >
            {/* Header */}
            <div style={{
              display: "flex", alignItems: "center", gap: 12, padding: "14px 18px", flexShrink: 0,
              borderBottom: "1px solid rgba(167,139,250,0.18)",
              background: "rgba(10, 8, 22, 0.98)",
            }}>
              {/* Symbol avatar */}
              <div style={{
                width: 40, height: 40, borderRadius: 11, flexShrink: 0,
                background: "linear-gradient(135deg, rgba(167,139,250,0.18), rgba(96,165,250,0.1))",
                border: "1px solid rgba(167,139,250,0.3)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 800, color: "#a78bfa", letterSpacing: "0.02em" }}>
                  {displaySymbol.slice(0, 3)}
                </span>
              </div>

              {/* Symbol info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                  <span style={{ fontSize: 18, fontFamily: "var(--font-mono)", fontWeight: 800, color: "#f5f5f7", letterSpacing: "0.02em" }}>
                    {displaySymbol}
                  </span>
                  <span style={{
                    fontSize: 9.5, fontFamily: "var(--font-mono)", color: "#a78bfa",
                    background: "rgba(167,139,250,0.12)", padding: "2px 7px", borderRadius: 5,
                    border: "1px solid rgba(167,139,250,0.25)",
                  }}>
                    {yfTicker}
                  </span>
                </div>
                {name && (
                  <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", fontFamily: "var(--font-body)" }}>{name}</div>
                )}
              </div>

              {/* Actions */}
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <a
                  href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`}
                  target="_blank" rel="noopener noreferrer"
                  style={{
                    display: "flex", alignItems: "center", gap: 4,
                    padding: "5px 10px", borderRadius: 7,
                    background: "rgba(167,139,250,0.1)", border: "1px solid rgba(167,139,250,0.25)",
                    color: "#a78bfa", fontSize: 10, fontWeight: 600,
                    fontFamily: "var(--font-body)", textDecoration: "none",
                    transition: "background 150ms",
                  }}
                  title="Open in TradingView"
                  onMouseEnter={e => (e.currentTarget.style.background = "rgba(167,139,250,0.2)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "rgba(167,139,250,0.1)")}
                >
                  <ExternalLink style={{ width: 11, height: 11 }} />
                  <span>TradingView</span>
                </a>
                <button
                  onClick={onClose}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "center",
                    width: 32, height: 32, borderRadius: 8,
                    background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                    color: "rgba(255,255,255,0.5)", cursor: "pointer", transition: "all 150ms",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background = "rgba(248,113,113,0.15)"; e.currentTarget.style.color = "#f87171"; e.currentTarget.style.borderColor = "rgba(248,113,113,0.3)"; }}
                  onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = "rgba(255,255,255,0.5)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; }}
                >
                  <X style={{ width: 15, height: 15 }} />
                </button>
              </div>
            </div>

            {/* Timeframe selector */}
            <div style={{
              display: "flex", alignItems: "center", gap: 4, padding: "8px 14px", flexShrink: 0,
              borderBottom: "1px solid rgba(255,255,255,0.07)",
              background: "rgba(12,10,26,0.6)",
            }}>
              {TIMEFRAMES.map(t => (
                <button
                  key={t.label}
                  onClick={() => setTf(t)}
                  style={{
                    fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: tf.label === t.label ? 700 : 500,
                    padding: "4px 12px", borderRadius: 6,
                    background: tf.label === t.label ? "rgba(167,139,250,0.18)" : "transparent",
                    color: tf.label === t.label ? "#a78bfa" : "rgba(255,255,255,0.35)",
                    border: `1px solid ${tf.label === t.label ? "rgba(167,139,250,0.4)" : "transparent"}`,
                    cursor: "pointer", transition: "all 150ms",
                  }}
                  onMouseEnter={e => { if (tf.label !== t.label) { e.currentTarget.style.color = "rgba(255,255,255,0.7)"; e.currentTarget.style.background = "rgba(255,255,255,0.07)"; } }}
                  onMouseLeave={e => { if (tf.label !== t.label) { e.currentTarget.style.color = "rgba(255,255,255,0.35)"; e.currentTarget.style.background = "transparent"; } }}
                >
                  {t.label}
                </button>
              ))}
              <div style={{ flex: 1 }} />
              <span style={{ fontSize: 9, color: "rgba(255,255,255,0.2)", letterSpacing: "0.1em", fontFamily: "var(--font-body)" }}>
                NSE · OHLCV DATA
              </span>
            </div>

            {/* Chart area */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
              <StockChart
                key={`${yfTicker}-${tf.label}`}
                yfTicker={yfTicker}
                period={tf.period}
                interval={tf.interval}
              />
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
