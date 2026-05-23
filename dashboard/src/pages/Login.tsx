import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "@/hooks/useTheme";
import type { Theme } from "@/hooks/useTheme";

/* passphrase is compared case-sensitively after stripping all whitespace */
const ACCESS_PHRASE: string = import.meta.env.VITE_AUTH_PHRASE || "One piece is real";

export const AUTH_KEY  = "op_matrix_auth";
export const LOCK_KEY  = "op_lock_until";
export const FAIL_KEY  = "op_fail_count";
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

      const bg = ctx.createLinearGradient(0, 0, w, h);
      bg.addColorStop(0, bgFrom); bg.addColorStop(1, bgTo);
      ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);

      ctx.strokeStyle = isDark ? `rgba(167,139,250,0.025)` : `rgba(106,98,86,0.025)`;
      ctx.lineWidth = 0.5;
      for (let gx = 0; gx < w; gx += 20) { ctx.beginPath(); ctx.moveTo(gx,0); ctx.lineTo(gx,h); ctx.stroke(); }
      for (let gy = 0; gy < h; gy += 20) { ctx.beginPath(); ctx.moveTo(0,gy); ctx.lineTo(w,gy); ctx.stroke(); }

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

/* ── Agent Status Panel ──────────────────────────────────────────────────────── */
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

/* ══════════════════════════════════════════════════════════════════════════════
   MATRIX ACCESS GRANTED SEQUENCE
   ══════════════════════════════════════════════════════════════════════════════ */

const MTX_CHARS = "01アイウエオカキクケコタチツテト0110ヲンヴアABCDEF∑∆Ω≠∫√#$@!%&<>{}[]";

/* synthesise Matrix-style sound entirely in-browser — no external files */
function playMatrixSound() {
  try {
    type AudioCtxCtor = typeof AudioContext;
    const Ctx = (window.AudioContext || (window as unknown as { webkitAudioContext: AudioCtxCtor }).webkitAudioContext);
    const ctx = new Ctx();

    /* ── low digital drone ── */
    const drone = ctx.createOscillator();
    const droneG = ctx.createGain();
    drone.type = "sawtooth";
    drone.frequency.setValueAtTime(40, ctx.currentTime);
    drone.frequency.exponentialRampToValueAtTime(80, ctx.currentTime + 4);
    droneG.gain.setValueAtTime(0, ctx.currentTime);
    droneG.gain.linearRampToValueAtTime(0.05, ctx.currentTime + 0.4);
    droneG.gain.linearRampToValueAtTime(0.03, ctx.currentTime + 3);
    droneG.gain.linearRampToValueAtTime(0, ctx.currentTime + 4.5);
    drone.connect(droneG); droneG.connect(ctx.destination);
    drone.start(); drone.stop(ctx.currentTime + 4.6);

    /* ── glitch ticks while rain falls ── */
    [0.05, 0.18, 0.38, 0.62, 0.91, 1.25, 1.6, 2.0, 2.4].forEach(t => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "square";
      o.frequency.value = 180 + Math.random() * 520;
      g.gain.setValueAtTime(0, ctx.currentTime + t);
      g.gain.linearRampToValueAtTime(0.055, ctx.currentTime + t + 0.015);
      g.gain.linearRampToValueAtTime(0, ctx.currentTime + t + 0.07);
      o.connect(g); g.connect(ctx.destination);
      o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.09);
    });

    /* ── rising tone sweep during scramble ── */
    const sweep = ctx.createOscillator();
    const sweepG = ctx.createGain();
    sweep.type = "sine";
    sweep.frequency.setValueAtTime(220, ctx.currentTime + 0.9);
    sweep.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 2.9);
    sweepG.gain.setValueAtTime(0, ctx.currentTime + 0.9);
    sweepG.gain.linearRampToValueAtTime(0.04, ctx.currentTime + 1.2);
    sweepG.gain.linearRampToValueAtTime(0.06, ctx.currentTime + 2.8);
    sweepG.gain.linearRampToValueAtTime(0, ctx.currentTime + 3.1);
    sweep.connect(sweepG); sweepG.connect(ctx.destination);
    sweep.start(ctx.currentTime + 0.9); sweep.stop(ctx.currentTime + 3.2);

    /* ── ACCESS GRANTED chord ── */
    [261.63, 329.63, 392, 523.25].forEach((freq, i) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = freq;
      const t0 = ctx.currentTime + 2.85 + i * 0.055;
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(0.09, t0 + 0.04);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + 1.8);
      o.connect(g); g.connect(ctx.destination);
      o.start(t0); o.stop(t0 + 2);
    });
  } catch { /* AudioContext not available — silent fallback */ }
}

