import { useEffect, useRef } from "react";
import { createChart, ColorType, LineStyle } from "lightweight-charts";
import { motion } from "framer-motion";
import type { EquityPoint } from "@/api/types";
import { formatCurrency, formatPct } from "@/lib/utils";

interface EquityChartProps {
  data: EquityPoint[];
  height?: number;
  showBenchmark?: boolean;
}

const cssVar = (name: string, fallback = "") =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

export function EquityChart({ data, height = 280, showBenchmark = true }: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const textColor   = cssVar("--text-4", "rgba(255,255,255,0.4)");
    const gridColor   = "rgba(255,255,255,0.05)";
    const accentColor = cssVar("--accent", "#7c3aed");
    const greenColor  = cssVar("--green",  "#34d399");

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      rightPriceScale: {
        borderColor: gridColor,
        textColor,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      leftPriceScale: {
        visible: false,
      },
      timeScale: {
        borderColor: gridColor,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      crosshair: {
        horzLine: { color: "rgba(255,255,255,0.2)", width: 1, style: LineStyle.Dashed },
        vertLine: { color: "rgba(255,255,255,0.2)", width: 1, style: LineStyle.Dashed },
      },
      handleScroll: false,
      handleScale: false,
    });

    // Portfolio equity area
    const portfolioSeries = chart.addAreaSeries({
      lineColor: accentColor,
      topColor: `${accentColor}44`,
      bottomColor: `${accentColor}04`,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      priceFormat: {
        type: "custom",
        formatter: (v: number) => formatCurrency(v, true),
        minMove: 1,
      },
    });

    portfolioSeries.setData(
      data.map(d => ({ time: d.date as `${number}-${number}-${number}`, value: d.portfolio_value }))
    );

    // Benchmark line (secondary axis)
    if (showBenchmark && data.some(d => d.benchmark_ret != null)) {
      const benchSeries = chart.addLineSeries({
        color: `${greenColor}aa`,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: {
          type: "custom",
          formatter: (v: number) => formatPct(v, 2, true),
          minMove: 0.01,
        },
        priceScaleId: "benchmark",
      });

      chart.priceScale("benchmark").applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.6 },
        visible: false,
      });

      benchSeries.setData(
        data.map(d => ({
          time: d.date as `${number}-${number}-${number}`,
          value: d.benchmark_ret ?? 0,
        }))
      );
    }

    chart.timeScale().fitContent();

    // Tooltip overlay
    const tooltipEl = document.createElement("div");
    tooltipEl.style.cssText = `
      position:absolute; top:12px; left:12px; pointer-events:none;
      background:var(--surface-2); border:1px solid var(--border);
      border-radius:8px; padding:8px 12px; font-size:11px;
      font-family:'JetBrains Mono',monospace; display:none; z-index:10;
      box-shadow:0 4px 16px rgba(0,0,0,0.4);
    `;
    containerRef.current.style.position = "relative";
    containerRef.current.appendChild(tooltipEl);

    chart.subscribeCrosshairMove(param => {
      if (!param.time || !param.seriesData.size) {
        tooltipEl.style.display = "none";
        return;
      }
      const pv = param.seriesData.get(portfolioSeries) as { value?: number } | undefined;
      if (!pv?.value) { tooltipEl.style.display = "none"; return; }

      const dateStr = String(param.time);
      const pct = ((pv.value - data[0].portfolio_value) / data[0].portfolio_value) * 100;
      tooltipEl.innerHTML = `
        <div style="color:var(--text-3);font-size:10px;margin-bottom:4px">${dateStr}</div>
        <div style="color:var(--text-1);font-weight:700">${formatCurrency(pv.value, true)}</div>
        <div style="color:${pct >= 0 ? "var(--green)" : "var(--red)"};font-size:10px">
          ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%
        </div>
      `;
      tooltipEl.style.display = "block";
    });

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [data, height, showBenchmark]);

  if (!data.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.1 }}
    >
      <div ref={containerRef} style={{ width: "100%", height, position: "relative" }} />
    </motion.div>
  );
}
