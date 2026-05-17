import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

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

/* ── Animated gradient background canvas ─────────────────────────────────── */
function GradientCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf: number;
    let t = 0;

    const resize = () => {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    /* Floating soft orbs */
    const orbs = [
      { x: 0.15, y: 0.30, r: 0.45, speed: 0.0004, phase: 0    },
      { x: 0.80, y: 0.15, r: 0.38, speed: 0.0003, phase: 2.1  },
      { x: 0.50, y: 0.75, r: 0.32, speed: 0.0005, phase: 4.2  },
      { x: 0.90, y: 0.80, r: 0.28, speed: 0.0004, phase: 1.0  },
    ];

    const draw = () => {
      t += 1;
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      /* Base gradient */
      const base = ctx.createLinearGradient(0, 0, w, h);
      base.addColorStop(0, "#F8F9FC");
      base.addColorStop(1, "#EFF2F7");
      ctx.fillStyle = base;
      ctx.fillRect(0, 0, w, h);

      /* Soft blue orbs */
      for (const o of orbs) {
        const cx = w * (o.x + Math.sin(t * o.speed + o.phase) * 0.08);
        const cy = h * (o.y + Math.cos(t * o.speed + o.phase) * 0.07);
        const r  = Math.min(w, h) * o.r;
        const g  = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        g.addColorStop(0, "rgba(50,121,249,0.07)");
        g.addColorStop(1, "rgba(50,121,249,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, h);
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: "absolute", inset: 0, display: "block" }}
    />
  );
}

