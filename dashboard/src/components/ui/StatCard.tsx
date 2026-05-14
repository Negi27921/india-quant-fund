import { useState } from "react";
import { motion } from "framer-motion";
import { type ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: ReactNode;
  subValue?: ReactNode;
  icon?: ReactNode;
  variant?: "default" | "success" | "danger" | "warning";
  className?: string;
  delay?: number;
}

const variantMap = {
  default: { accentColor: "var(--accent)", glowColor: "var(--accent-dim)", hoverBorder: "var(--accent-border)" },
  success: { accentColor: "var(--green)", glowColor: "var(--green-glow)", hoverBorder: "var(--border-green)" },
  danger:  { accentColor: "var(--red)",   glowColor: "var(--red-glow)",   hoverBorder: "var(--border-red)" },
  warning: { accentColor: "var(--amber)", glowColor: "transparent",       hoverBorder: "rgba(255,176,23,0.4)" },
};

export function StatCard({ label, value, subValue, icon, variant = "default", className, delay = 0 }: StatCardProps) {
  const v = variantMap[variant];
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: "var(--card-bg)",
        border: `1px solid ${hovered ? v.hoverBorder : "var(--border)"}`,
        borderRadius: 14,
        padding: "20px 22px",
        position: "relative",
        overflow: "hidden",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        boxShadow: hovered
          ? `0 8px 32px rgba(0,0,0,0.15), 0 0 0 1px ${v.hoverBorder}`
          : "none",
        transition: "border-color 200ms, box-shadow 200ms",
      }}
    >
      {/* Top gradient accent line */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: `linear-gradient(90deg, transparent, ${v.accentColor}60, transparent)`,
      }} />

      {/* Inner top highlight */}
      <div style={{
        position: "absolute", inset: 0, borderRadius: 14,
        background: "linear-gradient(135deg, rgba(255,255,255,0.02) 0%, transparent 50%)",
        pointerEvents: "none",
      }} />

      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
        <span style={{
          fontFamily: "var(--font-body)",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: "var(--text-3)",
        }}>
          {label}
        </span>
        {icon && (
          <div style={{
            width: 28, height: 28, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
            background: `color-mix(in srgb, ${v.accentColor} 15%, transparent)`,
            border: `1px solid color-mix(in srgb, ${v.accentColor} 25%, transparent)`,
            color: v.accentColor,
          }}>
            {icon}
          </div>
        )}
      </div>

      <div>
        <div style={{
          fontFamily: "var(--font-body)",
          fontSize: 30,
          fontWeight: 700,
          letterSpacing: "-0.03em",
          color: "var(--text-1)",
          lineHeight: 1.1,
          fontFeatureSettings: '"tnum"',
        }}>
          {value}
        </div>
        {subValue && (
          <div style={{
            marginTop: 6,
            fontFamily: "var(--font-body)",
            fontSize: 12,
            color: "var(--text-3)",
            fontWeight: 400,
          }}>
            {subValue}
          </div>
        )}
      </div>
    </motion.div>
  );
}
