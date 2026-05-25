import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ExternalLink, Loader2, RefreshCw, BarChart2, Activity, Brain, TrendingUp, Send } from "lucide-react";
import { createChart, ColorType, CandlestickStyleOptions, DeepPartial } from "lightweight-charts";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useLivePrice, useStockFundamentals, type OHLCBar } from "@/api/market-queries";
import { useAnalyseStock } from "@/api/watchlist-queries";

// ── Types ──────────────────────────────────────────────────────────────────────

interface ChartDrawerProps {
  symbol: string | null;
  name?: string;
  onClose: () => void;
}

// ── Symbol helpers ─────────────────────────────────────────────────────────────

const TV_INDEX_MAP: Record<string, string> = {
  "^NSEI": "NSE:NIFTY", "^NSEBANK": "NSE:BANKNIFTY",
  "^BSESN": "BSE:SENSEX", "^NSEMDCP50": "NSE:MIDCPNIFTY", "^CNXIT": "NSE:NIFTYIT",
};
function toTVSymbol(raw: string) {
  const clean = raw.replace(".NS", "").replace(".BO", "").toUpperCase();
  return TV_INDEX_MAP[clean] ?? `NSE:${clean}`;
}
function toYFTicker(raw: string) {
  const s = raw.trim().toUpperCase().replace(/\.(NS|BO)$/i, "");
  return s.startsWith("^") ? s : `${s}.NS`;
}

// ── Timeframes ─────────────────────────────────────────────────────────────────

const TIMEFRAMES = [
  { label: "5m",  period: "5d",  interval: "5m"  },
  { label: "15m", period: "5d",  interval: "15m" },
  { label: "1h",  period: "30d", interval: "1h"  },
  { label: "1D",  period: "3mo", interval: "1d"  },
  { label: "1W",  period: "1y",  interval: "1wk" },
  { label: "1M",  period: "2y",  interval: "1mo" },
] as const;
type TF = typeof TIMEFRAMES[number];

// ── Client-side technicals ─────────────────────────────────────────────────────

function computeTechnicals(bars: OHLCBar[]) {
  const n = bars.length;
  if (n < 20) return null;
  const closes = bars.map(b => b.close);
  const highs   = bars.map(b => b.high);
  const lows    = bars.map(b => b.low);
  const vols    = bars.map(b => b.volume);

  const sma = (period: number) =>
    n >= period ? closes.slice(-period).reduce((a, b) => a + b, 0) / period : null;

  // RSI-14 (Wilder smoothing, simplified)
  const rsi14 = (() => {
    if (n < 15) return null;
    const deltas = closes.slice(-(14 + 1));
    let gains = 0, losses = 0;
    for (let i = 1; i < deltas.length; i++) {
      const d = deltas[i] - deltas[i - 1];
      if (d > 0) gains += d; else losses -= d;
    }
    const avgG = gains / 14, avgL = losses / 14;
    if (avgL === 0) return 100;
    return +(100 - 100 / (1 + avgG / avgL)).toFixed(1);
  })();

  // MACD 12/26/9
  const ema = (period: number, src = closes): number | null => {
    if (src.length < period) return null;
    const k = 2 / (period + 1);
    let e = src.slice(0, period).reduce((a, b) => a + b) / period;
    for (let i = period; i < src.length; i++) e = src[i] * k + e * (1 - k);
    return +e.toFixed(2);
  };
  const ema12 = ema(12); const ema26 = ema(26);
  const macd  = ema12 && ema26 ? +(ema12 - ema26).toFixed(2) : null;

  const pctChange = (days: number) =>
    n > days ? +(((closes[n - 1] - closes[n - 1 - days]) / closes[n - 1 - days]) * 100).toFixed(2) : null;

  const vol20avg = vols.slice(-20).reduce((a, b) => a + b, 0) / 20;
  const relVol   = vol20avg > 0 ? +(vols[n - 1] / vol20avg).toFixed(2) : null;

  const h52 = Math.max(...highs.slice(-252));
  const l52  = Math.min(...lows.slice(-252));
  const fromHigh = h52 > 0 ? +(((closes[n - 1] - h52) / h52) * 100).toFixed(1) : null;

  const bb20 = sma(20);
  let bbUpper: number | null = null, bbLower: number | null = null;
  if (bb20 !== null) {
    const slice = closes.slice(-20);
    const sd = Math.sqrt(slice.reduce((a, v) => a + (v - bb20) ** 2, 0) / 20);
    bbUpper = +(bb20 + 2 * sd).toFixed(2);
    bbLower = +(bb20 - 2 * sd).toFixed(2);
  }

  return {
    close: closes[n - 1],
    sma20: sma(20), sma50: sma(50), sma200: sma(200),
    ema20: ema(20),
    rsi14, macd,
    bbUpper, bbLower,
    h52, l52, fromHigh,
    pct1d: pctChange(1), pct5d: pctChange(5), pct20d: pctChange(20),
    relVol,
    volume: vols[n - 1],
  };
}

