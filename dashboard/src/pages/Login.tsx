import { useEffect, useRef, useState } from "react";

const ACCESS_PHRASE = "One piece is real";
export const AUTH_KEY = "iqf_matrix_auth";

const MATRIX_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*+-=[]|ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜｵﾘｱﾎﾃﾏｹﾒｴｶｷｾﾽｿﾁﾄﾍ01".split("");

const GRANTED_LANGS = [
  "ACCESS GRANTED",
  "アクセス許可",
  "ACCÈS ACCORDÉ",
  "ZUGANG GEWÄHRT",
  "ДОСТУП РАЗРЕШЁН",
  "访问已授权",
  "وصول مصرح",
  "ACCESSO CONSENTITO",
  "ACCESS GRANTED",
];

export function LoginPage({ onAuth }: { onAuth: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const dropsRef = useRef<number[]>([]);
  const speedRef = useRef<number>(1);

  const [phrase, setPhrase] = useState("");
  const [error, setError] = useState(false);
  const [shake, setShake] = useState(false);
  const [phase, setPhase] = useState<"idle" | "granted" | "fadeout">("idle");
  const [grantedText, setGrantedText] = useState("ACCESS GRANTED");

  // Matrix rain canvas
  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const FS = 13;

    const init = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      const cols = Math.floor(canvas.width / FS);
      dropsRef.current = Array.from({ length: cols }, () => Math.random() * -80);
    };
    init();
    window.addEventListener("resize", init);

    const draw = () => {
      const { width: w, height: h } = canvas;
      const speed = speedRef.current;
      ctx.fillStyle = `rgba(0,0,0,${phase === "granted" ? 0.02 : 0.055})`;
      ctx.fillRect(0, 0, w, h);
      ctx.font = `${FS}px "JetBrains Mono", monospace`;

      const drops = dropsRef.current;
      for (let i = 0; i < drops.length; i++) {
        const y = drops[i] * FS;
        if (y < 0) { drops[i] += 0.4 * speed; continue; }
        const char = MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
        const rnd = Math.random();
        if (rnd > 0.995) ctx.fillStyle = "#ffffff";
        else if (rnd > 0.93) ctx.fillStyle = phase === "granted" ? "#00ff41" : "#00e535";
        else if (rnd > 0.7) ctx.fillStyle = "#00cc33";
        else if (rnd > 0.4) ctx.fillStyle = "#009922";
        else ctx.fillStyle = "#004411";
        ctx.fillText(char, i * FS, y);
        if (y > h && Math.random() > 0.975) drops[i] = 0;
        drops[i] += (0.38 + Math.random() * 0.3) * speed;
      }
      animRef.current = requestAnimationFrame(draw);
    };
    animRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", init);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (phrase.trim().toLowerCase() === ACCESS_PHRASE.toLowerCase()) {
      setPhase("granted");
      speedRef.current = 3;

      // Cycle through multi-language "ACCESS GRANTED" text
      let idx = 0;
      const interval = setInterval(() => {
        idx++;
        if (idx < GRANTED_LANGS.length) {
          setGrantedText(GRANTED_LANGS[idx]);
        } else {
          clearInterval(interval);
        }
      }, 160);

      setTimeout(() => {
        setPhase("fadeout");
        speedRef.current = 0.1;
        setTimeout(() => {
          localStorage.setItem(AUTH_KEY, "1");
          onAuth();
        }, 700);
      }, GRANTED_LANGS.length * 160 + 400);
    } else {
      setError(true);
      setShake(true);
      setTimeout(() => setShake(false), 400);
      setTimeout(() => setError(false), 2200);
      setPhrase("");
    }
  };

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh", overflow: "hidden", background: "#000" }}>
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, display: "block" }} />

      {/* CRT scanlines */}
      <div style={{
        position: "absolute", inset: 0, pointerEvents: "none",
        backgroundImage: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.04) 2px,rgba(0,0,0,0.04) 4px)",
      }} />

      {/* Vignette */}
      <div style={{
        position: "absolute", inset: 0, pointerEvents: "none",
        background: "radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.72) 100%)",
      }} />

      {/* ── ACCESS GRANTED overlay ── */}
      {phase !== "idle" && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column",
          gap: 24,
          opacity: phase === "fadeout" ? 0 : 1,
          transition: "opacity 0.6s ease-in",
          pointerEvents: "none",
          zIndex: 10,
        }}>
          <div style={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 36,
            fontWeight: 700,
            color: "#00ff41",
            textShadow: "0 0 30px #00ff41, 0 0 60px rgba(0,255,65,0.4)",
            letterSpacing: "0.15em",
            textAlign: "center",
            animation: "matrixBlink 0.3s step-start 2",
            minWidth: 500,
          }}>
            {grantedText}
          </div>
          <div style={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 12,
            color: "#00aa28",
            letterSpacing: "0.25em",
            textTransform: "uppercase",
          }}>
            INITIALISING TERMINAL...
          </div>
          <div style={{
            width: 300, height: 2,
            background: "linear-gradient(90deg, transparent, #00ff41, transparent)",
            animation: "matrixScan 0.4s linear infinite",
          }} />
        </div>
      )}

      {/* ── Login panel ── */}
      <div style={{
        position: "absolute", top: "50%", left: "50%",
        transform: `translate(-50%, -50%) translateX(${shake ? "-8px" : "0"})`,
        transition: shake ? "transform 50ms" : "transform 80ms ease-out",
        width: 400,
        opacity: phase !== "idle" ? 0 : 1,
        transition2: "opacity 0.3s ease",
      } as React.CSSProperties}>
        <div style={{
          background: "rgba(0,6,0,0.92)",
          border: `1px solid ${error ? "#ff2244" : "rgba(0,255,65,0.6)"}`,
          borderRadius: 2,
          padding: "36px 32px 28px",
          boxShadow: error
            ? "0 0 60px rgba(255,34,68,0.12)"
            : "0 0 80px rgba(0,255,65,0.1), inset 0 0 40px rgba(0,255,65,0.03)",
          backdropFilter: "blur(10px)",
          fontFamily: '"JetBrains Mono", monospace',
          transition: "border-color 300ms, box-shadow 300ms, opacity 300ms",
        }}>

          {/* Top ruler */}
          <div style={{
            width: "100%", height: 1,
            background: "linear-gradient(90deg, transparent, #00ff41 30%, #00ff41 70%, transparent)",
            opacity: 0.4, marginBottom: 24,
          }} />

          {/* Brand */}
          <div style={{ textAlign: "center", marginBottom: 28 }}>
            <div style={{
              fontSize: 28,
              fontWeight: 900,
              color: "#00ff41",
              letterSpacing: "0.12em",
              textShadow: "0 0 20px rgba(0,255,65,0.6), 0 0 40px rgba(0,255,65,0.2)",
              lineHeight: 1.1,
              marginBottom: 4,
            }}>
              ONE PIECE
            </div>
            <div style={{
              fontSize: 12,
              fontWeight: 600,
              color: "#00cc33",
              letterSpacing: "0.3em",
              textTransform: "uppercase",
              textShadow: "0 0 10px rgba(0,204,51,0.4)",
            }}>
              QUANT TERMINAL
            </div>

            <div style={{
              width: "60%", height: 1, margin: "16px auto 0",
              background: "linear-gradient(90deg, transparent, rgba(0,255,65,0.4), transparent)",
            }} />

            <div style={{
              color: "#004d19", fontSize: 9, marginTop: 12,
              letterSpacing: "0.15em",
            }}>
              NSE · BSE · REAL-TIME MARKET INTELLIGENCE
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} autoComplete="off">
            <div style={{ marginBottom: 18 }}>
              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                color: error ? "#ff2244" : "#00aa28",
                fontSize: 9.5, letterSpacing: "0.08em", marginBottom: 8,
              }}>
                <span style={{ opacity: 0.5 }}>&gt;</span>
                <span>{error ? "// ACCESS DENIED — RETRY" : "// ENTER ACCESS PHRASE"}</span>
                <span style={{ animation: "matrixBlink 1s step-start infinite", color: "#00ff41" }}>█</span>
              </div>
              <input
                type="password"
                value={phrase}
                onChange={e => { setPhrase(e.target.value); if (error) setError(false); }}
                placeholder="••••••••••••••••••••••••"
                autoFocus
                autoComplete="new-password"
                style={{
                  width: "100%", boxSizing: "border-box",
                  background: error ? "rgba(255,34,68,0.04)" : "rgba(0,255,65,0.03)",
                  border: `1px solid ${error ? "rgba(255,34,68,0.6)" : "rgba(0,255,65,0.4)"}`,
                  borderRadius: 1,
                  padding: "12px 14px",
                  color: error ? "#ff2244" : "#00ff41",
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: 16,
                  outline: "none",
                  letterSpacing: "0.15em",
                  caretColor: "#00ff41",
                  transition: "all 250ms",
                  boxShadow: error ? "0 0 16px rgba(255,34,68,0.12)" : "none",
                }}
                onFocus={e => {
                  if (!error) {
                    e.target.style.borderColor = "#00ff41";
                    e.target.style.boxShadow = "0 0 16px rgba(0,255,65,0.12)";
                  }
                }}
                onBlur={e => {
                  if (!error) {
                    e.target.style.borderColor = "rgba(0,255,65,0.4)";
                    e.target.style.boxShadow = "none";
                  }
                }}
              />
              <div style={{
                fontSize: 9, marginTop: 5, letterSpacing: "0.06em", minHeight: 14,
                color: error ? "#ff2244" : "#003311",
              }}>
                {error ? "⚠ ACCESS DENIED — INVALID PHRASE. ATTEMPT LOGGED." : "CLASSIFIED SYSTEM — BIOMETRIC VERIFICATION ACTIVE"}
              </div>
            </div>

            <button
              type="submit"
              style={{
                width: "100%",
                background: "transparent",
                border: "1px solid rgba(0,255,65,0.6)",
                borderRadius: 1,
                padding: "12px 0",
                color: "#00ff41",
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.22em",
                cursor: "pointer",
                textTransform: "uppercase",
                transition: "all 150ms",
                textShadow: "0 0 8px rgba(0,255,65,0.4)",
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = "rgba(0,255,65,0.07)";
                e.currentTarget.style.boxShadow = "0 0 24px rgba(0,255,65,0.12)";
                e.currentTarget.style.borderColor = "#00ff41";
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.boxShadow = "none";
                e.currentTarget.style.borderColor = "rgba(0,255,65,0.6)";
              }}
            >
              [ AUTHENTICATE ]
            </button>
          </form>

          {/* Bottom ruler + footer */}
          <div style={{
            marginTop: 20, paddingTop: 14,
            borderTop: "1px solid rgba(0,255,65,0.08)",
            display: "flex", justifyContent: "space-between",
          }}>
            <span style={{ fontSize: 8, color: "#003311", letterSpacing: "0.05em" }}>
              UNAUTHORIZED ACCESS PROHIBITED
            </span>
            <span style={{ fontSize: 8, color: "#003311", letterSpacing: "0.05em" }}>
              ALL ACTIVITY MONITORED
            </span>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes matrixBlink {
          0%, 49% { opacity: 1; }
          50%, 100% { opacity: 0; }
        }
        @keyframes matrixScan {
          from { transform: scaleX(0) translateX(-50%); opacity: 0; }
          50%  { transform: scaleX(1) translateX(0); opacity: 1; }
          to   { transform: scaleX(0) translateX(50%); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