/* matrix rain canvas — pure green on black */
function MatrixRainCanvas({ fadeOut }: { fadeOut: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fadeRef   = useRef(fadeOut);
  fadeRef.current = fadeOut;

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx    = canvas.getContext("2d")!;
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;

    const fontSize = 15;
    const cols     = Math.floor(canvas.width / fontSize);
    const drops    = Array.from({ length: cols }, () => Math.random() * -(canvas.height / fontSize));
    const speeds   = Array.from({ length: cols }, () => 0.25 + Math.random() * 0.75);

    let raf: number;
    let globalAlpha = 1;

    const draw = () => {
      if (fadeRef.current) {
        globalAlpha = Math.max(0, globalAlpha - 0.035);
      }

      ctx.globalAlpha = globalAlpha;
      ctx.fillStyle = "rgba(0,0,0,0.055)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      for (let i = 0; i < drops.length; i++) {
        const y = drops[i] * fontSize;
        if (y < 0) { drops[i] += speeds[i]; continue; }

        /* bright head character */
        const head = MTX_CHARS[Math.floor(Math.random() * MTX_CHARS.length)];
        ctx.font = `${fontSize}px 'JetBrains Mono', monospace`;
        ctx.fillStyle = `rgba(180,255,180,${0.88 + Math.random() * 0.12})`;
        ctx.fillText(head, i * fontSize, y);

        /* fading trail */
        for (let t = 1; t <= 6; t++) {
          const trailY = y - t * fontSize;
          if (trailY < 0) continue;
          const a = (1 - t / 7) * 0.55;
          ctx.fillStyle = `rgba(0,${180 + Math.floor(Math.random() * 55)},0,${a})`;
          ctx.fillText(MTX_CHARS[Math.floor(Math.random() * MTX_CHARS.length)], i * fontSize, trailY);
        }

        drops[i] += speeds[i];
        if (drops[i] * fontSize > canvas.height && Math.random() > 0.97) {
          drops[i] = -Math.random() * 10;
        }
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", inset: 0, display: "block", background: "#000" }}
    />
  );
}

/* scramble text: random chars → resolves to target letter by letter */
function useTextScramble(target: string, active: boolean, duration = 2000) {
  const [display, setDisplay] = useState("");
  const frameRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!active) return;
    let frame = 0;
    const totalFrames = Math.round(duration / 35);

    const tick = () => {
      const progress  = frame / totalFrames;
      const locked    = Math.floor(progress * target.length);
      let out = "";
      for (let i = 0; i < target.length; i++) {
        if (target[i] === " ") { out += " "; continue; }
        if (i < locked) {
          out += target[i];
        } else {
          out += MTX_CHARS[Math.floor(Math.random() * MTX_CHARS.length)];
        }
      }
      setDisplay(out);
      frame++;
      if (frame <= totalFrames) frameRef.current = setTimeout(tick, 35);
    };

    tick();
    return () => { if (frameRef.current) clearTimeout(frameRef.current); };
  }, [active, target, duration]);

  return display;
}

type MatrixPhase = "rain" | "scramble" | "granted" | "fadeout";

function MatrixAccessOverlay({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<MatrixPhase>("rain");

  const scrambleActive = phase === "scramble" || phase === "granted";
  const displayText    = useTextScramble("ACCESS  GRANTED", scrambleActive, 1900);

  useEffect(() => {
    playMatrixSound();

    const t1 = setTimeout(() => setPhase("scramble"), 900);
    const t2 = setTimeout(() => setPhase("granted"),  2950);
    const t3 = setTimeout(() => setPhase("fadeout"),  3700);
    const t4 = setTimeout(() => onDone(),             4500);

    return () => [t1, t2, t3, t4].forEach(clearTimeout);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const isGranted = phase === "granted" || phase === "fadeout";
  const fadeOut   = phase === "fadeout";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: fadeOut ? 0 : 1 }}
      transition={{ duration: fadeOut ? 0.8 : 0.15, ease: "easeInOut" }}
      style={{
        position: "fixed", inset: 0, zIndex: 50,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexDirection: "column",
        pointerEvents: "all",
      }}
    >
      {/* Matrix rain canvas */}
      <MatrixRainCanvas fadeOut={fadeOut} />

      {/* Centrepiece text */}
      <div style={{
        position: "relative", zIndex: 10,
        textAlign: "center", userSelect: "none",
      }}>
        {/* scan-line overlay for authenticity */}
        <div style={{
          position: "absolute", inset: "-40px -60px",
          backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)",
          pointerEvents: "none", zIndex: 1,
        }} />

        {phase !== "rain" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            style={{ position: "relative", zIndex: 2 }}
          >
            {/* main text */}
            <div style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "clamp(22px, 5vw, 52px)",
              fontWeight: 700,
              letterSpacing: "0.25em",
              whiteSpace: "pre",
              color: isGranted ? "#00ff41" : "rgba(0,255,65,0.72)",
              textShadow: isGranted
                ? "0 0 10px #00ff41, 0 0 30px #00ff4188, 0 0 70px #00ff4144, 0 0 120px #00ff4122"
                : "0 0 8px rgba(0,255,65,0.5)",
              transition: "color 0.35s ease, text-shadow 0.35s ease",
            }}>
              {displayText || "________________"}
            </div>

            {/* progress bar beneath while scrambling */}
            {!isGranted && (
              <div style={{
                marginTop: 18, height: 2,
                background: "rgba(0,255,65,0.12)",
                borderRadius: 2, overflow: "hidden",
                width: "clamp(200px, 40vw, 420px)",
                margin: "18px auto 0",
              }}>
                <motion.div
                  initial={{ width: "0%" }}
                  animate={{ width: "100%" }}
                  transition={{ duration: 2.05, ease: "linear" }}
                  style={{ height: "100%", background: "rgba(0,255,65,0.65)", borderRadius: 2 }}
                />
              </div>
            )}

            {/* sub-line on granted */}
            {isGranted && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.1 }}
                style={{
                  marginTop: 14,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: "clamp(10px, 1.2vw, 13px)",
                  letterSpacing: "0.3em",
                  color: "rgba(0,255,65,0.48)",
                  textTransform: "uppercase",
                }}
              >
                Initialising terminal…
              </motion.div>
            )}
          </motion.div>
        )}
      </div>

      {/* vignette */}
      <div style={{
        position: "absolute", inset: 0, zIndex: 9, pointerEvents: "none",
        background: "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.72) 100%)",
      }} />
    </motion.div>
  );
}

