import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
} from "lightweight-charts";
import { X, ExternalLink, RefreshCw, TrendingUp, TrendingDown } from "lucide-react";
import { API_BASE } from "@/lib/constants";

interface ChartDrawerProps {
  symbol: string | null;
  name?: string;
  onClose: () => void;
}

const TIMEFRAMES = [
  { label: "5m",  period: "1d",  interval: "5m" },
  { label: "15m", period: "5d",  interval: "15m" },
  { label: "1h",  period: "1mo", interval: "1h" },
  { label: "1D",  period: "1y",  interval: "1d" },
  { label: "1W",  period: "5y",  interval: "1wk" },
  { label: "1M",  period: "max", interval: "1mo" },
] as const;

type TF = typeof TIMEFRAMES[number];

interface OHLCV {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function fmtPrice(v: number): string {
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtVol(v: number): string {
  if (v >= 1e7) return (v / 1e7).toFixed(2) + " Cr";
  if (v >= 1e5) return (v / 1e5).toFixed(2) + " L";
  return v.toLocaleString("en-IN");
}

export function ChartDrawer({ symbol, name, onClose }: ChartDrawerProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const [tf, setTf] = useState<TF>(TIMEFRAMES[3]);
  const [data, setData] = useState<OHLCV[]>([]);
  const [loading, setLoading] = useState(false);
  const [hoverData, setHoverData] = useState<Partial<OHLCV> | null>(null);
  const cleanSymbol = symbol ? symbol.replace(".NS", "").replace(".BO", "").toUpperCase() : "";
  const yfSymbol = cleanSymbol ? `${cleanSymbol}.NS` : "";

  const fetchData = useCallback(async () => {
    if (!yfSymbol) return;
    setLoading(true);
    try {
      const url = `${API_BASE}/market/history/${encodeURIComponent(yfSymbol)}?period=${tf.period}&interval=${tf.interval}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("fetch failed");
      const json: OHLCV[] = await res.json();
      setData(json.filter(d => d.close > 0));
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [yfSymbol, tf]);

  useEffect(() => {
    if (symbol) fetchData();
  }, [symbol, fetchData]);

  useEffect(() => {
    if (!chartContainerRef.current) return;
    const el = chartContainerRef.current;

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "#000000" },
        textColor: "var(--text-3)",
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: "rgba(50,121,249,0.06)", style: LineStyle.Dotted },
        horzLines: { color: "rgba(50,121,249,0.06)", style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(50,121,249,0.5)", labelBackgroundColor: "var(--surface)" },
        horzLine: { color: "rgba(50,121,249,0.5)", labelBackgroundColor: "var(--surface)" },
      },
      rightPriceScale: {
        borderColor: "var(--border)",
        textColor: "var(--text-3)",
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: "var(--border)",
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: number | string) => {
          if (typeof time === "number") {
            return new Date(time * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
          }
          return String(time).slice(5);
        },
      },
      handleScale: { axisPressedMouseMove: true },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#27AE60",
      downColor: "#E74C3C",
      borderUpColor: "#27AE60",
      borderDownColor: "#E74C3C",
      wickUpColor: "#27AE60",
      wickDownColor: "#E74C3C",
    });

    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      color: "rgba(50,121,249,0.3)",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chart.subscribeCrosshairMove((param) => {
      if (param.time) {
        const c = param.seriesData.get(candleSeries) as CandlestickData | undefined;
        const v = param.seriesData.get(volSeries) as HistogramData | undefined;
        if (c) setHoverData({ time: c.time as string | number, open: c.open, high: c.high, low: c.low, close: c.close, volume: (v as any)?.value ?? 0 });
      } else {
        setHoverData(null);
      }
    });

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    });
    ro.observe(el);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volSeriesRef.current = volSeries;

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candleSeriesRef.current || !volSeriesRef.current || data.length === 0) return;
    const candleData: CandlestickData[] = data.map(d => ({
      time: d.time as any,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));
    const volData: HistogramData[] = data.map(d => ({
      time: d.time as any,
      value: d.volume,
      color: d.close >= d.open ? "rgba(39,174,96,0.35)" : "rgba(231,76,60,0.3)",
    }));
    candleSeriesRef.current.setData(candleData);
    volSeriesRef.current.setData(volData);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  const last = data[data.length - 1];
  const prev = data[data.length - 2];
  const displayData = hoverData ?? last;
  const change = displayData && prev ? displayData.close! - prev.close : 0;
  const changePct = prev?.close ? (change / prev.close) * 100 : 0;
  const isUp = (displayData?.close ?? 0) >= (displayData?.open ?? 0);

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
              borderLeft: "1px solid rgba(50,121,249,0.15)",
              boxShadow: "-24px 0 80px rgba(0,0,0,0.9)",
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
                  <span style={{ fontSize: "18px", fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: "var(--text-1)", letterSpacing: "0.04em" }}>
                    {cleanSymbol}
                  </span>
                  <span
                    style={{
                      fontSize: "13px",
                      fontFamily: "JetBrains Mono, monospace",
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 6,
                      color: isUp ? "#27AE60" : "#E74C3C",
                      background: isUp ? "rgba(39,174,96,0.1)" : "rgba(231,76,60,0.1)",
                      border: `1px solid ${isUp ? "rgba(39,174,96,0.25)" : "rgba(231,76,60,0.25)"}`,
                    }}
                  >
                    {isUp ? "▲" : "▼"} {Math.abs(changePct).toFixed(2)}%
                  </span>
                </div>
                {name && <div style={{ fontSize: "11px", color: "var(--text-3)", marginTop: 2, fontFamily: "Inter, sans-serif" }}>{name}</div>}
              </div>

              {displayData && (
                <div className="hidden md:flex items-center gap-5 mr-4">
                  {[
                    { label: "O", val: fmtPrice(displayData.open ?? 0) },
                    { label: "H", val: fmtPrice(displayData.high ?? 0) },
                    { label: "L", val: fmtPrice(displayData.low ?? 0) },
                    { label: "C", val: fmtPrice(displayData.close ?? 0) },
                    { label: "V", val: fmtVol(displayData.volume ?? 0) },
                  ].map(item => (
                    <div key={item.label} className="text-center">
                      <div style={{ fontSize: "9px", color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "Inter, sans-serif" }}>{item.label}</div>
                      <div style={{ fontSize: "11px", color: "#A0A0BC", fontFamily: "JetBrains Mono, monospace" }}>{item.val}</div>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-1">
                {loading && <RefreshCw style={{ width: 13, height: 13, color: "#3279F9", animation: "spin 1s linear infinite" }} />}
                <a
                  href={`https://www.tradingview.com/chart/?symbol=NSE%3A${cleanSymbol}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 rounded flex items-center gap-1 transition-colors"
                  style={{ fontSize: "9px", color: "var(--text-3)", letterSpacing: "0.08em", textDecoration: "none" }}
                  onMouseEnter={e => (e.currentTarget.style.color = "#3279F9")}
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
                  onMouseEnter={e => (e.currentTarget.style.color = "#FFFFFF")}
                  onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
                >
                  <X style={{ width: 16, height: 16 }} />
                </button>
              </div>
            </div>

            {/* Timeframe selector */}
            <div
              className="flex items-center gap-1 px-4 py-2 shrink-0"
              style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", background: "rgba(0,0,0,0.6)" }}
            >
              {TIMEFRAMES.map(t => (
                <button
                  key={t.label}
                  onClick={() => setTf(t)}
                  style={{
                    fontSize: "11px",
                    fontFamily: "JetBrains Mono, monospace",
                    fontWeight: tf.label === t.label ? 700 : 500,
                    padding: "4px 12px",
                    borderRadius: 6,
                    background: tf.label === t.label ? "rgba(50,121,249,0.15)" : "transparent",
                    color: tf.label === t.label ? "#3279F9" : "var(--text-3)",
                    border: `1px solid ${tf.label === t.label ? "rgba(50,121,249,0.35)" : "transparent"}`,
                    cursor: "pointer",
                    transition: "all 150ms",
                  }}
                  onMouseEnter={e => { if (tf.label !== t.label) { e.currentTarget.style.color = "#A0A0BC"; e.currentTarget.style.background = "rgba(255,255,255,0.04)"; } }}
                  onMouseLeave={e => { if (tf.label !== t.label) { e.currentTarget.style.color = "var(--text-3)"; e.currentTarget.style.background = "transparent"; } }}
                >
                  {t.label}
                </button>
              ))}
              <div className="flex-1" />
              <span style={{ fontSize: "9px", color: "#1C1C2E", letterSpacing: "0.1em", fontFamily: "Inter, sans-serif" }}>NSE · YFINANCE</span>
            </div>

            {/* Chart area */}
            <div className="flex-1 relative overflow-hidden">
              {loading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.85)" }}>
                  <div className="flex flex-col items-center gap-3">
                    <RefreshCw style={{ width: 20, height: 20, color: "#3279F9", animation: "spin 1s linear infinite" }} />
                    <span style={{ fontSize: "11px", color: "var(--text-3)", fontFamily: "Inter, sans-serif" }}>Loading chart data...</span>
                  </div>
                </div>
              )}
              {!loading && data.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <div style={{ fontSize: "28px", marginBottom: 8 }}>📊</div>
                    <div style={{ fontSize: "12px", color: "var(--text-3)", fontFamily: "Inter, sans-serif" }}>No chart data for {cleanSymbol}</div>
                    <div style={{ fontSize: "10px", color: "var(--text-3)", marginTop: 4, fontFamily: "Inter, sans-serif" }}>Market may be closed or symbol not found</div>
                  </div>
                </div>
              )}
              <div ref={chartContainerRef} className="w-full h-full" />
            </div>

            {/* Bottom stats bar */}
            {last && (
              <div
                className="flex items-center gap-6 px-5 py-2.5 shrink-0 flex-wrap"
                style={{ borderTop: "1px solid rgba(255,255,255,0.05)", background: "rgba(0,0,0,0.8)" }}
              >
                {[
                  { label: "OPEN",  val: `₹${fmtPrice(last.open)}`,  color: "#A0A0BC" },
                  { label: "HIGH",  val: `₹${fmtPrice(last.high)}`,  color: "#27AE60" },
                  { label: "LOW",   val: `₹${fmtPrice(last.low)}`,   color: "#E74C3C" },
                  { label: "CLOSE", val: `₹${fmtPrice(last.close)}`, color: "#FFFFFF" },
                  { label: "VOL",   val: fmtVol(last.volume),         color: "#3279F9" },
                ].map(s => (
                  <div key={s.label} className="flex items-center gap-1.5">
                    <span style={{ fontSize: "9px", color: "var(--text-3)", letterSpacing: "0.1em", fontFamily: "Inter, sans-serif" }}>{s.label}</span>
                    <span style={{ fontSize: "11px", color: s.color, fontFamily: "JetBrains Mono, monospace" }}>{s.val}</span>
                  </div>
                ))}
                <div className="flex-1" />
                <div className="flex items-center gap-1.5">
                  {changePct >= 0
                    ? <TrendingUp style={{ width: 12, height: 12, color: "#27AE60" }} />
                    : <TrendingDown style={{ width: 12, height: 12, color: "#E74C3C" }} />
                  }
                  <span style={{ fontSize: "12px", fontFamily: "JetBrains Mono, monospace", fontWeight: 700, color: changePct >= 0 ? "#27AE60" : "#E74C3C" }}>
                    {change >= 0 ? "+" : ""}{fmtPrice(change)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
                  </span>
                </div>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
