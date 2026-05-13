import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { RefreshCw, Bell, Search } from "lucide-react";
import { format } from "date-fns";
import { useLiveStore } from "@/store/live";
import { usePortfolioSummary } from "@/api/queries";
import { useMarketIndices } from "@/api/market-queries";
import { formatCurrency, formatPct } from "@/lib/utils";
import { useUIStore } from "@/store/ui";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

function ISTClock() {
  const [t, setT] = useState(() =>
    new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false })
  );
  useEffect(() => {
    const iv = setInterval(() =>
      setT(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false })), 1000);
    return () => clearInterval(iv);
  }, []);
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-3)", letterSpacing: "0.05em", flexShrink: 0 }}>
      {t} <span style={{ color: "var(--text-4)" }}>IST</span>
    </span>
  );
}

interface TickerItemData { label: string; value: string; chg?: number }

function renderTickerItem(item: TickerItemData, i: number) {
  const up = (item.chg ?? 0) > 0;
  const dn = (item.chg ?? 0) < 0;
  return (
    <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6, marginRight: 32, flexShrink: 0 }}>
      <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-4)", fontFamily: "var(--font-body)" }}>{item.label}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-2)", fontWeight: 500 }}>{item.value}</span>
      {item.chg !== undefined && (
        <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 10, color: up ? "var(--green)" : dn ? "var(--red)" : "var(--text-3)" }}>
          {up ? "▲" : dn ? "▼" : "—"}{Math.abs(item.chg).toFixed(2)}%
        </span>
      )}
      <span style={{ color: "var(--border)", marginLeft: 12 }}>│</span>
    </span>
  );
}

