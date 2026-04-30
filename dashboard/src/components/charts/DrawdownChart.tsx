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
import type { DrawdownPoint } from "@/api/types";
import { CHART_COLORS } from "@/lib/constants";

interface DrawdownChartProps {
  data: DrawdownPoint[];
  alertLevel?: number;
  limitLevel?: number;
  height?: number;
}

export function DrawdownChart({
  data,
  alertLevel = 8,
  limitLevel = 12,
  height = 180,
}: DrawdownChartProps) {
  const chartData = data.map((d) => ({
    ...d,
    drawdown_neg: -d.drawdown_pct,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="ddGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={CHART_COLORS.danger} stopOpacity={0.3} />
            <stop offset="100%" stopColor={CHART_COLORS.danger} stopOpacity={0.05} />
          </linearGradient>
        </defs>

        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} vertical={false} />

        <XAxis
          dataKey="date"
          tickFormatter={(v) => format(parseISO(v), "MMM yy")}
          tick={{ fontSize: 10, fill: CHART_COLORS.text }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />

        <YAxis
          domain={[-limitLevel * 1.2, 0]}
          tickFormatter={(v) => `${v.toFixed(0)}%`}
          tick={{ fontSize: 10, fill: CHART_COLORS.text }}
          tickLine={false}
          axisLine={false}
          width={40}
        />

        <Tooltip
          formatter={(v: number) => [`${v.toFixed(2)}%`, "Drawdown"]}
          labelFormatter={(l) => format(parseISO(l as string), "dd MMM yyyy")}
          contentStyle={{
            background: "#171A21",
            border: "1px solid #1E2028",
            borderRadius: "8px",
            fontSize: 12,
          }}
        />

        <ReferenceLine y={-alertLevel} stroke={CHART_COLORS.warning} strokeDasharray="4 2" strokeWidth={1} />
        <ReferenceLine y={-limitLevel} stroke={CHART_COLORS.danger} strokeDasharray="4 2" strokeWidth={1} />

        <Area
          type="monotone"
          dataKey="drawdown_neg"
          stroke={CHART_COLORS.danger}
          strokeWidth={1.5}
          fill="url(#ddGradient)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
