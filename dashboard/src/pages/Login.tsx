import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "@/hooks/useTheme";
import type { Theme } from "@/hooks/useTheme";

// Password from build-time env — set VITE_AUTH_PHRASE in Vercel.
const ACCESS_PHRASE: string = import.meta.env.VITE_AUTH_PHRASE || "One piece is real";

export const AUTH_KEY  = "iqf_matrix_auth";
export const LOCK_KEY  = "iqf_lock_until";
export const FAIL_KEY  = "iqf_fail_count";
const MAX_FAILS       = 5;
const LOCK_MS         = 15 * 60 * 1000;
const SESSION_TTL_MS  = 8  * 60 * 60 * 1000;

export function hasValidSession(): boolean {
  const raw = localStorage.getItem(AUTH_KEY);
  if (!raw) return false;
  try {
    const { ts } = JSON.parse(raw);
    return Date.now() - ts < SESSION_TTL_MS;
  } catch {
    return false;
  }
}

function isLockedOut(): boolean {
  const until = Number(localStorage.getItem(LOCK_KEY) || "0");
  if (Date.now() < until) return true;
  if (until) {
    localStorage.removeItem(LOCK_KEY);
    localStorage.removeItem(FAIL_KEY);
  }
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

/* ── Types ─────────────────────────────────────────────────────────────────── */
interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  opacity: number;
  label?: string;
  isActive: boolean;
  pulsePhase: number;
  pulseSpeed: number;
}

interface Candle {
  open: number;
  close: number;
  high: number;
  low: number;
}

interface CandleSeries {
  candles: Candle[];
  x: number;
  y: number;
  width: number;
  height: number;
  scrollSpeed: number;
}

interface DataStream {
  x: number;
  tickers: string[];
  offset: number;
  speed: number;
  opacity: number;
}

/* ── Neural Network Canvas ─────────────────────────────────────────────────── */
const NODE_LABELS = ["VCP", "AI", "NSE", "RSI", "EMA", "ML", "BSE", "ATR", "MFI", "OBV"];
const TICKERS = [
  "NIFTY 21842.50", "RELIANCE 2814.35", "INFY 1542.20", "HDFC 1623.90",
  "TCS 3891.00", "WIPRO 412.75", "BAJFINANCE 6923.40", "ICICIBANK 1021.60",
  "AXISBANK 1102.30", "SBIN 732.85", "HCLTECH 1234.55", "MARUTI 9821.40",
  "TATAMOTORS 892.60", "ADANIENT 2341.80", "SUNPHARMA 1456.20",
  "+0.84%", "-1.23%", "+2.17%", "-0.56%", "+1.09%",
  "21843", "21891", "21756", "21902", "21834",
];

function generateCandleSeries(
  canvasW: number,
  canvasH: number,
  cornerIndex: number
): CandleSeries {
  const corners = [
    { x: 40, y: 60 },
    { x: canvasW - 360, y: 40 },
    { x: 60, y: canvasH - 180 },
    { x: canvasW - 380, y: canvasH - 200 },
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
    const low = Math.min(open, close) - Math.random() * 2;
    candles.push({ open, close, high, low });
    price = close;
  }
  return {
    candles,
    x: pos.x,
    y: pos.y,
    width: 280,
    height: 120,
    scrollSpeed: 0.12 + Math.random() * 0.08,
  };
}

interface NeuralCanvasProps {
  theme: Theme;
  hyperspeed: boolean;
}

