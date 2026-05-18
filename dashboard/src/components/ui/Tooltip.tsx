import { useState, useRef } from "react";
import { createPortal } from "react-dom";

interface TooltipProps {
  content: string;
  children: React.ReactNode;
}

export function Tooltip({ content, children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const ref = useRef<HTMLSpanElement>(null);

  const show = () => {
    if (ref.current) {
      const r = ref.current.getBoundingClientRect();
      setPos({ x: r.left + r.width / 2, y: r.top - 8 });
    }
    setVisible(true);
  };

  return (
    <>
      <span
        ref={ref}
        onMouseEnter={show}
        onMouseLeave={() => setVisible(false)}
        style={{ cursor: "help", borderBottom: "1px dotted var(--text-4)" }}
      >
        {children}
      </span>
      {visible && createPortal(
        <div style={{
          position: "fixed",
          left: pos.x,
          top: pos.y,
          transform: "translate(-50%, -100%)",
          zIndex: 9999,
          background: "var(--surface)",
          border: "1px solid var(--border-2)",
          borderRadius: 6,
          padding: "6px 10px",
          fontSize: 11,
          color: "var(--text-2)",
          fontFamily: "var(--font-body)",
          maxWidth: 220,
          boxShadow: "var(--shadow-md)",
          whiteSpace: "normal",
          lineHeight: 1.4,
          pointerEvents: "none",
        }}>
          {content}
        </div>,
        document.body
      )}
    </>
  );
}
