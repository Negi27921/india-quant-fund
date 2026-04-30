import { motion } from "framer-motion";
import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: ReactNode;
  subValue?: ReactNode;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
  variant?: "default" | "success" | "danger" | "warning";
  className?: string;
  delay?: number;
}

const variantStyles = {
  default: "border-border",
  success: "border-success/20 bg-success/5",
  danger: "border-danger/20 bg-danger/5",
  warning: "border-warning/20 bg-warning/5",
};

export function StatCard({
  label,
  value,
  subValue,
  icon,
  variant = "default",
  className,
  delay = 0,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "card p-5 flex flex-col gap-3",
        variantStyles[variant],
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="stat-label">{label}</span>
        {icon && (
          <div className="p-1.5 rounded-lg bg-bg-elevated text-text-muted">
            {icon}
          </div>
        )}
      </div>
      <div>
        <div className="stat-value">{value}</div>
        {subValue && (
          <div className="mt-1 text-xs text-text-muted">{subValue}</div>
        )}
      </div>
    </motion.div>
  );
}
