import {
  BarChart as ReBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { CHART_COLORS } from "@/lib/constants";

interface BarChartProps {
  data: Array<Record<string, string | number>>;
  dataKey: string;
  nameKey: string;
  height?: number;
  colorFn?: (value: number, index?: number) => string;
  formatter?: (v: number) => string;
  yTickFormatter?: (v: number) => string;
}

export function SimpleBarChart({
  data,
  dataKey,
  nameKey,
  height = 200,
  colorFn,
  formatter,
  yTickFormatter,
}: BarChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ReBarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} vertical={false} />
        <XAxis
          dataKey={nameKey}
          tick={{ fontSize: 10, fill: CHART_COLORS.text }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tickFormatter={yTickFormatter ?? ((v) => `${v}`)}
          tick={{ fontSize: 10, fill: CHART_COLORS.text }}
          tickLine={false}
          axisLine={false}
          width={40}
        />
        <Tooltip
          formatter={(v: number) =>
            formatter ? formatter(v) : v.toFixed(2)
          }
          contentStyle={{
            background: "#171A21",
            border: "1px solid #1E2028",
            borderRadius: "8px",
            fontSize: 12,
          }}
        />
        <Bar dataKey={dataKey} radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell
              key={index}
              fill={
                colorFn
                  ? colorFn(entry[dataKey] as number, index)
                  : CHART_COLORS.primary
              }
            />
          ))}
        </Bar>
      </ReBarChart>
    </ResponsiveContainer>
  );
}
