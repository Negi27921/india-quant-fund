import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "@/hooks/useTheme";
import type { Theme } from "@/hooks/useTheme";

const ACCESS_PHRASE: string = import.meta.env.VITE_AUTH_PHRASE || "One piece is real";

export const AUTH_KEY  = "iqf_matrix_auth";
export const LOCK_KEY  = "iqf_lock_until";
export const FAIL_KEY  = "iqf_fail_count";
const MAX_FAILS        = 5;
const LOCK_MS          = 15 * 60 * 1000;
const SESSION_TTL_MS   = 8  * 60 * 60 * 1000;

export function hasValidSession(): boolean {
  const raw = localStorage.getItem(AUTH_KEY);
  if (!raw) return false;
  try {
    const { ts } = JSON.parse(raw);
    return Date.now() - ts < SESSION_TTL_MS;
  } catch { return false; }
}

function isLockedOut(): boolean {
  const until = Number(localStorage.getItem(LOCK_KEY) || "0");
  if (Date.now() < until) return true;
  if (until) { localStorage.removeItem(LOCK_KEY); localStorage.removeItem(FAIL_KEY); }
  return false;
}

function recordFailure(): { locked: boolean; remaining: number } {
  const count = Number(localStorage.getItem(FAIL_KEY) || "0") + 1;
  localStorage.setItem(FAIL_KEY, String(count));
  if (count >= MAX_FAILS) {
    localStorage.setItem(LOCK_KEY, String(Date.now() + LOCK_MS));
    return { locked: true, remaining: 0 };
  }
  return { locked: false, remaining: MAX_FAILS - count };
}

function clearFailures(): void {
  localStorage.removeItem(FAIL_KEY);
  localStorage.removeItem(LOCK_KEY);
}

/* ── Types ──────────────────────────────────────────────────────────────────── */
interface Node {
  x: number; y: number; vx: number; vy: number; r: number;
  opacity: number; label?: string; isActive: boolean;
  pulsePhase: number; pulseSpeed: number;
}
interface Candle { open: number; close: number; high: number; low: number; }
interface CandleSeries {
  candles: Candle[]; x: number; y: number;
  width: number; height: number; scrollSpeed: number;
}
interface DataStream {
  x: number; tickers: string[]; offset: number; speed: number; opacity: number;
}

/* ── Neural Network Canvas ───────────────────────────────────────────────────── */
const NODE_LABELS = ["VCP", "AI", "NSE", "RSI", "EMA", "ML", "BSE", "ATR", "MFI", "OBV"];
const TICKERS = [
  "NIFTY 21842.50", "RELIANCE 2814.35", "INFY 1542.20", "HDFC 1623.90",
  "TCS 3891.00", "WIPRO 412.75", "BAJFINANCE 6923.40", "ICICIBANK 1021.60",
  "AXISBANK 1102.30", "SBIN 732.85", "HCLTECH 1234.55", "MARUTI 9821.40",
  "TATAMOTORS 892.60", "ADANIENT 2341.80", "SUNPHARMA 1456.20",
  "+0.84%", "-1.23%", "+2.17%", "-0.56%", "+1.09%",
  "21843", "21891", "21756", "21902", "21834",
];

function generateCandleSeries(canvasW: number, canvasH: number, cornerIndex: number): CandleSeries {
  const corners = [
    { x: 40, y: 60 }, { x: canvasW - 360, y: 40 },
    { x: 60, y: canvasH - 180 }, { x: canvasW - 380, y: canvasH - 200 },
  ];
  const pos = corners[cornerIndex % corners.length];
  const candles: Candle[] = [];
  let price = 100 + Math.random() * 50;
  const trend = cornerIndex % 2 === 0 ? 0.6 : -0.3;
  for (let i = 0; i < 20; i++) {
    const move = (Math.random() - 0.5 + trend * 0.1) * 4;
    const open = price;
    const close = price + move;
    const high = Math.max(open, close) + Math.random() * 2;
    const low  = Math.min(open, close) - Math.random() * 2;
    candles.push({ open, close, high, low });
    price = close;
  }
  return { candles, x: pos.x, y: pos.y, width: 280, height: 120, scrollSpeed: 0.12 + Math.random() * 0.08 };
}

