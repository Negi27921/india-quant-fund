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

    const fontSize = 12;
    const chars = "0123456789₹%+-NIFTYBSESENSEXRELIANCETCSHDFCINFOSYSICICIAXIS";
    let cols = Math.floor(canvas.width / fontSize);
    let drops: number[] = Array.from({ length: cols }, () => Math.random() * -80);

    const onResize = () => {
      setSize();
      cols = Math.floor(canvas.width / fontSize);
      drops = Array.from({ length: cols }, () => Math.random() * -80);
    };
    window.addEventListener("resize", onResize);

    let frame = 0;
    let raf: number;

    const draw = () => {
      frame++;
      if (frame % 3 === 0) {
        ctx.fillStyle = "rgba(9,9,15,0.08)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.font = `${fontSize}px "JetBrains Mono", monospace`;

        for (let i = 0; i < drops.length; i++) {
          const ch = chars[Math.floor(Math.random() * chars.length)];
          const y = drops[i] * fontSize;
          if (drops[i] > 0 && y < canvas.height) {
            const alpha = Math.max(0, 1 - (y / canvas.height) * 1.1);
            ctx.fillStyle = i % 3 === 0
              ? `rgba(6,214,160,${alpha * 0.35})`
              : `rgba(91,127,255,${alpha * 0.4})`;
            ctx.fillText(ch, i * fontSize, y);
          }
          if (y > canvas.height && Math.random() > 0.975) drops[i] = 0;
          drops[i]++;
        }
      }
      raf = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
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
