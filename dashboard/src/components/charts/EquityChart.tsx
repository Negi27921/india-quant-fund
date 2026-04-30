import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { format, parseISO } from "date-fns";
import { motion } from "framer-motion";
import type { EquityPoint } from "@/api/types";
import { formatCurrency, formatPct } from "@/lib/utils";
import { CHART_COLORS } from "@/lib/constants";

interface EquityChartProps {
  data: EquityPoint[];
  height?: number;
  showBenchmark?: boolean;
}

const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-bg-elevated border border-border rounded-lg p-3 shadow-card text-xs space-y-1.5">
      <p className="text-text-muted font-medium">
        {label ? format(parseISO(label), "dd MMM yyyy") : ""}
      </p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: entry.color }}
            />
            <span className="text-text-muted capitalize">
              {entry.name === "portfolio_value" ? "Portfolio" : "Nifty 50"}
            </span>
          </div>
          <span className="font-mono font-medium text-text-primary">
            {entry.name === "portfolio_value"
              ? formatCurrency(entry.value, true)
              : formatPct(entry.value, 2, true)}
          </span>
        </div>
      ))}
    </div>
  );
};

export function EquityChart({ data, height = 280, showBenchmark = true }: EquityChartProps) {
  if (!data.length) return null;

  const minVal = Math.min(...data.map((d) => d.portfolio_value));
  const maxVal = Math.max(...data.map((d) => d.portfolio_value));
  const range = maxVal - minVal;
  const startVal = data[0]?.portfolio_value ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.1 }}
    >
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_COLORS.primary} stopOpacity={0.25} />
              <stop offset="100%" stopColor={CHART_COLORS.primary} stopOpacity={0.0} />
            </linearGradient>
            <linearGradient id="benchmarkGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_COLORS.success} stopOpacity={0.1} />
              <stop offset="100%" stopColor={CHART_COLORS.success} stopOpacity={0.0} />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke={CHART_COLORS.grid}
            vertical={false}
          />

          <XAxis
            dataKey="date"
            tickFormatter={(v) => format(parseISO(v), "MMM yy")}
            tick={{ fontSize: 10, fill: CHART_COLORS.text }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />

          <YAxis
            yAxisId="left"
            domain={[minVal - range * 0.05, maxVal + range * 0.05]}
            tickFormatter={(v) => formatCurrency(v, true)}
            tick={{ fontSize: 10, fill: CHART_COLORS.text }}
            tickLine={false}
            axisLine={false}
            width={60}
          />

          {showBenchmark && (
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`}
              tick={{ fontSize: 10, fill: CHART_COLORS.text }}
              tickLine={false}
              axisLine={false}
              width={50}
            />
          )}

          <ReferenceLine
            yAxisId="left"
            y={startVal}
            stroke={CHART_COLORS.grid}
            strokeDasharray="4 2"
          />

          <Tooltip content={<CustomTooltip />} />

          <Area
            yAxisId="left"
            type="monotone"
            dataKey="portfolio_value"
            stroke={CHART_COLORS.primary}
            strokeWidth={2}
            fill="url(#equityGradient)"
            dot={false}
            activeDot={{ r: 4, fill: CHART_COLORS.primary, stroke: "#0A0B0D", strokeWidth: 2 }}
          />

          {showBenchmark && (
            <Area
              yAxisId="right"
              type="monotone"
              dataKey="benchmark_ret"
              stroke={CHART_COLORS.success}
              strokeWidth={1.5}
              strokeDasharray="4 2"
              fill="none"
              dot={false}
              activeDot={{ r: 3, fill: CHART_COLORS.success }}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