/* ── Login Page ─────────────────────────────────────────────────────────────── */
export function LoginPage({ onAuth }: { onAuth: () => void }) {
  const { theme }  = useTheme();
  const isDark     = theme === "dark";

  const [phrase,    setPhrase]    = useState("");
  const [error,     setError]     = useState(false);
  const [errorMsg,  setErrorMsg]  = useState("Incorrect passphrase. Try again.");
  const [shake,     setShake]     = useState(false);
  const [granted,   setGranted]   = useState(false);
  const [locked,    setLocked]    = useState(isLockedOut);
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
    /* case-sensitive, whitespace-stripped comparison */
    const attempt = phrase.replace(/\s+/g, "");
    const secret  = ACCESS_PHRASE.replace(/\s+/g, "");
    if (attempt === secret) {
      clearFailures();
      setGranted(true);
      setHyperspeed(true);
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

  const handleAuthDone = () => {
    localStorage.setItem(AUTH_KEY, JSON.stringify({ ts: Date.now() }));
    onAuth();
  };

  const btnDisabled = locked || granted || !phrase.trim();

  return (
    <div style={{
      position: "relative", width: "100vw", height: "100vh",
      overflow: "hidden", background: isDark ? "#06060b" : "#EBE7E7",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <NeuralCanvas theme={theme} hyperspeed={hyperspeed} />
      <div className="grid-bg" />
      <div className="glow-top" />

      {/* ── Login card ── */}
      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.96 }}
        animate={granted
          ? { opacity: 0, y: -20, scale: 1.04 }
          : { opacity: 1, y: 0, scale: 1 }}
        transition={granted
          ? { duration: 0.4, ease: [0.4,0,0.2,1] }
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
          {isDark && (
            <div style={{
              position: "absolute", top: 0, left: 0, right: 0, height: 1,
              background: "linear-gradient(90deg, transparent, rgba(167,139,250,0.55) 40%, rgba(96,165,250,0.35) 70%, transparent)",
              pointerEvents: "none",
            }} />
          )}

          {/* Header bar */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 24, paddingBottom: 16,
            borderBottom: isDark ? "1px solid rgba(255,255,255,0.06)" : "1px solid rgba(17,16,14,0.08)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <img src="/favicon.svg" alt="One Piece Quant"
                style={{ width: 22, height: 22, borderRadius: 5, flexShrink: 0 }} />
              <span style={{
                fontFamily: "var(--font-heading)", fontStyle: "italic", fontSize: 13,
                color: isDark ? "rgba(245,245,247,0.82)" : "rgba(17,16,14,0.78)",
                letterSpacing: "0.01em",
              }}>One Piece Quant</span>
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
              }}>ONLINE</span>
            </div>
          </div>

          {/* Brand */}
          <div style={{ textAlign: "center", marginBottom: 22 }}>
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

            <div style={{
              fontFamily: "var(--font-heading)", fontStyle: "italic",
              fontSize: 27, letterSpacing: "-0.02em", lineHeight: 1.1, marginBottom: 5,
              color: isDark ? "#f5f5f7" : "#11100E",
            }}>
              One Piece{" "}
              <span style={{
                background: "linear-gradient(120deg, #a78bfa 0%, #60a5fa 55%, #34d399 100%)",
                WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
              }}>Quant</span>
            </div>

            <div style={{
              fontSize: 9.5, fontFamily: "var(--font-mono)", fontWeight: 500,
              letterSpacing: "0.16em", textTransform: "uppercase",
              color: isDark ? "rgba(167,139,250,0.45)" : "rgba(106,98,86,0.52)",
            }}>NSE · BSE · AI Terminal</div>
          </div>

          <AgentStatusPanel theme={theme} />

          {/* Form */}
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

          {/* Footer */}
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

      {/* ── Matrix ACCESS GRANTED sequence ── */}
      <AnimatePresence>
        {granted && <MatrixAccessOverlay onDone={handleAuthDone} />}
      </AnimatePresence>
    </div>
  );
}
