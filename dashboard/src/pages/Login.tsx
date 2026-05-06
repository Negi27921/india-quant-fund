import { useEffect, useRef, useState } from "react";

const ACCESS_PHRASE = "One piece is real";
export const AUTH_KEY = "iqf_matrix_auth";

const MATRIX_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*+-=[]|ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜｵﾘｱﾎﾃﾏｹﾒｴｶｷｾﾽｿﾁﾄﾍ".split("");

export function LoginPage({ onAuth }: { onAuth: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const dropsRef = useRef<number[]>([]);
  const [phrase, setPhrase] = useState("");
  const [error, setError] = useState(false);
  const [shake, setShake] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    const FONT_SIZE = 13;

    const init = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      const cols = Math.floor(canvas.width / FONT_SIZE);
      dropsRef.current = Array.from({ length: cols }, () => Math.random() * -80);
    };
    init();

    const onResize = () => init();
    window.addEventListener("resize", onResize);

    const draw = () => {
      const { width: w, height: h } = canvas;
      ctx.fillStyle = "rgba(0,0,0,0.055)";
      ctx.fillRect(0, 0, w, h);
      ctx.font = `${FONT_SIZE}px "JetBrains Mono", monospace`;

      const drops = dropsRef.current;
      for (let i = 0; i < drops.length; i++) {
        const y = drops[i] * FONT_SIZE;
        if (y < 0) { drops[i] += 0.4; continue; }
        const char = MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
        const rnd = Math.random();

        if (rnd > 0.995) ctx.fillStyle = "#ffffff";
        else if (rnd > 0.93) ctx.fillStyle = "#00ff41";
        else if (rnd > 0.7) ctx.fillStyle = "#00cc33";
        else if (rnd > 0.4) ctx.fillStyle = "#009922";
        else ctx.fillStyle = "#004411";

        ctx.fillText(char, i * FONT_SIZE, y);

        if (y > h && Math.random() > 0.975) drops[i] = 0;
        drops[i] += 0.38 + Math.random() * 0.3;
      }
      animRef.current = requestAnimationFrame(draw);
    };
    animRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (phrase.trim().toLowerCase() === ACCESS_PHRASE.toLowerCase()) {
      setSuccess(true);
      setTimeout(() => {
        localStorage.setItem(AUTH_KEY, "1");
        onAuth();
      }, 700);
    } else {
      setError(true);
      setShake(true);
      setTimeout(() => setShake(false), 400);
      setTimeout(() => { setError(false); }, 2200);
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
        background: "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.7) 100%)",
      }} />

      {/* Login panel */}
      <div style={{
        position: "absolute", top: "50%", left: "50%",
        transform: `translate(-50%, -50%) translateX(${shake ? "-8px" : "0"})`,
        transition: shake ? "transform 50ms" : "transform 80ms ease-out",
        width: 390,
        opacity: success ? 0 : 1,
        filter: success ? "brightness(4) saturate(0)" : "none",
        transition2: "opacity 0.5s, filter 0.5s",
      } as React.CSSProperties}>
        <div style={{
          background: "rgba(0,6,0,0.92)",
          border: `1px solid ${error ? "#ff2244" : "#00ff41"}`,
          borderRadius: 2,
          padding: "36px 32px 28px",
          boxShadow: error
            ? "0 0 60px rgba(255,34,68,0.12), inset 0 0 40px rgba(255,34,68,0.04)"
            : "0 0 80px rgba(0,255,65,0.1), inset 0 0 40px rgba(0,255,65,0.03)",
          backdropFilter: "blur(10px)",
          fontFamily: '"JetBrains Mono", monospace',
          transition: "border-color 300ms, box-shadow 300ms",
        }}>

          {/* ASCII logo */}
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <pre style={{
              color: "#00ff41",
              fontSize: 9.5,
              lineHeight: 1.25,
              margin: "0 auto",
              textShadow: "0 0 10px rgba(0,255,65,0.6)",
              whiteSpace: "pre",
              display: "inline-block",
            }}>{`
 ██╗ ██████╗ ███████╗
 ██║██╔═══██╗██╔════╝
 ██║██║   ██║█████╗
 ██║██║▄▄ ██║██╔══╝
 ██║╚██████╔╝██║
 ╚═╝ ╚══▀▀═╝ ╚═╝`.trim()}</pre>

            <div style={{
              color: "#00cc33", fontSize: 9, marginTop: 10,
              letterSpacing: "0.2em", textTransform: "uppercase",
              textShadow: "0 0 6px rgba(0,204,51,0.4)",
            }}>
              INDIA QUANT FUND // v1.0
            </div>

            <div style={{
              width: "80%", height: "1px", margin: "14px auto 0",
              background: "linear-gradient(90deg,transparent,#00ff41,transparent)",
              opacity: 0.35,
            }} />
          </div>

          <form onSubmit={handleSubmit} autoComplete="off">
            <div style={{ marginBottom: 18 }}>
              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                color: error ? "#ff2244" : "#00aa28",
                fontSize: 9.5, letterSpacing: "0.08em", marginBottom: 8,
              }}>
                <span style={{ opacity: 0.6 }}>&gt;</span>
                <span>{error ? "// ACCESS DENIED — RETRY" : "// ENTER ACCESS PHRASE"}</span>
                <span style={{
                  animation: "matrixBlink 1s step-start infinite",
                  color: "#00ff41",
                }}>█</span>
              </div>
              <input
                type="password"
                value={phrase}
                onChange={e => { setPhrase(e.target.value); if (error) setError(false); }}
                placeholder="••••••••••••••••••••"
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
            </div>

            <button
              type="submit"
              style={{
                width: "100%",
                background: "transparent",
                border: "1px solid #00ff41",
                borderRadius: 1,
                padding: "11px 0",
                color: "#00ff41",
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 10.5,
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
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              [ AUTHENTICATE ]
            </button>
          </form>

          <div style={{
            marginTop: 20, paddingTop: 14,
            borderTop: "1px solid rgba(0,255,65,0.1)",
            display: "flex", justifyContent: "space-between",
          }}>
            <span style={{ fontSize: 8, color: "#003311", letterSpacing: "0.05em" }}>
              AUTHORIZED PERSONNEL ONLY
            </span>
            <span style={{ fontSize: 8, color: "#003311", letterSpacing: "0.05em" }}>
              SURVEILLANCE ACTIVE
            </span>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes matrixBlink {
          0%, 49% { opacity: 1; }
          50%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
