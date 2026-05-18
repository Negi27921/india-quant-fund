import { useEffect, useRef } from "react";

export function MatrixRain() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const setSize = () => {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    setSize();
    window.addEventListener("resize", setSize);

    let t = 0;
    let raf: number;

    const orbs = [
      { x: 0.12, y: 0.25, r: 0.50, speed: 0.0003, phase: 0.0 },
      { x: 0.78, y: 0.15, r: 0.40, speed: 0.0002, phase: 2.1 },
      { x: 0.55, y: 0.72, r: 0.35, speed: 0.0004, phase: 4.2 },
      { x: 0.88, y: 0.78, r: 0.30, speed: 0.0003, phase: 1.0 },
    ];

    const draw = () => {
      t += 1;
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      const base = ctx.createLinearGradient(0, 0, w, h);
      base.addColorStop(0, "#EBE7E7");
      base.addColorStop(1, "#DAD8D8");
      ctx.fillStyle = base;
      ctx.fillRect(0, 0, w, h);

      for (const o of orbs) {
        const cx = w * (o.x + Math.sin(t * o.speed + o.phase) * 0.08);
        const cy = h * (o.y + Math.cos(t * o.speed + o.phase) * 0.07);
        const r  = Math.min(w, h) * o.r;
        const g  = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
        g.addColorStop(0, "rgba(106,98,86,0.08)");
        g.addColorStop(1, "rgba(106,98,86,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, h);
      }

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", setSize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        top: 0, left: 0,
        width: "100vw", height: "100vh",
        pointerEvents: "none",
        zIndex: 0,
      }}
    />
  );
}