interface NeuralCanvasProps { theme: Theme; hyperspeed: boolean; }

function NeuralCanvas({ theme, hyperspeed }: NeuralCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef  = useRef<{
    nodes: Node[]; series: CandleSeries[]; streams: DataStream[];
    raf: number; t: number; lastTime: number;
  } | null>(null);

  const initState = useCallback((w: number, h: number) => {
    const nodes: Node[] = Array.from({ length: 65 }, (_, i) => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4,
      r: 2.5 + Math.random() * 3, opacity: 0.3 + Math.random() * 0.7,
      label: i < NODE_LABELS.length ? NODE_LABELS[i] : undefined,
      isActive: Math.random() > 0.65,
      pulsePhase: Math.random() * Math.PI * 2, pulseSpeed: 0.02 + Math.random() * 0.03,
    }));
    const series: CandleSeries[]  = [0, 1, 2, 3].map(i => generateCandleSeries(w, h, i));
    const streams: DataStream[] = Array.from({ length: 5 }, (_, i) => ({
      x: (w / 6) * (i + 0.5) + (Math.random() - 0.5) * (w / 8),
      tickers: [...TICKERS].sort(() => Math.random() - 0.5),
      offset: Math.random() * 800, speed: 0.3 + Math.random() * 0.2,
      opacity: 0.028 + Math.random() * 0.018,
    }));
    return { nodes, series, streams, raf: 0, t: 0, lastTime: 0 };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    const isDark = theme === "dark";

    const resize = () => {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
      if (stateRef.current)
        stateRef.current.series = [0, 1, 2, 3].map(i => generateCandleSeries(canvas.width, canvas.height, i));
    };
    resize();
    if (!stateRef.current) stateRef.current = initState(canvas.width, canvas.height);
    window.addEventListener("resize", resize);

    /* ── Colour palette ── */
    const nodeColor   = isDark ? (a: number) => `rgba(167,139,250,${a})`  : (a: number) => `rgba(106,98,86,${a})`;
    const activeColor = isDark ? (a: number) => `rgba(196,181,253,${a})`  : (a: number) => `rgba(80,70,55,${a})`;
    const lineColor   = isDark ? (a: number) => `rgba(130,100,220,${a})`  : (a: number) => `rgba(106,98,86,${a})`;
    const bgFrom      = isDark ? "#06060b" : "#EBE7E7";
    const bgTo        = isDark ? "#0b0b14" : "#DAD8D8";
    const candleUp    = isDark ? "rgba(52,211,153,0.14)"  : "rgba(80,70,55,0.12)";
    const candleDown  = isDark ? "rgba(248,113,113,0.11)" : "rgba(180,80,60,0.08)";
    const streamColor = isDark ? "rgba(167,139,250," : "rgba(106,98,86,";

    const draw = (timestamp: number) => {
      const state = stateRef.current!;
      const delta = timestamp - state.lastTime;
      if (delta < 14) { state.raf = requestAnimationFrame(draw); return; }
      state.lastTime = timestamp;
      state.t += 1;
      const w = canvas.width; const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      /* Background */
      const bg = ctx.createLinearGradient(0, 0, w, h);
      bg.addColorStop(0, bgFrom); bg.addColorStop(1, bgTo);
      ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);

      /* Subtle grid */
      ctx.strokeStyle = isDark ? `rgba(167,139,250,0.025)` : `rgba(106,98,86,0.025)`;
      ctx.lineWidth = 0.5;
      for (let gx = 0; gx < w; gx += 20) { ctx.beginPath(); ctx.moveTo(gx,0); ctx.lineTo(gx,h); ctx.stroke(); }
      for (let gy = 0; gy < h; gy += 20) { ctx.beginPath(); ctx.moveTo(0,gy); ctx.lineTo(w,gy); ctx.stroke(); }

      /* Data streams */
      ctx.font = "9px 'JetBrains Mono', monospace";
      for (const stream of state.streams) {
        stream.offset += stream.speed;
        ctx.fillStyle = `${streamColor}${stream.opacity})`;
        const lh = 16;
        for (let i = 0; i < Math.ceil(h / lh) + 2; i++) {
          const yPos = ((i * lh - stream.offset) % (stream.tickers.length * lh) + h) % h;
          const idx  = Math.floor(i + stream.offset / lh) % stream.tickers.length;
          ctx.fillText(stream.tickers[(idx + stream.tickers.length) % stream.tickers.length], stream.x, yPos);
        }
      }

      /* Candlestick ghosts */
      for (const series of state.series) {
        series.x -= series.scrollSpeed;
        if (series.x + series.width < -50) series.x = w + 50;
        const prices = series.candles.map(c => [c.low, c.high]).flat();
        const minP = Math.min(...prices), maxP = Math.max(...prices), range = maxP - minP || 1;
        const cw = series.width / series.candles.length;
        const scaleY = (p: number) => series.y + series.height - ((p - minP) / range) * series.height;
        for (let ci = 0; ci < series.candles.length; ci++) {
          const c = series.candles[ci];
          const cx = series.x + ci * cw + cw * 0.15, bw = cw * 0.6;
          const isUp = c.close >= c.open;
          ctx.strokeStyle = isUp ? candleUp : candleDown;
          ctx.fillStyle   = isUp ? candleUp : candleDown;
          ctx.lineWidth = 0.5;
          ctx.beginPath(); ctx.moveTo(cx+bw/2, scaleY(c.high)); ctx.lineTo(cx+bw/2, scaleY(c.low)); ctx.stroke();
          ctx.fillRect(cx, scaleY(Math.max(c.open, c.close)), bw, Math.max(1, Math.abs(scaleY(c.open)-scaleY(c.close))));
        }
      }

      /* Connections + travelling dots */
      const spd = hyperspeed ? 8 : 1;
      for (let i = 0; i < state.nodes.length; i++) {
        for (let j = i + 1; j < state.nodes.length; j++) {
          const a = state.nodes[i], b = state.nodes[j];
          const dx = a.x-b.x, dy = a.y-b.y, dist = Math.sqrt(dx*dx+dy*dy);
          if (dist < 150) {
            const alpha = (1 - dist / 150) * 0.20;
            ctx.strokeStyle = lineColor(alpha); ctx.lineWidth = 0.6;
            ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
            const tp = ((state.t * spd * 0.008 + i * 0.3 + j * 0.17) % 1);
            const da = alpha * 2.5 * Math.sin(tp * Math.PI);
            ctx.fillStyle = lineColor(da);
            ctx.beginPath(); ctx.arc(a.x+(b.x-a.x)*tp, a.y+(b.y-a.y)*tp, 1.2, 0, Math.PI*2); ctx.fill();
          }
        }
      }

      /* Nodes */
      for (const node of state.nodes) {
        node.x += node.vx * spd; node.y += node.vy * spd;
        if (node.x < 0 || node.x > w) node.vx *= -1;
        if (node.y < 0 || node.y > h) node.vy *= -1;
        node.pulsePhase += node.pulseSpeed;
        const pulse = node.isActive ? 0.5 + 0.5 * Math.sin(node.pulsePhase) : 0;
        const glow  = node.isActive ? (hyperspeed ? 24 : 12) : 0;
        const base  = hyperspeed ? Math.min(1, node.opacity * 2.5) : node.opacity;
        if (node.isActive && glow > 0) {
          const g = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, node.r + glow);
          g.addColorStop(0, activeColor(0.35 * pulse * (hyperspeed ? 2 : 1)));
          g.addColorStop(1, activeColor(0));
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(node.x, node.y, node.r + glow, 0, Math.PI*2); ctx.fill();
        }
        ctx.fillStyle = node.isActive ? activeColor(base) : nodeColor(base * 0.7);
        ctx.beginPath(); ctx.arc(node.x, node.y, node.r, 0, Math.PI*2); ctx.fill();
        if (node.label && !hyperspeed) {
          ctx.fillStyle = nodeColor(0.3);
          ctx.font = "7px 'JetBrains Mono', monospace";
          ctx.fillText(node.label, node.x + node.r + 3, node.y + 3);
        }
      }
      state.raf = requestAnimationFrame(draw);
    };
    stateRef.current.raf = requestAnimationFrame(draw);
    return () => {
      if (stateRef.current) cancelAnimationFrame(stateRef.current.raf);
      window.removeEventListener("resize", resize);
    };
  }, [theme, hyperspeed, initState]);

  return <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, display: "block" }} />;
}