/* ── Login page ─────────────────────────────────────────────────────────── */
export function LoginPage({ onAuth }: { onAuth: () => void }) {
  const [phrase, setPhrase]     = useState("");
  const [error, setError]       = useState(false);
  const [errorMsg, setErrorMsg] = useState("Incorrect passphrase. Try again.");
  const [shake, setShake]       = useState(false);
  const [granted, setGranted]   = useState(false);
  const [locked, setLocked]     = useState(isLockedOut);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 300);
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
      setTimeout(() => {
        localStorage.setItem(AUTH_KEY, JSON.stringify({ ts: Date.now() }));
        onAuth();
      }, 800);
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

  return (
    <div style={{
      position: "relative", width: "100vw", height: "100vh",
      overflow: "hidden", background: "#F8F9FC",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <GradientCanvas />

      {/* Grid pattern overlay */}
      <div style={{
        position: "absolute", inset: 0, pointerEvents: "none",
        backgroundImage: `
          linear-gradient(rgba(33,34,38,0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(33,34,38,0.03) 1px, transparent 1px)
        `,
        backgroundSize: "40px 40px",
      }} />

      {/* Login card */}
      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 28, delay: 0.1 }}
        style={{
          position: "relative", zIndex: 10,
          width: "min(420px, calc(100vw - 40px))",
        }}
      >
        <motion.div
          animate={{ x: shake ? [-8, 8, -6, 6, -4, 4, 0] : 0 }}
          transition={{ duration: 0.4 }}
          style={{
            background: "rgba(255,255,255,0.92)",
            border: `1.5px solid ${error ? "rgba(231,76,60,0.3)" : "rgba(33,34,38,0.10)"}`,
            borderRadius: 20,
            padding: "36px 36px 28px",
            boxShadow: error
              ? "0 8px 40px rgba(231,76,60,0.10), 0 0 0 1px rgba(231,76,60,0.12)"
              : "0 8px 40px rgba(33,34,38,0.10), 0 0 0 1px rgba(33,34,38,0.06)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            transition: "border-color 300ms, box-shadow 300ms",
          }}
        >
          {/* Brand */}
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <div style={{
              width: 52, height: 52, borderRadius: 14,
              background: "linear-gradient(135deg, #3279F9 0%, #5A9BFB 100%)",
              display: "flex", alignItems: "center", justifyContent: "center",
              margin: "0 auto 16px",
              boxShadow: "0 8px 24px rgba(50,121,249,0.3)",
              fontSize: 24,
            }}>
              ⚓
            </div>
            <div style={{
              fontSize: 20,
              fontFamily: '"DM Sans", "Google Sans", system-ui, sans-serif',
              fontWeight: 700,
              color: "#121317",
              letterSpacing: "-0.01em",
              lineHeight: 1.2,
              marginBottom: 4,
            }}>
              One Piece Quant
            </div>
            <div style={{
              fontSize: 11,
              fontFamily: '"DM Sans", system-ui, sans-serif',
              fontWeight: 500,
              color: "#818590",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}>
              NSE · BSE · AI Terminal
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} autoComplete="off">
            <div style={{ marginBottom: 16 }}>
              <label style={{
                display: "block", marginBottom: 6,
                fontSize: 11, fontWeight: 600,
                fontFamily: '"DM Sans", system-ui, sans-serif',
                color: error ? "#E74C3C" : "#45474D",
                letterSpacing: "0.04em",
                transition: "color 200ms",
              }}>
                {locked
                  ? "Terminal locked"
                  : error
                    ? errorMsg
                    : "Enter passphrase to continue"}
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
                  background: error ? "rgba(231,76,60,0.04)" : "rgba(248,249,252,0.9)",
                  border: `1.5px solid ${error ? "rgba(231,76,60,0.35)" : "rgba(33,34,38,0.16)"}`,
                  borderRadius: 10,
                  padding: "12px 14px",
                  fontSize: 16,
                  fontFamily: '"JetBrains Mono", monospace',
                  color: error ? "#E74C3C" : "#121317",
                  outline: "none",
                  letterSpacing: "0.2em",
                  transition: "all 200ms",
                  boxSizing: "border-box",
                  caretColor: "#3279F9",
                }}
                onFocus={e => {
                  if (!error) {
                    e.target.style.borderColor = "rgba(50,121,249,0.5)";
                    e.target.style.boxShadow = "0 0 0 3px rgba(50,121,249,0.08)";
                  }
                }}
                onBlur={e => {
                  if (!error) {
                    e.target.style.borderColor = "rgba(33,34,38,0.16)";
                    e.target.style.boxShadow = "none";
                  }
                }}
              />
            </div>

            <button
              type="submit"
              disabled={locked || granted || !phrase.trim()}
              style={{
                width: "100%",
                background: locked || granted || !phrase.trim()
                  ? "rgba(33,34,38,0.06)"
                  : "#3279F9",
                color: locked || granted || !phrase.trim() ? "#9E9EA6" : "#ffffff",
                border: "none",
                borderRadius: 9999,
                padding: "12px 0",
                fontSize: 13,
                fontWeight: 600,
                fontFamily: '"DM Sans", system-ui, sans-serif',
                letterSpacing: "0.01em",
                cursor: locked || !phrase.trim() ? "not-allowed" : "pointer",
                transition: "all 200ms",
                boxShadow: !locked && !granted && phrase.trim()
                  ? "0 4px 16px rgba(50,121,249,0.28)"
                  : "none",
              }}
              onMouseEnter={e => {
                if (!locked && !granted && phrase.trim()) {
                  e.currentTarget.style.background = "#2060E0";
                  e.currentTarget.style.transform = "translateY(-1px)";
                  e.currentTarget.style.boxShadow = "0 6px 24px rgba(50,121,249,0.35)";
                }
              }}
              onMouseLeave={e => {
                if (!locked && !granted && phrase.trim()) {
                  e.currentTarget.style.background = "#3279F9";
                  e.currentTarget.style.transform = "translateY(0)";
                  e.currentTarget.style.boxShadow = "0 4px 16px rgba(50,121,249,0.28)";
                }
              }}
            >
              {granted ? "Entering terminal…" : locked ? "Terminal locked" : "Access terminal"}
            </button>
          </form>

          {/* Footer */}
          <div style={{
            marginTop: 20, paddingTop: 16,
            borderTop: "1px solid rgba(33,34,38,0.07)",
            display: "flex", justifyContent: "center",
          }}>
            <span style={{
              fontSize: 10,
              fontFamily: '"DM Sans", system-ui, sans-serif',
              color: "#9E9EA6",
              letterSpacing: "0.03em",
            }}>
              Authorized access only · All activity logged
            </span>
          </div>
        </motion.div>
      </motion.div>

      {/* Access granted overlay */}
      <AnimatePresence>
        {granted && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: "absolute", inset: 0, zIndex: 20,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "rgba(248,249,252,0.85)",
              backdropFilter: "blur(12px)",
            }}
          >
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              style={{ textAlign: "center" }}
            >
              <div style={{
                width: 64, height: 64, borderRadius: "50%",
                background: "linear-gradient(135deg, #3279F9 0%, #27AE60 100%)",
                display: "flex", alignItems: "center", justifyContent: "center",
                margin: "0 auto 16px",
                boxShadow: "0 8px 32px rgba(50,121,249,0.35)",
                fontSize: 28,
              }}>✓</div>
              <div style={{
                fontSize: 16, fontWeight: 700,
                fontFamily: '"DM Sans", system-ui, sans-serif',
                color: "#121317", letterSpacing: "-0.01em",
              }}>
                Access granted
              </div>
              <div style={{ fontSize: 11, color: "#818590", marginTop: 4 }}>
                Initialising terminal…
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
