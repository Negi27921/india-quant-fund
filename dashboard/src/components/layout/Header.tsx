import { motion } from "framer-motion";
import { RefreshCw, Bell, Clock } from "lucide-react";
import { format } from "date-fns";
import { useLiveStore } from "@/store/live";
import { usePortfolioSummary } from "@/api/queries";
import { formatCurrency, formatPct, pctColor } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  const { data: live, lastUpdate } = useLiveStore();
  const { refetch, isFetching } = usePortfolioSummary();

  return (
    <header className="h-14 border-b border-border bg-bg-surface/80 backdrop-blur-sm flex items-center px-6 gap-4 shrink-0 sticky top-0 z-10">
      {/* Page title */}
      <div className="flex-1 min-w-0">
        <h1 className="text-sm font-semibold text-text-primary truncate">{title}</h1>
        {subtitle && (
          <p className="text-xs text-text-muted truncate">{subtitle}</p>
        )}
      </div>

      {/* Live PnL ticker */}
      {live && (
        <motion.div
          key={live.day_pnl_pct}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="hidden md:flex items-center gap-4"
        >
          <div className="text-right">
            <p className="text-xs text-text-muted">Portfolio</p>
            <p className="text-sm font-mono font-semibold text-text-primary">
              {formatCurrency(live.portfolio_value, true)}
            </p>
          </div>
          <div className="h-8 w-px bg-border" />
          <div className="text-right">
            <p className="text-xs text-text-muted">Day P&L</p>
            <p className={cn("text-sm font-mono font-semibold", pctColor(live.day_pnl_pct))}>
              {formatPct(live.day_pnl_pct)}
            </p>
          </div>
          <div className="h-8 w-px bg-border" />
          <div className="text-right">
            <p className="text-xs text-text-muted">Drawdown</p>
            <p className={cn("text-sm font-mono font-semibold", pctColor(-live.drawdown_pct))}>
              -{Math.abs(live.drawdown_pct).toFixed(2)}%
            </p>
          </div>
        </motion.div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        {lastUpdate && (
          <div className="hidden lg:flex items-center gap-1 text-xs text-text-muted">
            <Clock className="w-3 h-3" />
            <span>{format(lastUpdate, "HH:mm:ss")}</span>
          </div>
        )}

        <button
          onClick={() => refetch()}
          className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
        >
          <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin")} />
        </button>

        <button className="relative p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-danger rounded-full" />
        </button>
      </div>
    </header>
  );
}