/* ── AI Agent Status Panel ──────────────────────────────────────────────────── */
type AgentState = "ACTIVE" | "SCANNING" | "READY" | "LOADING" | "STANDBY";
interface Agent { name: string; states: AgentState[]; currentState: AgentState; dotColor: string; }

const AGENT_CONFIGS: Omit<Agent, "currentState">[] = [
  { name: "VCP Engine", states: ["ACTIVE",   "LOADING",  "ACTIVE"],            dotColor: "#34d399" },
  { name: "Screener",   states: ["SCANNING", "LOADING",  "SCANNING","STANDBY"], dotColor: "#f59e0b" },
  { name: "Risk Mgmt",  states: ["READY",    "ACTIVE",   "READY"],             dotColor: "#34d399" },
];

function AgentStatusPanel({ theme }: { theme: Theme }) {
  const isDark = theme === "dark";
  const [agents, setAgents] = useState<Agent[]>(
    AGENT_CONFIGS.map(a => ({ ...a, currentState: a.states[0] as AgentState }))
  );

  useEffect(() => {
    const ids = agents.map((__a, i) => {
      let idx = 0;
      const delay = 3000 + i * 1400 + Math.random() * 2000;
      return window.setInterval(() => {
        idx = (idx + 1) % AGENT_CONFIGS[i].states.length;
        setAgents(prev => {
          const next = [...prev];
          next[i] = { ...next[i], currentState: AGENT_CONFIGS[i].states[idx] as AgentState };
          return next;
        });
      }, delay);
    });
    return () => ids.forEach(clearInterval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dotStyle = (color: string, state: AgentState): React.CSSProperties => ({
    width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
    background: state === "LOADING" ? "rgba(255,255,255,0.18)" : color,
    boxShadow: state !== "LOADING" ? `0 0 6px ${color}99` : "none",
    animation: state === "SCANNING"
      ? "agentPulseSlow 2s ease-in-out infinite"
      : state === "ACTIVE" ? "agentPulseFast 1.2s ease-in-out infinite" : "none",
  });

  const stateColor = (s: AgentState) => {
    if (s === "ACTIVE")   return isDark ? "#34d399" : "#16a34a";
    if (s === "SCANNING") return isDark ? "#f59e0b" : "#d97706";
    if (s === "READY")    return isDark ? "#60a5fa" : "#2563eb";
    if (s === "LOADING")  return "rgba(255,255,255,0.22)";
    return "rgba(255,255,255,0.18)";
  };

  return (
    <>
      <style>{`
        @keyframes agentPulseFast { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(1.3)} }
        @keyframes agentPulseSlow { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.3;transform:scale(1.2)} }
      `}</style>
      <div style={{
        background: isDark ? "rgba(255,255,255,0.025)" : "rgba(0,0,0,0.025)",
        border: isDark ? "1px solid rgba(255,255,255,0.06)" : "1px solid rgba(17,16,14,0.09)",
        borderRadius: 10, padding: "10px 14px", marginBottom: 20,
      }}>
        <div style={{
          fontSize: 9, fontFamily: "var(--font-mono)", letterSpacing: "0.14em",
          textTransform: "uppercase", marginBottom: 10,
          color: isDark ? "rgba(167,139,250,0.55)" : "rgba(106,98,86,0.65)",
        }}>
          AI Agent Status
        </div>
        {agents.map((agent, i) => (
          <motion.div key={agent.name}
            initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.6 + i * 0.15, duration: 0.4 }}
            style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom: i < agents.length-1 ? 8 : 0 }}
          >
            <div style={{ display:"flex", alignItems:"center", gap: 8 }}>
              <div style={dotStyle(agent.dotColor, agent.currentState)} />
              <span style={{ fontSize:11, fontFamily:"var(--font-mono)", color: isDark ? "rgba(245,245,247,0.65)" : "rgba(17,16,14,0.65)" }}>
                {agent.name}
              </span>
            </div>
            <span style={{ fontSize:9, fontFamily:"var(--font-mono)", letterSpacing:"0.1em", fontWeight:600, color: stateColor(agent.currentState) }}>
              {agent.currentState}
            </span>
          </motion.div>
        ))}
      </div>
    </>
  );
}