function NeuralCanvas({ theme, hyperspeed }: NeuralCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<{
    nodes: Node[];
    series: CandleSeries[];
    streams: DataStream[];
    raf: number;
    t: number;
    lastTime: number;
  } | null>(null);

  const initState = useCallback((w: number, h: number) => {
    const nodes: Node[] = Array.from({ length: 65 }, (_, i) => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: 2.5 + Math.random() * 3,
      opacity: 0.3 + Math.random() * 0.7,
      label: i < NODE_LABELS.length ? NODE_LABELS[i] : undefined,
      isActive: Math.random() > 0.65,
      pulsePhase: Math.random() * Math.PI * 2,
      pulseSpeed: 0.02 + Math.random() * 0.03,
    }));

    const series: CandleSeries[] = [0, 1, 2, 3].map(i =>
      generateCandleSeries(w, h, i)
    );

    const streams: DataStream[] = Array.from({ length: 5 }, (_, i) => ({
      x: (w / 6) * (i + 0.5) + (Math.random() - 0.5) * (w / 8),
      tickers: [...TICKERS].sort(() => Math.random() - 0.5),
      offset: Math.random() * 800,
      speed: 0.3 + Math.random() * 0.2,
      opacity: 0.035 + Math.random() * 0.025,
    }));

    return { nodes, series, streams, raf: 0, t: 0, lastTime: 0 };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;

    const isDark = theme === "dark";

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      if (stateRef.current) {
        stateRef.current.series = [0, 1, 2, 3].map(i =>
          generateCandleSeries(canvas.width, canvas.height, i)
        );
      }
    };
    resize();

    if (!stateRef.current) {
      stateRef.current = initState(canvas.width, canvas.height);
    }

    window.addEventListener("resize", resize);

    const nodeColor = isDark
      ? (a: number) => `rgba(160,148,127,${a})`
      : (a: number) => `rgba(106,98,86,${a})`;
    const activeColor = isDark
      ? (a: number) => `rgba(200,185,158,${a})`
      : (a: number) => `rgba(80,70,55,${a})`;
    const lineColor = isDark
      ? (a: number) => `rgba(160,148,127,${a})`
      : (a: number) => `rgba(106,98,86,${a})`;
    const bgFrom = isDark ? "#0F0E0C" : "#EBE7E7";
    const bgTo = isDark ? "#161411" : "#DAD8D8";
    const candleUp = isDark ? "rgba(160,148,127,0.18)" : "rgba(80,70,55,0.12)";
    const candleDown = isDark ? "rgba(200,100,80,0.12)" : "rgba(180,80,60,0.08)";
    const streamColor = isDark ? "rgba(160,148,127," : "rgba(106,98,86,";

    const draw = (timestamp: number) => {
      const state = stateRef.current!;
      const delta = timestamp - state.lastTime;
      if (delta < 14) {
        state.raf = requestAnimationFrame(draw);
        return;
      }
      state.lastTime = timestamp;
      state.t += 1;

      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      // Background gradient
      const bg = ctx.createLinearGradient(0, 0, w, h);
      bg.addColorStop(0, bgFrom);
      bg.addColorStop(1, bgTo);
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      // Grid overlay
      const gridOpacity = isDark ? 0.04 : 0.025;
      ctx.strokeStyle = isDark
        ? `rgba(160,148,127,${gridOpacity})`
        : `rgba(106,98,86,${gridOpacity})`;
      ctx.lineWidth = 0.5;
      for (let gx = 0; gx < w; gx += 20) {
        ctx.beginPath();
        ctx.moveTo(gx, 0);
        ctx.lineTo(gx, h);
        ctx.stroke();
      }
      for (let gy = 0; gy < h; gy += 20) {
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(w, gy);
        ctx.stroke();
      }

      // Data streams
      ctx.font = "9px 'JetBrains Mono', monospace";
      for (const stream of state.streams) {
        stream.offset += stream.speed;
        ctx.fillStyle = `${streamColor}${stream.opacity})`;
        const lineHeight = 16;
        for (let i = 0; i < Math.ceil(h / lineHeight) + 2; i++) {
          const yPos = ((i * lineHeight - stream.offset) % (stream.tickers.length * lineHeight) + h) % h;
          const tickerIdx = Math.floor(i + stream.offset / lineHeight) % stream.tickers.length;
          const ticker = stream.tickers[(tickerIdx + stream.tickers.length) % stream.tickers.length];
          ctx.fillText(ticker, stream.x, yPos);
        }
      }

      // Candlestick ghosts
      for (const series of state.series) {
        series.x -= series.scrollSpeed;
        if (series.x + series.width < -50) {
          series.x = w + 50;
        }

        const prices = series.candles.map(c => [c.low, c.high]).flat();
        const minP = Math.min(...prices);
        const maxP = Math.max(...prices);
        const range = maxP - minP || 1;
        const candleW = series.width / series.candles.length;
        const scaleY = (p: number) =>
          series.y + series.height - ((p - minP) / range) * series.height;

        for (let ci = 0; ci < series.candles.length; ci++) {
          const c = series.candles[ci];
          const cx = series.x + ci * candleW + candleW * 0.15;
          const bodyW = candleW * 0.6;
          const isUp = c.close >= c.open;

          ctx.strokeStyle = isUp ? candleUp : candleDown;
          ctx.fillStyle = isUp ? candleUp : candleDown;
          ctx.lineWidth = 0.5;

          // Wick
          ctx.beginPath();
          ctx.moveTo(cx + bodyW / 2, scaleY(c.high));
          ctx.lineTo(cx + bodyW / 2, scaleY(c.low));
          ctx.stroke();

          // Body
          const bodyTop = scaleY(Math.max(c.open, c.close));
          const bodyH = Math.max(1, Math.abs(scaleY(c.open) - scaleY(c.close)));
          ctx.fillRect(cx, bodyTop, bodyW, bodyH);
        }
      }

      // Connections
      const speedMult = hyperspeed ? 8 : 1;
      for (let i = 0; i < state.nodes.length; i++) {
        for (let j = i + 1; j < state.nodes.length; j++) {
          const a = state.nodes[i];
          const b = state.nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const maxDist = 150;
          if (dist < maxDist) {
            const alpha = (1 - dist / maxDist) * 0.25;
            ctx.strokeStyle = lineColor(alpha);
            ctx.lineWidth = 0.6;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();

            // Travelling dot
            const travelPhase = ((state.t * speedMult * 0.008 + i * 0.3 + j * 0.17) % 1);
            const dotX = a.x + (b.x - a.x) * travelPhase;
            const dotY = a.y + (b.y - a.y) * travelPhase;
            const dotAlpha = alpha * 2.5 * Math.sin(travelPhase * Math.PI);
            ctx.fillStyle = lineColor(dotAlpha);
            ctx.beginPath();
            ctx.arc(dotX, dotY, 1.2, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // Nodes
      for (const node of state.nodes) {
        const spd = hyperspeed ? speedMult : 1;
        node.x += node.vx * spd;
        node.y += node.vy * spd;
        if (node.x < 0 || node.x > w) node.vx *= -1;
        if (node.y < 0 || node.y > h) node.vy *= -1;
        node.pulsePhase += node.pulseSpeed;

        const pulse = node.isActive
          ? 0.5 + 0.5 * Math.sin(node.pulsePhase)
          : 0;
        const glow = node.isActive ? (hyperspeed ? 24 : 12) : 0;
        const baseOpacity = hyperspeed
          ? Math.min(1, node.opacity * 2.5)
          : node.opacity;

        if (node.isActive && glow > 0) {
          const glowGrad = ctx.createRadialGradient(
            node.x, node.y, 0,
            node.x, node.y, node.r + glow
          );
          glowGrad.addColorStop(0, activeColor(0.35 * pulse * (hyperspeed ? 2 : 1)));
          glowGrad.addColorStop(1, activeColor(0));
          ctx.fillStyle = glowGrad;
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.r + glow, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.fillStyle = node.isActive
          ? activeColor(baseOpacity)
          : nodeColor(baseOpacity * 0.7);
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
        ctx.fill();

        if (node.label && !hyperspeed) {
          ctx.fillStyle = nodeColor(0.45);
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

  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", inset: 0, display: "block" }}
    />
  );
}

/* ── AI Agent Status Panel ─────────────────────────────────────────────────── */
type AgentState = "ACTIVE" | "SCANNING" | "READY" | "LOADING" | "STANDBY";

interface Agent {
  name: string;
  states: AgentState[];
  currentState: AgentState;
  dotColor: string;
}

const AGENT_CONFIGS: Omit<Agent, "currentState">[] = [
  {
    name: "VCP Engine",
    states: ["ACTIVE", "LOADING", "ACTIVE"],
    dotColor: "#4ade80",
  },
  {
    name: "Screener",
    states: ["SCANNING", "LOADING", "SCANNING", "STANDBY"],
    dotColor: "#fbbf24",
  },
  {
    name: "Risk Mgmt",
    states: ["READY", "ACTIVE", "READY"],
    dotColor: "#4ade80",
  },
];

function AgentStatusPanel({ theme }: { theme: Theme }) {
  const isDark = theme === "dark";
  const [agents, setAgents] = useState<Agent[]>(
    AGENT_CONFIGS.map(a => ({ ...a, currentState: a.states[0] as AgentState }))
  );

  useEffect(() => {
    const intervals = agents.map((__agent, i) => {
      let stateIdx = 0;
      const delay = 3000 + i * 1400 + Math.random() * 2000;
      const tick = () => {
        stateIdx = (stateIdx + 1) % AGENT_CONFIGS[i].states.length;
        setAgents(prev => {
          const next = [...prev];
          next[i] = { ...next[i], currentState: AGENT_CONFIGS[i].states[stateIdx] as AgentState };
          return next;
        });
      };
      const id = window.setInterval(tick, delay);
      return id;
    });
    return () => intervals.forEach(clearInterval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dotStyle = (color: string, state: AgentState): React.CSSProperties => ({
    width: 7,
    height: 7,
    borderRadius: "50%",
    background: state === "LOADING" ? (isDark ? "#64748b" : "#94a3b8") : color,
    flexShrink: 0,
    boxShadow: state !== "LOADING" ? `0 0 6px ${color}88` : "none",
    animation: state === "SCANNING"
      ? "agentPulseSlow 2s ease-in-out infinite"
      : state === "ACTIVE"
        ? "agentPulseFast 1.2s ease-in-out infinite"
        : "none",
  });

  const stateColor = (state: AgentState): string => {
    if (state === "ACTIVE") return isDark ? "#4ade80" : "#16a34a";
    if (state === "SCANNING") return isDark ? "#fbbf24" : "#d97706";
    if (state === "READY") return isDark ? "#60a5fa" : "#2563eb";
    if (state === "LOADING") return isDark ? "#64748b" : "#94a3b8";
    return isDark ? "#94a3b8" : "#64748b";
  };

  return (
    <>
      <style>{`
        @keyframes agentPulseFast {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.3); }
        }
        @keyframes agentPulseSlow {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(1.2); }
        }
      `}</style>
      <div style={{
        background: isDark
          ? "rgba(15,14,12,0.6)"
          : "rgba(220,216,210,0.55)",
        border: isDark
          ? "1px solid rgba(160,148,127,0.12)"
          : "1px solid rgba(106,98,86,0.12)",
        borderRadius: 10,
        padding: "10px 14px",
        marginBottom: 20,
      }}>
        <div style={{
          fontSize: 9,
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          color: isDark ? "rgba(160,148,127,0.7)" : "rgba(106,98,86,0.7)",
          marginBottom: 10,
        }}>
          AI Agent Status
        </div>
        {agents.map((agent, i) => (
          <motion.div
            key={agent.name}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.6 + i * 0.15, duration: 0.4 }}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: i < agents.length - 1 ? 8 : 0,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={dotStyle(agent.dotColor, agent.currentState)} />
              <span style={{
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                color: isDark ? "rgba(235,231,231,0.75)" : "rgba(17,16,14,0.7)",
              }}>
                {agent.name}
              </span>
            </div>
            <span style={{
              fontSize: 9,
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.08em",
              color: stateColor(agent.currentState),
              fontWeight: 600,
            }}>
              {agent.currentState}
            </span>
          </motion.div>
        ))}
      </div>
    </>
  );
}

/* ── Login page ─────────────────────────────────────────────────────────────── */
export function LoginPage({ onAuth }: { onAuth: () => void }) {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const [phrase, setPhrase]     = useState("");
  const [error, setError]       = useState(false);
  const [errorMsg, setErrorMsg] = useState("Incorrect passphrase. Try again.");
  const [shake, setShake]       = useState(false);
  const [granted, setGranted]   = useState(false);
  const [locked, setLocked]     = useState(isLockedOut);
  const [hyperspeed, setHyperspeed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 400);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (isLockedOut()) {
      setLocked(true);
      setError(true);
      setErrorMsg("Terminal locked — try again in 15 minutes.");
      setPhrase("");
      return;
    }

    if (phrase.trim().toLowerCase() === ACCESS_PHRASE.toLowerCase()) {
      clearFailures();
      setGranted(true);
      setHyperspeed(true);
      setTimeout(() => {
        localStorage.setItem(AUTH_KEY, JSON.stringify({ ts: Date.now() }));
        onAuth();
      }, 1600);
    } else {
      const result = recordFailure();
      setError(true);
      setShake(true);
      if (result.locked) {
        setLocked(true);
        setErrorMsg("Terminal locked — too many failed attempts.");
      } else {
        setErrorMsg(`Incorrect passphrase — ${result.remaining} attempt${result.remaining !== 1 ? "s" : ""} left.`);
      }
      setTimeout(() => setShake(false), 400);
      setTimeout(() => { setError(false); setErrorMsg("Incorrect passphrase. Try again."); }, 3000);
      setPhrase("");
    }
  };

  const cardBg = isDark
    ? "rgba(26,25,23,0.88)"
    : "rgba(242,240,240,0.88)";
  const cardBorder = error
    ? "1px solid rgba(231,76,60,0.35)"
    : isDark
      ? "1px solid rgba(160,148,127,0.15)"
      : "1px solid rgba(17,16,14,0.12)";
  const cardShadow = error
    ? "0 20px 60px rgba(231,76,60,0.15), 0 0 0 1px rgba(231,76,60,0.1)"
    : isDark
      ? "0 20px 60px rgba(0,0,0,0.8)"
      : "0 20px 60px rgba(17,16,14,0.12)";

  const inputBg = isDark
    ? error ? "rgba(231,76,60,0.08)" : "rgba(15,14,12,0.7)"
    : error ? "rgba(231,76,60,0.04)" : "rgba(248,247,246,0.9)";
  const inputBorder = error
    ? "1.5px solid rgba(231,76,60,0.45)"
    : isDark
      ? "1.5px solid rgba(160,148,127,0.2)"
      : "1.5px solid rgba(17,16,14,0.16)";
  const inputColor = isDark
    ? error ? "#f87171" : "#EBE7E7"
    : error ? "#dc2626" : "#11100E";

  const btnDisabled = locked || granted || !phrase.trim();
  const btnBg = btnDisabled
    ? isDark ? "rgba(160,148,127,0.1)" : "rgba(17,16,14,0.07)"
    : "var(--accent)";
  const btnColor = btnDisabled
    ? isDark ? "rgba(160,148,127,0.4)" : "rgba(17,16,14,0.3)"
    : isDark ? "#EBE7E7" : "#F5F3F2";

  return (
    <div style={{
      position: "relative",
      width: "100vw",
      height: "100vh",
      overflow: "hidden",
      background: isDark ? "#0F0E0C" : "#EBE7E7",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }}>
      {/* Layer 1: Neural network canvas */}
      <NeuralCanvas theme={theme} hyperspeed={hyperspeed} />

      {/* Login card */}
      <motion.div
        initial={{ opacity: 0, y: 32, scale: 0.95 }}
        animate={granted
          ? { opacity: 0, y: -16, scale: 1.04 }
          : { opacity: 1, y: 0, scale: 1 }
        }
        transition={granted
          ? { duration: 0.5, ease: [0.4, 0, 0.2, 1] }
          : { type: "spring", stiffness: 280, damping: 26, delay: 0.15 }
        }
        style={{
          position: "relative",
          zIndex: 10,
          width: "min(420px, calc(100vw - 40px))",
        }}
      >
        <motion.div
          animate={{ x: shake ? [-10, 10, -7, 7, -4, 4, 0] : 0 }}
          transition={{ duration: 0.4 }}
          style={{
            background: cardBg,
            border: cardBorder,
            borderLeft: `3px solid var(--accent)`,
            borderRadius: 16,
            padding: "28px 28px 22px",
            boxShadow: cardShadow,
            backdropFilter: "blur(32px)",
            WebkitBackdropFilter: "blur(32px)",
            transition: "border-color 300ms, box-shadow 300ms",
          }}
        >
          {/* Header bar */}
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 20,
            paddingBottom: 14,
            borderBottom: isDark
              ? "1px solid rgba(160,148,127,0.1)"
              : "1px solid rgba(17,16,14,0.08)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 15 }}>⚓</span>
              <span style={{
                fontFamily: "var(--font-heading)",
                fontStyle: "italic",
                fontSize: 14,
                color: isDark ? "rgba(235,231,231,0.9)" : "rgba(17,16,14,0.85)",
                letterSpacing: "0.01em",
              }}>
                One Piece
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: "#4ade80",
                boxShadow: "0 0 8px #4ade8088",
                animation: "agentPulseFast 1.2s ease-in-out infinite",
              }} />
              <span style={{
                fontSize: 9,
                fontFamily: "var(--font-mono)",
                letterSpacing: "0.08em",
                color: isDark ? "rgba(160,148,127,0.6)" : "rgba(106,98,86,0.6)",
              }}>
                ONLINE
              </span>
            </div>
          </div>

          {/* Brand */}
          <div style={{ textAlign: "center", marginBottom: 22 }}>
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 400, damping: 22, delay: 0.3 }}
              style={{
                width: 52,
                height: 52,
                borderRadius: 14,
                background: isDark
                  ? "linear-gradient(135deg, rgba(160,148,127,0.25) 0%, rgba(120,108,87,0.35) 100%)"
                  : "linear-gradient(135deg, rgba(106,98,86,0.18) 0%, rgba(80,72,60,0.28) 100%)",
                border: isDark
                  ? "1px solid rgba(160,148,127,0.25)"
                  : "1px solid rgba(106,98,86,0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 14px",
                boxShadow: isDark
                  ? "0 8px 24px rgba(0,0,0,0.5)"
                  : "0 8px 24px rgba(106,98,86,0.2)",
                fontSize: 22,
              }}
            >
              ⚓
            </motion.div>
            <div style={{
              fontFamily: "var(--font-heading)",
              fontStyle: "italic",
              fontSize: 26,
              color: isDark ? "#EBE7E7" : "#11100E",
              letterSpacing: "-0.01em",
              lineHeight: 1.1,
              marginBottom: 2,
            }}>
              One Piece{" "}
              <span style={{
                color: isDark ? "rgba(160,148,127,0.85)" : "rgba(106,98,86,0.8)",
              }}>
                Quant
              </span>
            </div>
            <div style={{
              fontSize: 10,
              fontFamily: "var(--font-body)",
              fontWeight: 500,
              color: isDark ? "rgba(160,148,127,0.65)" : "rgba(106,98,86,0.65)",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              marginTop: 4,
            }}>
              NSE · BSE · AI Terminal
            </div>
          </div>

          {/* AI Agent Status Panel */}
          <AgentStatusPanel theme={theme} />

          {/* Form */}
          <form onSubmit={handleSubmit} autoComplete="off">
            <div style={{ marginBottom: 14 }}>
              <label style={{
                display: "block",
                marginBottom: 7,
                fontSize: 10,
                fontWeight: 600,
                fontFamily: "var(--font-mono)",
                color: error
                  ? "#ef4444"
                  : isDark ? "rgba(160,148,127,0.75)" : "rgba(106,98,86,0.75)",
                letterSpacing: "0.07em",
                textTransform: "uppercase",
                transition: "color 200ms",
              }}>
                {locked
                  ? "⚠ Terminal locked"
                  : error
                    ? errorMsg
                    : "Enter passphrase"}
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
                  background: inputBg,
                  border: inputBorder,
                  borderRadius: 10,
                  padding: "13px 14px",
                  fontSize: 16,
                  fontFamily: "var(--font-mono)",
                  color: inputColor,
                  outline: "none",
                  letterSpacing: "0.22em",
                  transition: "all 200ms",
                  boxSizing: "border-box",
                  caretColor: "var(--accent)",
                }}
                onFocus={e => {
                  if (!error) {
                    e.target.style.borderColor = isDark
                      ? "rgba(160,148,127,0.5)"
                      : "rgba(106,98,86,0.5)";
                    e.target.style.boxShadow = isDark
                      ? "0 0 0 3px rgba(160,148,127,0.1)"
                      : "0 0 0 3px rgba(106,98,86,0.1)";
                  }
                }}
                onBlur={e => {
                  if (!error) {
                    e.target.style.borderColor = isDark
                      ? "rgba(160,148,127,0.2)"
                      : "rgba(17,16,14,0.16)";
                    e.target.style.boxShadow = "none";
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
                width: "100%",
                background: btnBg,
                color: btnColor,
                border: "none",
                borderRadius: 9999,
                padding: "13px 0",
                fontSize: 12,
                fontWeight: 700,
                fontFamily: "var(--font-body)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                cursor: btnDisabled ? "not-allowed" : "pointer",
                transition: "background 200ms, box-shadow 200ms, color 200ms",
                boxShadow: !btnDisabled
                  ? isDark
                    ? "0 4px 20px rgba(160,148,127,0.25)"
                    : "0 4px 20px rgba(106,98,86,0.25)"
                  : "none",
              }}
            >
              {granted ? "Initialising terminal…" : locked ? "Terminal locked" : "Access Terminal"}
            </motion.button>
          </form>

          {/* Footer */}
          <div style={{
            marginTop: 18,
            paddingTop: 14,
            borderTop: isDark
              ? "1px solid rgba(160,148,127,0.08)"
              : "1px solid rgba(17,16,14,0.07)",
            display: "flex",
            justifyContent: "center",
          }}>
            <span style={{
              fontSize: 10,
              fontFamily: "var(--font-mono)",
              color: isDark ? "rgba(160,148,127,0.4)" : "rgba(106,98,86,0.4)",
              letterSpacing: "0.04em",
            }}>
              Authorized access only · All activity logged
            </span>
          </div>
        </motion.div>
      </motion.div>

      {/* Access granted overlay */}
      <AnimatePresence>
        {granted && (
          <>
            {/* Flash effect */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0.6, 0] }}
              transition={{ duration: 0.5, times: [0, 0.2, 1] }}
              style={{
                position: "absolute",
                inset: 0,
                zIndex: 15,
                background: isDark ? "#EBE7E7" : "#11100E",
                pointerEvents: "none",
              }}
            />
            {/* Main overlay */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ delay: 0.3, duration: 0.4 }}
              style={{
                position: "absolute",
                inset: 0,
                zIndex: 20,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: isDark
                  ? "rgba(15,14,12,0.75)"
                  : "rgba(235,231,231,0.8)",
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
              }}
            >
              <motion.div
                initial={{ scale: 0.7, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{
                  type: "spring",
                  stiffness: 350,
                  damping: 22,
                  delay: 0.35,
                }}
                style={{ textAlign: "center" }}
              >
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: [0, 1.2, 1] }}
                  transition={{ delay: 0.4, duration: 0.5, ease: "easeOut" }}
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: "50%",
                    background: "linear-gradient(135deg, #4ade80 0%, #22c55e 100%)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    margin: "0 auto 20px",
                    boxShadow: "0 8px 40px rgba(74,222,128,0.45)",
                    fontSize: 30,
                    color: "#fff",
                  }}
                >
                  ✓
                </motion.div>
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.6 }}
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    fontFamily: "var(--font-heading)",
                    fontStyle: "italic",
                    color: isDark ? "#EBE7E7" : "#11100E",
                    letterSpacing: "-0.01em",
                  }}
                >
                  Access granted
                </motion.div>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.75 }}
                  style={{
                    fontSize: 11,
                    fontFamily: "var(--font-mono)",
                    color: isDark ? "rgba(160,148,127,0.7)" : "rgba(106,98,86,0.7)",
                    marginTop: 6,
                    letterSpacing: "0.06em",
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