// ── Design tokens ──────────────────────────────────────────────────────────────

const C = {
  bg:      "#08080f",
  bg2:     "rgba(10,8,22,0.98)",
  bg3:     "rgba(12,10,26,0.6)",
  border:  "rgba(167,139,250,0.18)",
  border2: "rgba(255,255,255,0.07)",
  accent:  "#a78bfa",
  accentDim: "rgba(167,139,250,0.12)",
  green:   "#10b981",
  red:     "#f87171",
  amber:   "#f59e0b",
  text1:   "#f5f5f7",
  text2:   "rgba(255,255,255,0.6)",
  text3:   "rgba(255,255,255,0.35)",
  text4:   "rgba(255,255,255,0.2)",
};

// ── Micro components ───────────────────────────────────────────────────────────

function Pill({ label, color = C.accent }: { label: string; color?: string }) {
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, letterSpacing: "0.08em",
      padding: "2px 7px", borderRadius: 4,
      background: `${color}18`, color, border: `1px solid ${color}30`,
      fontFamily: "var(--font-mono)",
    }}>{label}</span>
  );
}

function FRow({ label, value, sub, highlight, positive, negative }:
  { label: string; value: React.ReactNode; sub?: string; highlight?: boolean; positive?: boolean; negative?: boolean }) {
  const col = positive ? C.green : negative ? C.red : highlight ? C.accent : C.text1;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 0", borderBottom: `1px solid ${C.border2}` }}>
      <span style={{ fontSize: 11.5, color: C.text3, fontWeight: 500 }}>{label}</span>
      <div style={{ textAlign: "right" }}>
        <span style={{ fontSize: 12, color: col, fontWeight: 700, fontFamily: "var(--font-mono)" }}>{value}</span>
        {sub && <div style={{ fontSize: 9.5, color: C.text4, marginTop: 1 }}>{sub}</div>}
      </div>
    </div>
  );
}

function SectionHead({ title }: { title: string }) {
  return (
    <div style={{ fontSize: 9.5, fontWeight: 700, color: C.text4, letterSpacing: "0.12em", textTransform: "uppercase", marginTop: 20, marginBottom: 6 }}>
      {title}
    </div>
  );
}

