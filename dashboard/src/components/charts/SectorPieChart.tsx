import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { motion } from "framer-motion";
import type { SectorExposure } from "@/api/types";
import { SECTOR_COLORS } from "@/lib/constants";

interface SectorPieChartProps {
  data: SectorExposure[];
  height?: number;
}

const CustomLabel = ({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  percent,
}: {
  cx: number;
  cy: number;
  midAngle: number;
  innerRadius: number;
  outerRadius: number;
  percent: number;
}) => {
  if (percent < 0.05) return null;
  const RADIAN = Math.PI / 180;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x}
      y={y}
      fill="white"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={11}
      fontWeight={500}
    >
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
};

export function SectorPieChart({ data, height = 220 }: SectorPieChartProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, delay: 0.2 }}
    >
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey="weight"
            nameKey="sector"
            cx="50%"
            cy="50%"
            outerRadius={80}
            innerRadius={40}
            labelLine={false}
            label={CustomLabel}
          >
            {data.map((entry) => (
              <Cell
                key={entry.sector}
                fill={SECTOR_COLORS[entry.sector] ?? "#6B7280"}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(v: number) => [`${v.toFixed(1)}%`, "Weight"]}
            contentStyle={{
              background: "#171A21",
              border: "1px solid #1E2028",
              borderRadius: "8px",
              fontSize: 12,
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(value) => (
              <span style={{ fontSize: 11, color: "#8B8FA8" }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