/* ── Login Page ─────────────────────────────────────────────────────────────── */
export function LoginPage({ onAuth }: { onAuth: () => void }) {
  const { theme }  = useTheme();
  const isDark     = theme === "dark";

  const [phrase,   setPhrase]   = useState("");
  const [error,    setError]    = useState(false);
  const [errorMsg, setErrorMsg] = useState("Incorrect passphrase. Try again.");
  const [shake,    setShake]    = useState(false);
  const [granted,  setGranted]  = useState(false);
  const [locked,   setLocked]   = useState(isLockedOut);
  const [hyperspeed, setHyperspeed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 400); }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isLockedOut()) {
      setLocked(true); setError(true);
      setErrorMsg("Terminal locked — try again in 15 minutes.");
      setPhrase(""); return;
    }
    if (phrase.trim().toLowerCase() === ACCESS_PHRASE.toLowerCase()) {
      clearFailures(); setGranted(true); setHyperspeed(true);
      setTimeout(() => { localStorage.setItem(AUTH_KEY, JSON.stringify({ ts: Date.now() })); onAuth(); }, 1600);
    } else {
      const result = recordFailure();
      setError(true); setShake(true);
      setErrorMsg(result.locked
        ? "Terminal locked — too many failed attempts."
        : `Incorrect passphrase — ${result.remaining} attempt${result.remaining !== 1 ? "s" : ""} left.`);
      if (result.locked) setLocked(true);
      setTimeout(() => setShake(false), 400);
      setTimeout(() => { setError(false); setErrorMsg("Incorrect passphrase. Try again."); }, 3000);
      setPhrase("");
    }
  };

  const btnDisabled = locked || granted || !phrase.trim();

  return (
    <div style={{
      position: "relative", width: "100vw", height: "100vh",
      overflow: "hidden", background: isDark ? "#06060b" : "#EBE7E7",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      {/* Layer 0 — neural canvas */}
      <NeuralCanvas theme={theme} hyperspeed={hyperspeed} />

      {/* Layer 1 — grid dot overlay (dark only via CSS [data-theme]) */}
      <div className="grid-bg" />

      {/* Layer 2 — violet top glow */}
      <div className="glow-top" />

      {/* ── Login card ── */}
      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.96 }}
        animate={granted
          ? { opacity: 0, y: -20, scale: 1.04 }
          : { opacity: 1, y: 0, scale: 1 }}
        transition={granted
          ? { duration: 0.5, ease: [0.4,0,0.2,1] }
          : { type: "spring", stiffness: 280, damping: 26, delay: 0.15 }}
        style={{ position: "relative", zIndex: 10, width: "min(420px, calc(100vw - 40px))" }}
      >
        <motion.div
          animate={{ x: shake ? [-10,10,-7,7,-4,4,0] : 0 }}
          transition={{ duration: 0.4 }}
          style={{
            background: isDark
              ? "linear-gradient(160deg, rgba(255,255,255,0.055) 0%, rgba(255,255,255,0.02) 100%)"
              : "rgba(248,247,246,0.94)",
            border: error
              ? "1px solid rgba(248,113,113,0.38)"
              : isDark ? "1px solid rgba(255,255,255,0.09)" : "1px solid rgba(17,16,14,0.12)",
            borderRadius: 22,
            padding: "28px 28px 24px",
            boxShadow: error
              ? "0 24px 64px rgba(248,113,113,0.12), inset 0 1px 0 rgba(255,255,255,0.04)"
              : isDark
                ? "0 40px 80px rgba(0,0,0,0.92), 0 0 0 1px rgba(167,139,250,0.07), inset 0 1px 0 rgba(255,255,255,0.07)"
                : "0 20px 60px rgba(17,16,14,0.12)",
            backdropFilter: "blur(56px)",
            WebkitBackdropFilter: "blur(56px)",
            transition: "border-color 300ms, box-shadow 300ms",
            position: "relative", overflow: "hidden",
          }}
        >
          {/* Card top accent line */}
          {isDark && (
            <div style={{
              position: "absolute", top: 0, left: 0, right: 0, height: 1,
              background: "linear-gradient(90deg, transparent, rgba(167,139,250,0.55) 40%, rgba(96,165,250,0.35) 70%, transparent)",
              pointerEvents: "none",
            }} />
          )}

          {/* ── Header bar ── */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 24, paddingBottom: 16,
            borderBottom: isDark ? "1px solid rgba(255,255,255,0.06)" : "1px solid rgba(17,16,14,0.08)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <img
                src="/favicon.svg"
                alt="One Piece Quant"
                style={{ width: 22, height: 22, borderRadius: 5, flexShrink: 0 }}
              />
              <span style={{
                fontFamily: "var(--font-heading)", fontStyle: "italic", fontSize: 13,
                color: isDark ? "rgba(245,245,247,0.82)" : "rgba(17,16,14,0.78)",
                letterSpacing: "0.01em",
              }}>
                One Piece Quant
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <div style={{
                width: 6, height: 6, borderRadius: "50%", background: "#34d399",
                boxShadow: "0 0 8px #34d39999",
                animation: "agentPulseFast 1.2s ease-in-out infinite",
              }} />
              <span style={{
                fontSize: 9, fontFamily: "var(--font-mono)", letterSpacing: "0.12em",
                color: isDark ? "rgba(167,139,250,0.5)" : "rgba(106,98,86,0.58)",
                fontWeight: 600,
              }}>
                ONLINE
              </span>
            </div>
          </div>

          {/* ── Brand ── */}
          <div style={{ textAlign: "center", marginBottom: 22 }}>
            {/* Logo icon */}
            <motion.div
              initial={{ scale: 0.75, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 380, damping: 22, delay: 0.25 }}
              style={{
                width: 60, height: 60, borderRadius: 17, margin: "0 auto 16px",
                display: "flex", alignItems: "center", justifyContent: "center",
                background: isDark
                  ? "linear-gradient(135deg, rgba(167,139,250,0.15) 0%, rgba(96,165,250,0.08) 100%)"
                  : "linear-gradient(135deg, rgba(106,98,86,0.10) 0%, rgba(80,72,60,0.18) 100%)",
                border: isDark
                  ? "1px solid rgba(167,139,250,0.2)"
                  : "1px solid rgba(106,98,86,0.16)",
                boxShadow: isDark
                  ? "0 8px 32px rgba(0,0,0,0.65), 0 0 0 1px rgba(167,139,250,0.08), 0 0 48px rgba(167,139,250,0.1)"
                  : "0 8px 24px rgba(106,98,86,0.14)",
              }}
            >
              <img src="/favicon.svg" alt="One Piece" style={{ width: 36, height: 36 }} />
            </motion.div>

            {/* Title */}
            <div style={{
              fontFamily: "var(--font-heading)", fontStyle: "italic",
              fontSize: 27, letterSpacing: "-0.02em", lineHeight: 1.1, marginBottom: 5,
              color: isDark ? "#f5f5f7" : "#11100E",
            }}>
              One Piece{" "}
              <span style={{
                background: "linear-gradient(120deg, #a78bfa 0%, #60a5fa 55%, #34d399 100%)",
                WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
              }}>
                Quant
              </span>
            </div>

            {/* Tagline */}
            <div style={{
              fontSize: 9.5, fontFamily: "var(--font-mono)", fontWeight: 500,
              letterSpacing: "0.16em", textTransform: "uppercase",
              color: isDark ? "rgba(167,139,250,0.45)" : "rgba(106,98,86,0.52)",
            }}>
              NSE · BSE · AI Terminal
            </div>
          </div>

          {/* ── Agent Status ── */}
          <AgentStatusPanel theme={theme} />

          {/* ── Form ── */}
          <form onSubmit={handleSubmit} autoComplete="off">
            <div style={{ marginBottom: 14 }}>
              <label style={{
                display: "block", marginBottom: 7, fontSize: 10, fontWeight: 600,
                fontFamily: "var(--font-mono)", letterSpacing: "0.09em", textTransform: "uppercase",
                color: error ? "#f87171" : isDark ? "rgba(167,139,250,0.6)" : "rgba(106,98,86,0.68)",
                transition: "color 200ms",
              }}>
                {locked ? "⚠ Terminal locked" : error ? errorMsg : "Enter passphrase"}
              </label>
              <input
                ref={inputRef}
                type="password"
                value={phrase}
                disabled={locked || granted}
                onChange={e => { setPhrase(e.target.value); if (error) setError(false); }}
                placeholder="••••••••••••••••"
                autoComplete="new-password"
                style={{
                  width: "100%",
                  background: error
                    ? (isDark ? "rgba(248,113,113,0.08)" : "rgba(248,113,113,0.05)")
                    : (isDark ? "rgba(255,255,255,0.045)" : "rgba(248,247,246,0.9)"),
                  border: error
                    ? "1.5px solid rgba(248,113,113,0.45)"
                    : (isDark ? "1.5px solid rgba(255,255,255,0.09)" : "1.5px solid rgba(17,16,14,0.14)"),
                  borderRadius: 11, padding: "13px 14px",
                  fontSize: 16, fontFamily: "var(--font-mono)",
                  color: error ? "#f87171" : (isDark ? "#f5f5f7" : "#11100E"),
                  outline: "none", letterSpacing: "0.22em",
                  transition: "border-color 200ms, box-shadow 200ms, background 200ms",
                  boxSizing: "border-box", caretColor: "var(--accent)",
                }}
                onFocus={e => {
                  if (!error) {
                    e.target.style.borderColor = isDark ? "rgba(167,139,250,0.4)" : "rgba(106,98,86,0.42)";
                    e.target.style.boxShadow   = isDark ? "0 0 0 3px rgba(167,139,250,0.11)" : "0 0 0 3px rgba(106,98,86,0.09)";
                    e.target.style.background  = isDark ? "rgba(255,255,255,0.06)" : "rgba(248,247,246,1)";
                  }
                }}
                onBlur={e => {
                  if (!error) {
                    e.target.style.borderColor = isDark ? "rgba(255,255,255,0.09)" : "rgba(17,16,14,0.14)";
                    e.target.style.boxShadow   = "none";
                    e.target.style.background  = isDark ? "rgba(255,255,255,0.045)" : "rgba(248,247,246,0.9)";
                  }
                }}
              />
            </div>

            <motion.button
              type="submit"
              disabled={btnDisabled}
              whileHover={!btnDisabled ? { y: -2, scale: 1.01 } : {}}
              whileTap={!btnDisabled ? { scale: 0.98 } : {}}
              style={{
                width: "100%", border: "none", borderRadius: 9999,
                padding: "13px 0", fontSize: 12, fontWeight: 700,
                fontFamily: "var(--font-body)", letterSpacing: "0.1em", textTransform: "uppercase",
                cursor: btnDisabled ? "not-allowed" : "pointer",
                transition: "all 220ms",
                background: btnDisabled
                  ? (isDark ? "rgba(255,255,255,0.06)" : "rgba(17,16,14,0.07)")
                  : "linear-gradient(135deg, #a78bfa 0%, #818cf8 50%, #60a5fa 100%)",
                color: btnDisabled
                  ? (isDark ? "rgba(255,255,255,0.2)" : "rgba(17,16,14,0.25)")
                  : "#ffffff",
                boxShadow: !btnDisabled
                  ? "0 4px 28px rgba(167,139,250,0.45), 0 0 0 1px rgba(167,139,250,0.18)"
                  : "none",
              }}
            >
              {granted ? "Initialising terminal…" : locked ? "Terminal locked" : "Access Terminal"}
            </motion.button>
          </form>

          {/* ── Footer ── */}
          <div style={{
            marginTop: 18, paddingTop: 14,
            borderTop: isDark ? "1px solid rgba(255,255,255,0.05)" : "1px solid rgba(17,16,14,0.06)",
            display: "flex", justifyContent: "center",
          }}>
            <span style={{
              fontSize: 10, fontFamily: "var(--font-mono)",
              color: isDark ? "rgba(255,255,255,0.18)" : "rgba(17,16,14,0.28)",
              letterSpacing: "0.04em",
            }}>
              Authorized access only · All activity logged
            </span>
          </div>
        </motion.div>
      </motion.div>

      {/* ── Access granted overlay ── */}
      <AnimatePresence>
        {granted && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: [0, 0.45, 0] }}
              transition={{ duration: 0.5, times: [0, 0.2, 1] }}
              style={{ position:"absolute", inset:0, zIndex:15, background:"#a78bfa", pointerEvents:"none" }}
            />
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ delay: 0.3, duration: 0.4 }}
              style={{
                position:"absolute", inset:0, zIndex:20,
                display:"flex", alignItems:"center", justifyContent:"center",
                background: isDark ? "rgba(6,6,11,0.88)" : "rgba(235,231,231,0.88)",
                backdropFilter:"blur(24px)", WebkitBackdropFilter:"blur(24px)",
              }}
            >
              <motion.div
                initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                transition={{ type:"spring", stiffness:350, damping:22, delay:0.35 }}
                style={{ textAlign:"center" }}
              >
                <motion.div
                  initial={{ scale: 0 }} animate={{ scale: [0, 1.2, 1] }}
                  transition={{ delay: 0.4, duration: 0.5, ease: "easeOut" }}
                  style={{
                    width:72, height:72, borderRadius:"50%",
                    background:"linear-gradient(135deg, #a78bfa 0%, #60a5fa 50%, #34d399 100%)",
                    display:"flex", alignItems:"center", justifyContent:"center",
                    margin:"0 auto 20px",
                    boxShadow:"0 8px 48px rgba(167,139,250,0.55)",
                    fontSize:30, color:"#fff",
                  }}
                >
                  ✓
                </motion.div>
                <motion.div
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.6 }}
                  style={{
                    fontSize:18, fontWeight:700,
                    fontFamily:"var(--font-heading)", fontStyle:"italic",
                    color: isDark ? "#f5f5f7" : "#11100E", letterSpacing:"-0.01em",
                  }}
                >
                  Access granted
                </motion.div>
                <motion.div
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  transition={{ delay: 0.75 }}
                  style={{
                    fontSize:11, fontFamily:"var(--font-mono)",
                    color: isDark ? "rgba(167,139,250,0.65)" : "rgba(106,98,86,0.65)",
                    marginTop:6, letterSpacing:"0.06em",
                  }}
                >
                  Initialising terminal…
                </motion.div>
              </motion.div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
