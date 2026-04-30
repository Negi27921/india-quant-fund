import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type BadgeVariant = "success" | "danger" | "warning" | "primary" | "neutral";

const variants: Record<BadgeVariant, string> = {
  success: "badge-success",
  danger: "badge-danger",
  warning: "badge-warning",
  primary: "badge-primary",
  neutral: "badge-neutral",
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}

export function Badge({ variant = "neutral", children, className, dot }: BadgeProps) {
  return (
    <span className={cn(variants[variant], className)}>
      {dot && (
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full",
            variant === "success" && "bg-success",
            variant === "danger" && "bg-danger",
            variant === "warning" && "bg-warning",
            variant === "primary" && "bg-primary",
            variant === "neutral" && "bg-text-muted"
          )}
        />
      )}
      {children}
    </span>
  );
}

export function OrderStatusBadge({ status }: { status: string }) {
  const map: Record<string, BadgeVariant> = {
    FILLED: "success",
    PENDING: "warning",
    REJECTED: "danger",
    CANCELLED: "neutral",
  };
  return (
    <Badge variant={map[status] ?? "neutral"} dot>
      {status}
    </Badge>
  );
}

export function SideBadge({ side }: { side: string }) {
  return (
    <Badge variant={side === "BUY" ? "success" : "danger"}>
      {side}
    </Badge>
  );
}