function TickerBar() {
  const { data: indices } = useMarketIndices();
  const { data: live } = useLiveStore();

  const items: TickerItemData[] = [];
  if (indices?.nifty50)    items.push({ label: "NIFTY 50",   value: indices.nifty50.price.toLocaleString("en-IN",    { minimumFractionDigits: 2 }), chg: indices.nifty50.change_pct });
  if (indices?.banknifty)  items.push({ label: "BANK NIFTY", value: indices.banknifty.price.toLocaleString("en-IN",  { minimumFractionDigits: 2 }), chg: indices.banknifty.change_pct });
  if (indices?.sensex)     items.push({ label: "SENSEX",     value: indices.sensex.price.toLocaleString("en-IN",     { minimumFractionDigits: 2 }), chg: indices.sensex.change_pct });
  if (indices?.niftyit)    items.push({ label: "NIFTY IT",   value: indices.niftyit.price.toLocaleString("en-IN",    { minimumFractionDigits: 2 }), chg: indices.niftyit.change_pct });
  if (indices?.niftymid50) items.push({ label: "MIDCAP 50",  value: indices.niftymid50.price.toLocaleString("en-IN", { minimumFractionDigits: 2 }), chg: indices.niftymid50.change_pct });
  if (live) items.push({ label: "NAV", value: formatCurrency(live.portfolio_value, true), chg: live.day_pnl_pct });
  if (items.length === 0) {
    ["NIFTY 50","BANK NIFTY","SENSEX","NIFTY IT","MIDCAP 50"].forEach(label => items.push({ label, value: "···" }));
  }

  // JS-driven ticker: no CSS animation, no GPU compositor layer, no overflow bleed
  const trackRef = useRef<HTMLDivElement>(null);
  const posRef   = useRef(0);
  const pauseRef = useRef(false);
  const rafRef   = useRef<number>(0);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const speed = 0.5; // px per frame at 60fps

    const step = () => {
      if (!pauseRef.current && track) {
        posRef.current += speed;
        const half = track.scrollWidth / 2;
        if (posRef.current >= half) posRef.current = 0;
        track.style.transform = `translateX(${-posRef.current}px)`;
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [items.length]);

  const doubled = [...items, ...items, ...items, ...items];

  return (
    <div
      style={{ flex: 1, overflow: "hidden", minWidth: 0, height: "100%" }}
      onMouseEnter={() => { pauseRef.current = true; }}
      onMouseLeave={() => { pauseRef.current = false; }}
    >
      <div
        ref={trackRef}
        style={{ display: "inline-flex", alignItems: "center", whiteSpace: "nowrap", height: "100%", willChange: "unset" }}
      >
        {doubled.map((item, i) => renderTickerItem(item, i))}
      </div>
    </div>
  );
}

export function Header({ title, subtitle }: HeaderProps) {
  const { data: live, lastUpdate } = useLiveStore();
  const { refetch, isFetching } = usePortfolioSummary();
  const { paperMode, openSearch } = useUIStore();

  return (
    <div style={{ flexShrink: 0, position: "sticky", top: 0, zIndex: 50, borderBottom: "1px solid var(--border)" }}>
      {/* ── Ticker strip — JS-driven, no CSS animation, no compositor bleed ── */}
      <div style={{
        display: "flex", alignItems: "center", height: 34,
        padding: "0 12px", overflow: "hidden",
        background: "var(--surface)",
        borderBottom: "1px solid var(--border-2)",
      }}>
        {/* Exchange indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, paddingRight: 12, marginRight: 8, borderRight: "1px solid var(--border)" }}>
          <motion.div
            style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--green)", boxShadow: "0 0 6px var(--green)" }}
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.14em", color: "var(--text-4)", fontFamily: "var(--font-body)" }}>NSE · BSE</span>
        </div>
        <TickerBar />
        <ISTClock />
      </div>

      {/* ── Page header ── */}
      <div style={{
        display: "flex", alignItems: "center", height: 52, padding: "0 20px", gap: 16,
        background: "var(--overlay)", backdropFilter: "blur(12px)",
      }}>
        {/* Page title */}
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 3, height: 20, borderRadius: 2, background: "linear-gradient(180deg, var(--blue), var(--violet))" }} />
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-1)", letterSpacing: "0.06em", fontFamily: "var(--font-heading)", textTransform: "uppercase" }}>
              {title}
            </div>
            {subtitle && (
              <div style={{ fontSize: 10, color: "var(--text-3)", letterSpacing: "0.04em", fontFamily: "var(--font-body)", marginTop: 1 }}>
                {subtitle}
              </div>
            )}
          </div>
        </div>

        <div style={{ flex: 1 }} />

        {/* Search */}
        <button
          onClick={openSearch}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-xl transition-all"
          style={{ background: "var(--card-bg)", border: "1px solid var(--border)", color: "var(--text-3)" }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--border-blue)"; e.currentTarget.style.color = "var(--text-2)"; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text-3)"; }}
        >
          <Search style={{ width: 12, height: 12 }} />
          <span style={{ fontSize: 12, fontFamily: "var(--font-body)", fontWeight: 500 }}>Search stocks...</span>
          <div style={{ display: "flex", gap: 3, marginLeft: 8 }}>
            {["⌘", "K"].map(k => (
              <kbd key={k} style={{ fontSize: 10, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 5px", color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>{k}</kbd>
            ))}
          </div>
        </button>

        {/* Paper mode badge */}
        {paperMode && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 10px", background: "var(--amber-dim)", border: "1px solid var(--border-amber)", borderRadius: 8 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--amber)", display: "block", boxShadow: "0 0 6px var(--amber)" }} />
            <span style={{ fontSize: 9, color: "var(--amber)", fontWeight: 800, letterSpacing: "0.1em", fontFamily: "var(--font-body)" }}>PAPER</span>
          </div>
        )}

        {/* Live stats */}
        {live && (
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            {[
              { label: "NAV",     val: formatCurrency(live.portfolio_value, true), color: "var(--text-1)" },
              { label: "DAY P&L", val: formatPct(live.day_pnl_pct),               color: live.day_pnl_pct >= 0 ? "var(--green)" : "var(--red)" },
              { label: "DD",      val: `-${Math.abs(live.drawdown_pct).toFixed(2)}%`, color: live.drawdown_pct > 5 ? "var(--red)" : "var(--text-3)" },
            ].map(item => (
              <div key={item.label}>
                <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", color: "var(--text-4)", fontFamily: "var(--font-body)", marginBottom: 2 }}>{item.label}</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: item.color, letterSpacing: "-0.02em" }}>{item.val}</div>
              </div>
            ))}
          </div>
        )}

        {live && <div style={{ width: 1, height: 20, background: "var(--border)" }} />}

        {/* Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button onClick={openSearch} className="md:hidden p-2 rounded-lg" style={{ color: "var(--text-3)", background: "none", border: "none", cursor: "pointer" }}>
            <Search style={{ width: 14, height: 14 }} />
          </button>
          {lastUpdate && (
            <span className="hidden lg:block" style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-4)", marginRight: 4 }}>
              {format(lastUpdate, "HH:mm:ss")}
            </span>
          )}
          <button
            onClick={() => refetch()}
            style={{ padding: "6px", borderRadius: 8, color: "var(--text-3)", background: "none", border: "none", cursor: "pointer" }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--blue)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
          >
            <RefreshCw className={cn("w-3.5 h-3.5", isFetching && "animate-spin")}
              style={{ color: isFetching ? "var(--blue)" : undefined }} />
          </button>
          <button
            style={{ padding: "6px", borderRadius: 8, color: "var(--text-3)", background: "none", border: "none", cursor: "pointer", position: "relative" }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text-1)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-3)")}
          >
            <Bell style={{ width: 14, height: 14 }} />
            <span style={{ position: "absolute", top: 5, right: 5, width: 5, height: 5, borderRadius: "50%", background: "var(--red)", boxShadow: "0 0 4px var(--red)" }} />
          </button>
        </div>
      </div>
    </div>
  );
}