function ShareBar({ label, value, color, pledge }: { label: string; value: number | null | undefined; color: string; pledge?: number | null }) {
  const v = value ?? 0;
  return (
    <div style={{ marginBottom: 9 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
        <span style={{ fontSize: 11, color: C.text3 }}>{label}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {pledge != null && pledge > 0 && (
            <span style={{ fontSize: 9.5, color: C.red, background: "rgba(239,68,68,0.12)", padding: "1px 5px", borderRadius: 3 }}>
              {pledge.toFixed(1)}% pledged
            </span>
          )}
          <span style={{ fontSize: 11, fontWeight: 700, color, fontFamily: "var(--font-mono)" }}>
            {v > 0 ? `${v.toFixed(2)}%` : "—"}
          </span>
        </div>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.07)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.min(v, 100)}%`, background: color, borderRadius: 2, transition: "width 0.6s ease" }} />
      </div>
    </div>
  );
}

function RsiGauge({ value }: { value: number | null }) {
  if (value === null) return <span style={{ fontSize: 12, color: C.text3 }}>—</span>;
  const pct = (value / 100) * 100;
  const col = value >= 70 ? C.red : value <= 30 ? C.green : C.amber;
  const label = value >= 70 ? "Overbought" : value <= 30 ? "Oversold" : value >= 55 ? "Bullish" : value <= 45 ? "Bearish" : "Neutral";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ fontSize: 15, fontWeight: 800, fontFamily: "var(--font-mono)", color: col }}>{value}</span>
      <div style={{ flex: 1 }}>
        <div style={{ height: 5, borderRadius: 3, background: "rgba(255,255,255,0.07)", overflow: "hidden", position: "relative" }}>
          <div style={{ position: "absolute", left: 0, top: 0, height: "100%", background: `linear-gradient(90deg, ${C.green}, ${C.amber}, ${C.red})`, width: "100%", opacity: 0.3, borderRadius: 3 }} />
          <div style={{ position: "absolute", left: `${pct}%`, top: "-2px", width: 3, height: 9, background: col, borderRadius: 2, transform: "translateX(-50%)" }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2, fontSize: 8, color: C.text4 }}>
          <span>0</span><span>30</span><span>70</span><span>100</span>
        </div>
      </div>
      <Pill label={label} color={col} />
    </div>
  );
}

// ── Chart section ──────────────────────────────────────────────────────────────

function StockChart({ yfTicker, period, interval }: { yfTicker: string; period: string; interval: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { data, isLoading, error, refetch } = useQuery<OHLCBar[]>({
    queryKey: ["chart-ohlcv", yfTicker, period, interval],
    queryFn: () => api.get<OHLCBar[]>(`/market/history/${encodeURIComponent(yfTicker)}?period=${period}&interval=${interval}`),
    staleTime: 2 * 60_000,
    retry: 1,
    enabled: !!yfTicker,
  });

  useEffect(() => {
    if (!containerRef.current || !data || data.length < 2) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      layout: { background: { type: ColorType.Solid, color: C.bg }, textColor: C.text3, fontFamily: "'JetBrains Mono', monospace", fontSize: 10 },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.05)", textColor: C.text3, scaleMargins: { top: 0.06, bottom: 0.14 } },
      timeScale: { borderColor: "rgba(255,255,255,0.05)", fixLeftEdge: true, fixRightEdge: true, timeVisible: true, secondsVisible: false },
      crosshair: { horzLine: { color: "rgba(167,139,250,0.5)", width: 1, style: 2 }, vertLine: { color: "rgba(167,139,250,0.5)", width: 1, style: 2 } },
      handleScroll: true, handleScale: true,
    });
    const opts: DeepPartial<CandlestickStyleOptions> = { upColor: C.green, downColor: C.red, borderUpColor: C.green, borderDownColor: C.red, wickUpColor: C.green, wickDownColor: C.red };
    const cs = chart.addCandlestickSeries(opts);
    cs.setData(data.map(d => ({ time: d.time as any, open: d.open, high: d.high, low: d.low, close: d.close })));
    const vs = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, borderVisible: false });
    vs.setData(data.map(d => ({ time: d.time as any, value: d.volume, color: d.close >= d.open ? "rgba(16,185,129,0.28)" : "rgba(248,113,113,0.28)" })));
    chart.timeScale().fitContent();
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    });
    ro.observe(containerRef.current);
    return () => { ro.disconnect(); chart.remove(); };
  }, [data]);

  if (isLoading) return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, background: C.bg }}>
      <Loader2 style={{ width: 28, height: 28, color: C.accent, animation: "spin 1s linear infinite" }} />
      <span style={{ fontSize: 11, color: C.text3 }}>Fetching OHLCV…</span>
    </div>
  );
  if (error || !data || data.length < 2) return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, background: C.bg }}>
      <span style={{ fontSize: 32 }}>📊</span>
      <span style={{ fontSize: 12, color: C.text3, textAlign: "center", maxWidth: 280 }}>Chart data unavailable. Try 1D or 1W interval.</span>
      <button onClick={() => refetch()} style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 16px", borderRadius: 8, cursor: "pointer", background: C.accentDim, border: `1px solid ${C.accent}40`, color: C.accent, fontSize: 12, fontWeight: 600 }}>
        <RefreshCw style={{ width: 11, height: 11 }} /> Retry
      </button>
    </div>
  );
  return <div ref={containerRef} style={{ flex: 1, width: "100%", minHeight: 0 }} />;
}

// ── Fundamentals panel ─────────────────────────────────────────────────────────

function FundamentalsPanel({ symbol }: { symbol: string }) {
  const { data: f, isLoading } = useStockFundamentals(symbol);
  const na = "—";
  const fmt = (v: number | undefined | null, dec = 1, prefix = "") =>
    v != null && v !== 0 ? `${prefix}${v.toFixed(dec)}` : na;
  const pct = (v: number | undefined | null) =>
    v != null ? <span style={{ color: v >= 0 ? C.green : C.red }}>{v >= 0 ? "+" : ""}{v.toFixed(1)}%</span> : na;

  if (isLoading) return (
    <div style={{ padding: "20px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: 14 }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 22, borderRadius: 4, opacity: 1 - i * 0.04 }} />
      ))}
    </div>
  );
  if (!f || f.error) return (
    <div style={{ padding: 24, textAlign: "center" }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>📋</div>
      <div style={{ fontSize: 12, color: C.text3 }}>Fundamentals unavailable for {symbol}</div>
    </div>
  );

  return (
    <div style={{ padding: "6px 20px 20px", overflowY: "auto", flex: 1 }}>
      <SectionHead title="Valuation" />
      <FRow label="Market Cap" value={f.market_cap_cr >= 1000 ? `₹${(f.market_cap_cr / 1000).toFixed(1)}K Cr` : `₹${f.market_cap_cr?.toFixed(0)} Cr`} />
      <FRow label="P/E (TTM)"      value={fmt(f.pe)}          highlight />
      <FRow label="Forward P/E"    value={fmt(f.forward_pe)} />
      <FRow label="P/B"            value={fmt(f.pb)} />
      <FRow label="EV / EBITDA"    value={fmt(f.ev_ebitda)} />
      <FRow label="EPS (TTM)"      value={`₹${fmt(f.eps_ttm)}`}     highlight />
      <FRow label="EPS (Forward)"  value={`₹${fmt(f.eps_forward)}`} />
      <FRow label="Dividend Yield" value={f.dividend_yield ? `${f.dividend_yield.toFixed(2)}%` : na} />
      <FRow label="Beta"           value={fmt(f.beta, 2)} />
      <FRow label="52W High"       value={f.week_high_52 ? `₹${f.week_high_52.toLocaleString("en-IN")}` : na} />
      <FRow label="52W Low"        value={f.week_low_52  ? `₹${f.week_low_52.toLocaleString("en-IN")}`  : na} />

      <SectionHead title="Profitability" />
      <FRow label="ROE"             value={pct(f.roe)}           positive={(f.roe ?? 0) > 0} />
      {f.roce != null && <FRow label="ROCE" value={pct(f.roce)} positive={(f.roce ?? 0) > 15} negative={(f.roce ?? 0) < 0} highlight />}
      <FRow label="ROA"             value={pct(f.roa)}           positive={(f.roa ?? 0) > 0} />
      <FRow label="Operating Margin" value={pct(f.op_margin)} />
      <FRow label="Net Margin"      value={pct(f.profit_margin)} />
      {f.sales_ttm_cr   != null && <FRow label="Sales TTM"   value={`₹${(f.sales_ttm_cr).toFixed(0)} Cr`} />}
      {f.profit_ttm_cr  != null && <FRow label="Profit TTM"  value={`₹${(f.profit_ttm_cr).toFixed(0)} Cr`} positive={(f.profit_ttm_cr ?? 0) > 0} />}

      <SectionHead title="Growth (YoY)" />
      <FRow label="Revenue Growth"  value={pct(f.revenue_growth)}   positive={(f.revenue_growth ?? 0) > 0}  negative={(f.revenue_growth ?? 0) < -5} />
      <FRow label="Earnings Growth" value={pct(f.earnings_growth)} positive={(f.earnings_growth ?? 0) > 0} negative={(f.earnings_growth ?? 0) < -5} />

      <SectionHead title="Balance Sheet" />
      <FRow label="Debt / Equity"  value={fmt(f.debt_to_equity, 2)} negative={(f.debt_to_equity ?? 0) > 1} />
      <FRow label="Current Ratio"  value={fmt(f.current_ratio,  2)} positive={(f.current_ratio  ?? 0) > 1.5} />
      <FRow label="Book Value"     value={`₹${fmt(f.book_value)}`} />
      <FRow label="Shares"         value={f.shares_cr ? `${f.shares_cr.toFixed(2)} Cr` : na} />

      {(f.promoter_pct != null || f.fii_pct != null) && (
        <>
          <SectionHead title="Shareholding Pattern" />
          <ShareBar label="Promoters"  value={f.promoter_pct}  color={C.accent}  pledge={f.promoter_pledge_pct} />
          <ShareBar label="FII / FPI"  value={f.fii_pct}       color="#818cf8" />
          <ShareBar label="DII"        value={f.dii_pct}        color={C.amber} />
          <ShareBar label="Public"     value={f.public_pct}     color={C.text3} />
          {f.screener_scraped_at && (
            <div style={{ fontSize: 9.5, color: C.text4, marginTop: 4 }}>
              Shareholding as of screener.in scrape · {f.screener_scraped_at}
            </div>
          )}
        </>
      )}

      <div style={{ marginTop: 16, padding: "8px 10px", background: "rgba(255,255,255,0.03)", borderRadius: 6, border: `1px solid ${C.border2}` }}>
        <div style={{ fontSize: 9.5, color: C.text4 }}>
          Source: {f.source === "screener_db" ? "screener.in cache" : "yFinance"} + screener.in
          {f.screener_url && <> · <a href={f.screener_url} target="_blank" rel="noreferrer" style={{ color: C.accent }}>screener.in ↗</a></>}
          {" "}· ⚠ not SEBI-registered advice
        </div>
      </div>
    </div>
  );
}

// ── Technical panel ────────────────────────────────────────────────────────────

function TechnicalPanel({ yfTicker }: { yfTicker: string; symbol: string }) {
  const { data: bars, isLoading } = useQuery<OHLCBar[]>({
    queryKey: ["chart-ohlcv", yfTicker, "1y", "1d"],
    queryFn: () => api.get<OHLCBar[]>(`/market/history/${encodeURIComponent(yfTicker)}?period=1y&interval=1d`),
    staleTime: 5 * 60_000,
    enabled: !!yfTicker,
  });

  if (isLoading) return (
    <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: 12 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 24, borderRadius: 4 }} />)}
    </div>
  );

  const t = bars && bars.length >= 20 ? computeTechnicals(bars) : null;
  const price = t?.close ?? 0;

  const maSig = (sma: number | null) => {
    if (!sma || !price) return null;
    return price > sma
      ? <span style={{ color: C.green }}>▲ Above</span>
      : <span style={{ color: C.red }}>▼ Below</span>;
  };
  const fmt = (v: number | null, dec = 2, prefix = "₹") =>
    v != null ? `${prefix}${v.toFixed(dec)}` : "—";

  return (
    <div style={{ padding: "6px 20px 20px", overflowY: "auto", flex: 1 }}>
      <SectionHead title="Momentum" />
      <div style={{ padding: "8px 0", borderBottom: `1px solid ${C.border2}` }}>
        <div style={{ fontSize: 11.5, color: C.text3, marginBottom: 6 }}>RSI (14)</div>
        <RsiGauge value={t?.rsi14 ?? null} />
      </div>
      <FRow label="MACD"        value={fmt(t?.macd ?? null, 2, "")}
        positive={(t?.macd ?? 0) > 0} negative={(t?.macd ?? 0) < 0} />

      <SectionHead title="Moving Averages" />
      <FRow label="SMA 20"  value={<>{fmt(t?.sma20  ?? null)}&nbsp;&nbsp;{maSig(t?.sma20  ?? null)}</>} />
      <FRow label="SMA 50"  value={<>{fmt(t?.sma50  ?? null)}&nbsp;&nbsp;{maSig(t?.sma50  ?? null)}</>} />
      <FRow label="SMA 200" value={<>{fmt(t?.sma200 ?? null)}&nbsp;&nbsp;{maSig(t?.sma200 ?? null)}</>} />
      <FRow label="EMA 20"  value={<>{fmt(t?.ema20  ?? null)}&nbsp;&nbsp;{maSig(t?.ema20  ?? null)}</>} />

      <SectionHead title="Volatility" />
      <FRow label="BB Upper"     value={fmt(t?.bbUpper ?? null)} />
      <FRow label="BB Lower"     value={fmt(t?.bbLower ?? null)} />
      {t?.bbUpper && t?.bbLower && (
        <FRow label="BB Width"   value={`₹${(t.bbUpper - t.bbLower).toFixed(1)}`} />
      )}

      <SectionHead title="Price Action" />
      <FRow label="1D Change"      value={t?.pct1d  != null ? `${t.pct1d >= 0 ? "+" : ""}${t.pct1d}%`  : "—"} positive={(t?.pct1d  ?? 0) > 0} negative={(t?.pct1d  ?? 0) < 0} />
      <FRow label="5D Change"      value={t?.pct5d  != null ? `${t.pct5d >= 0 ? "+" : ""}${t.pct5d}%`  : "—"} positive={(t?.pct5d  ?? 0) > 0} negative={(t?.pct5d  ?? 0) < 0} />
      <FRow label="20D Change"     value={t?.pct20d != null ? `${t.pct20d >= 0 ? "+" : ""}${t.pct20d}%` : "—"} positive={(t?.pct20d ?? 0) > 0} negative={(t?.pct20d ?? 0) < 0} />
      <FRow label="52W High"       value={t?.h52 ? `₹${t.h52.toLocaleString("en-IN")}` : "—"} />
      <FRow label="52W Low"        value={t?.l52 ? `₹${t.l52.toLocaleString("en-IN")}`  : "—"} />
      <FRow label="From 52W High"  value={t?.fromHigh != null ? `${t.fromHigh}%` : "—"} negative={(t?.fromHigh ?? 0) < -20} />

      <SectionHead title="Volume" />
      <FRow label="Today"      value={t?.volume ? `${(t.volume / 1_000_000).toFixed(2)}M` : "—"} />
      <FRow label="Rel Volume" value={t?.relVol != null ? `${t.relVol}x` : "—"}
        positive={(t?.relVol ?? 0) > 1.5} />

      <div style={{ marginTop: 16, padding: "8px 10px", background: "rgba(255,255,255,0.03)", borderRadius: 6, border: `1px solid ${C.border2}` }}>
        <div style={{ fontSize: 9.5, color: C.text4 }}>Computed from 1Y daily OHLCV (yFinance). Refreshed on open.</div>
      </div>
    </div>
  );
}

// ── AI Chat panel ──────────────────────────────────────────────────────────────

interface ChatMsg { role: "user" | "assistant"; content: string }

const FAQS = [
  { label: "Full analysis",      question: "Give full analysis: thesis, fundamentals, technicals, trade structure with entry/stop/target." },
  { label: "Entry & targets",    question: "What is the best 1:3 risk-reward setup? Give specific entry zone, stop-loss, TP1 and TP2 with reasoning." },
  { label: "FII / DII flow",     question: "Analyse FII/DII trend and institutional positioning. Is smart money accumulating or distributing?" },
  { label: "Near-term catalyst", question: "Is there a near-term catalyst that can reprice this stock? Upcoming earnings, policy, or sector trigger?" },
  { label: "Breakout level",     question: "Where is the key breakout level? What price and volume conditions confirm a breakout?" },
  { label: "Key risks",          question: "What are the key risks, red flags, and invalidation levels to watch?" },
];

function renderMd(text: string) {
  return text.split("\n").map((line, i) => {
    const trimmed = line.trim();
    const hm = trimmed.match(/^(#{1,3})\s+(.+)/);
    if (hm) {
      const sz = hm[1].length === 1 ? 14 : hm[1].length === 2 ? 13 : 12;
      return <div key={i} style={{ fontWeight: 700, fontSize: sz, color: C.text1, marginTop: 10, marginBottom: 2 }}>{inlineMd(hm[2])}</div>;
    }
    if (/^[-*]\s/.test(trimmed)) return (
      <div key={i} style={{ display: "flex", gap: 8, marginBottom: 3, paddingLeft: 4 }}>
        <span style={{ color: C.accent, flexShrink: 0, marginTop: 2 }}>•</span>
        <span style={{ fontSize: 12.5, lineHeight: 1.65, color: C.text1 }}>{inlineMd(trimmed.slice(2))}</span>
      </div>
    );
    if (!trimmed) return <div key={i} style={{ height: 6 }} />;
    return <div key={i} style={{ fontSize: 12.5, lineHeight: 1.7, marginBottom: 2, color: C.text1 }}>{inlineMd(line)}</div>;
  });
}

function inlineMd(text: string): React.ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i} style={{ color: C.text1, fontWeight: 700 }}>{p.slice(2, -2)}</strong>
      : p
  );
}

function AIChatPanel({ symbol }: { symbol: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const analyse = useAnalyseStock();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMessages([]); setInput(""); }, [symbol]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, analyse.isPending]);

  const send = useCallback((question: string) => {
    if (!question.trim() || analyse.isPending) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: question }]);
    analyse.mutate(
      { symbol, question, history: messages.slice(-6) },
      {
        onSuccess: (data) => setMessages(prev => [...prev, { role: "assistant", content: data.response }]),
        onError: (err) => setMessages(prev => [...prev, { role: "assistant", content: `Error: ${(err as Error).message}` }]),
      }
    );
  }, [symbol, messages, analyse]);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px 8px" }}>
        {messages.length === 0 ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, color: C.text2, fontSize: 12, fontWeight: 700 }}>
              <Brain style={{ width: 13, height: 13, color: C.accent }} />
              AI Analysis · {symbol}
            </div>
            <div style={{ fontSize: 10.5, color: C.text4, marginBottom: 14 }}>Real-time context: screener.in + NSE live price + NEO database</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {FAQS.map(faq => (
                <button key={faq.label} onClick={() => send(faq.question)} disabled={analyse.isPending}
                  style={{ textAlign: "left", padding: "9px 14px", borderRadius: 9, background: "rgba(255,255,255,0.04)", border: `1px solid ${C.border2}`, color: C.text2, fontSize: 12, cursor: "pointer", fontFamily: "var(--font-body)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, transition: "all 120ms" }}
                  onMouseEnter={e => { const el = e.currentTarget as HTMLButtonElement; el.style.borderColor = C.accent; el.style.color = C.text1; el.style.background = C.accentDim; }}
                  onMouseLeave={e => { const el = e.currentTarget as HTMLButtonElement; el.style.borderColor = C.border2; el.style.color = C.text2; el.style.background = "rgba(255,255,255,0.04)"; }}
                >
                  <span style={{ fontWeight: 600 }}>{faq.label}</span>
                  <Send style={{ width: 10, height: 10, opacity: 0.4, flexShrink: 0 }} />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m, i) => (
              <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", marginBottom: 12 }}>
                <div style={{
                  maxWidth: "90%", padding: "9px 13px",
                  borderRadius: m.role === "user" ? "14px 14px 4px 14px" : "4px 14px 14px 14px",
                  background: m.role === "user" ? C.accent : "rgba(255,255,255,0.06)",
                  border: m.role === "user" ? "none" : `1px solid ${C.border2}`,
                  color: m.role === "user" ? "#fff" : C.text1,
                }}>
                  {m.role === "user"
                    ? <span style={{ fontSize: 12.5, lineHeight: 1.6 }}>{m.content}</span>
                    : <div>{renderMd(m.content)}</div>}
                </div>
              </div>
            ))}
            {analyse.isPending && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: C.text3, fontSize: 11.5, marginBottom: 12 }}>
                <Loader2 style={{ width: 13, height: 13, animation: "spin 1s linear infinite" }} />Analysing…
              </div>
            )}
            {!analyse.isPending && (
              <button onClick={() => setMessages([])} style={{ fontSize: 10, color: C.text4, background: "none", border: "none", cursor: "pointer", padding: "4px 0", marginBottom: 4 }}>
                ← Back to questions
              </button>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "8px 12px", borderTop: `1px solid ${C.border2}`, display: "flex", gap: 8, alignItems: "flex-end", flexShrink: 0 }}>
        <textarea value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.trim()); } }}
          placeholder={`Ask about ${symbol}…`} rows={2}
          style={{ flex: 1, resize: "none", padding: "8px 11px", borderRadius: 9, background: "rgba(255,255,255,0.06)", border: `1px solid ${C.border2}`, color: C.text1, fontSize: 12.5, outline: "none", fontFamily: "var(--font-body)", lineHeight: 1.5 }}
        />
        <button onClick={() => send(input.trim())} disabled={!input.trim() || analyse.isPending}
          style={{ width: 36, height: 36, borderRadius: 9, border: "none", background: input.trim() ? C.accent : "rgba(255,255,255,0.06)", color: input.trim() ? "#fff" : C.text4, display: "flex", alignItems: "center", justifyContent: "center", cursor: input.trim() ? "pointer" : "default", transition: "all 150ms", flexShrink: 0 }}>
          {analyse.isPending
            ? <Loader2 style={{ width: 14, height: 14, animation: "spin 1s linear infinite" }} />
            : <Send style={{ width: 14, height: 14 }} />}
        </button>
      </div>
    </div>
  );
}

// ── Live price header ──────────────────────────────────────────────────────────

function LivePriceStrip({ symbol }: { symbol: string }) {
  const { data: q, isLoading } = useLivePrice(symbol);

  if (isLoading) return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <div className="skeleton" style={{ width: 90, height: 22, borderRadius: 4 }} />
      <div className="skeleton" style={{ width: 60, height: 14, borderRadius: 4 }} />
    </div>
  );
  if (!q) return null;

  const up = q.change >= 0;
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
      <span style={{ fontSize: 22, fontFamily: "var(--font-mono)", fontWeight: 800, color: C.text1, letterSpacing: "-0.02em" }}>
        ₹{q.cmp?.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
      <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono)", color: up ? C.green : C.red }}>
        {up ? "▲" : "▼"} {up ? "+" : ""}{q.change?.toFixed(2)} ({q.pct_change?.toFixed(2)}%)
      </span>
      {q.volume > 0 && (
        <span style={{ fontSize: 10, color: C.text3, fontFamily: "var(--font-body)" }}>
          Vol {q.volume >= 1_000_000 ? `${(q.volume / 1_000_000).toFixed(2)}M` : `${(q.volume / 1_000).toFixed(0)}K`}
        </span>
      )}
      {q.vwap > 0 && (
        <span style={{ fontSize: 10, color: C.text3 }}>VWAP ₹{q.vwap?.toFixed(1)}</span>
      )}
    </div>
  );
}

// ── Main drawer ────────────────────────────────────────────────────────────────

type Tab = "chart" | "fundamentals" | "technical" | "ai";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "chart",        label: "Chart",        icon: <BarChart2   style={{ width: 12, height: 12 }} /> },
  { id: "fundamentals", label: "Fundamentals", icon: <TrendingUp  style={{ width: 12, height: 12 }} /> },
  { id: "technical",    label: "Technical",    icon: <Activity    style={{ width: 12, height: 12 }} /> },
  { id: "ai",           label: "AI Chat",      icon: <Brain       style={{ width: 12, height: 12 }} /> },
];

export function ChartDrawer({ symbol, name, onClose }: ChartDrawerProps) {
  const [tab, setTab]   = useState<Tab>("chart");
  const [tf,  setTf]    = useState<TF>(TIMEFRAMES[3]);

  const cleanSymbol = symbol ? symbol.replace(".NS", "").replace(".BO", "").replace(/^\^/, "").toUpperCase() : "";
  const tvSymbol    = symbol ? toTVSymbol(symbol) : "";
  const yfTicker    = symbol ? toYFTicker(symbol) : "";

  // Reset tab when symbol changes
  useEffect(() => { setTab("chart"); }, [symbol]);

  // Keyboard close
  useEffect(() => {
    if (!symbol) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [symbol, onClose]);

  return (
    <AnimatePresence>
      {symbol && (
        <>
          {/* Backdrop */}
          <motion.div className="fixed inset-0 z-40"
            style={{ background: "rgba(0,0,0,0.72)", backdropFilter: "blur(4px)" }}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.div className="fixed top-0 right-0 bottom-0 z-50 flex flex-col"
            style={{ width: "min(860px, 95vw)", background: C.bg, borderLeft: `1px solid ${C.border}`, boxShadow: `-24px 0 80px rgba(0,0,0,0.75), -1px 0 0 rgba(167,139,250,0.1)` }}
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 340, damping: 38 }}
          >

            {/* ── Header ── */}
            <div style={{ padding: "14px 18px 10px", flexShrink: 0, borderBottom: `1px solid ${C.border}`, background: C.bg2 }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                {/* Avatar */}
                <div style={{ width: 42, height: 42, borderRadius: 11, flexShrink: 0, background: "linear-gradient(135deg, rgba(167,139,250,0.18), rgba(96,165,250,0.1))", border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 800, color: C.accent }}>{cleanSymbol.slice(0, 3)}</span>
                </div>

                {/* Symbol + company */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                    <span style={{ fontSize: 17, fontFamily: "var(--font-mono)", fontWeight: 800, color: C.text1, letterSpacing: "0.02em" }}>{cleanSymbol}</span>
                    <Pill label="NSE" color={C.accent} />
                    <Pill label={yfTicker} color="rgba(255,255,255,0.4)" />
                  </div>
                  {name && <div style={{ fontSize: 11, color: C.text3, marginBottom: 6 }}>{name}</div>}
                  <LivePriceStrip symbol={cleanSymbol} />
                </div>

                {/* Actions */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                  <a href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`}
                    target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", gap: 4, padding: "5px 10px", borderRadius: 7, background: C.accentDim, border: `1px solid ${C.accent}40`, color: C.accent, fontSize: 10, fontWeight: 600, textDecoration: "none", transition: "background 150ms" }}
                    onMouseEnter={e => (e.currentTarget.style.background = "rgba(167,139,250,0.2)")}
                    onMouseLeave={e => (e.currentTarget.style.background = C.accentDim)}
                  >
                    <ExternalLink style={{ width: 10, height: 10 }} /> TV
                  </a>
                  <button onClick={onClose}
                    style={{ width: 30, height: 30, borderRadius: 7, background: "rgba(255,255,255,0.05)", border: `1px solid rgba(255,255,255,0.1)`, color: C.text3, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", transition: "all 150ms" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "rgba(248,113,113,0.15)"; e.currentTarget.style.color = C.red; e.currentTarget.style.borderColor = `${C.red}50`; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.05)"; e.currentTarget.style.color = C.text3; e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; }}
                  >
                    <X style={{ width: 14, height: 14 }} />
                  </button>
                </div>
              </div>
            </div>

            {/* ── Tab bar ── */}
            <div style={{ display: "flex", alignItems: "center", gap: 2, padding: "0 12px", flexShrink: 0, borderBottom: `1px solid ${C.border2}`, background: C.bg3 }}>
              {TABS.map(t => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  style={{
                    display: "flex", alignItems: "center", gap: 5, padding: "9px 14px",
                    fontSize: 11.5, fontWeight: tab === t.id ? 700 : 500, fontFamily: "var(--font-body)",
                    color: tab === t.id ? C.accent : C.text3,
                    background: "none", border: "none", cursor: "pointer",
                    borderBottom: tab === t.id ? `2px solid ${C.accent}` : "2px solid transparent",
                    transition: "all 120ms",
                  }}
                  onMouseEnter={e => { if (tab !== t.id) e.currentTarget.style.color = C.text2; }}
                  onMouseLeave={e => { if (tab !== t.id) e.currentTarget.style.color = C.text3; }}
                >
                  {t.icon}{t.label}
                </button>
              ))}
              {/* Timeframe selector only visible on chart tab */}
              {tab === "chart" && (
                <div style={{ display: "flex", alignItems: "center", gap: 2, marginLeft: "auto" }}>
                  {TIMEFRAMES.map(t => (
                    <button key={t.label} onClick={() => setTf(t)}
                      style={{ fontSize: 10.5, fontFamily: "var(--font-mono)", fontWeight: tf.label === t.label ? 700 : 500, padding: "4px 10px", borderRadius: 5, background: tf.label === t.label ? C.accentDim : "transparent", color: tf.label === t.label ? C.accent : C.text4, border: `1px solid ${tf.label === t.label ? `${C.accent}40` : "transparent"}`, cursor: "pointer", transition: "all 120ms" }}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* ── Content area ── */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
              {tab === "chart" && (
                <StockChart key={`${yfTicker}-${tf.label}`} yfTicker={yfTicker} period={tf.period} interval={tf.interval} />
              )}
              {tab === "fundamentals" && <FundamentalsPanel symbol={cleanSymbol} />}
              {tab === "technical"    && <TechnicalPanel yfTicker={yfTicker} symbol={cleanSymbol} />}
              {tab === "ai"           && <AIChatPanel symbol={cleanSymbol} />}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
