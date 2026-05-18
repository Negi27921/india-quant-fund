import { useEffect, useRef } from "react";
import { createChart, ColorType, LineStyle } from "lightweight-charts";
import type { DrawdownPoint } from "@/api/types";

interface DrawdownChartProps {
  data: DrawdownPoint[];
  alertLevel?: number;
  limitLevel?: number;
  height?: number;
}

const cssVar = (name: string, fallback = "") =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

export function DrawdownChart({
  data,
  alertLevel = 8,
  limitLevel = 12,
  height = 180,
}: DrawdownChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const gridColor  = "rgba(255,255,255,0.05)";
    const textColor  = cssVar("--text-4", "rgba(255,255,255,0.4)");
    const redColor   = cssVar("--red",   "#f87171");
    const amberColor = cssVar("--amber", "#fbbf24");

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
      leftPriceScale: { visible: false },
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

    // Drawdown area (negative values)
    const ddSeries = chart.addAreaSeries({
      lineColor: redColor,
      topColor: `${redColor}06`,
      bottomColor: `${redColor}44`,
      lineWidth: 1,
      invertFilledArea: true,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      priceFormat: {
        type: "custom",
        formatter: (v: number) => `${v.toFixed(1)}%`,
        minMove: 0.1,
      },
    });

    // drawdown_pct is stored as positive — invert for display
    ddSeries.setData(
      data.map(d => ({
        time: d.date as `${number}-${number}-${number}`,
        value: -d.drawdown_pct,
      }))
    );

    // Alert line
    ddSeries.createPriceLine({
      price: -alertLevel,
      color: amberColor,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: `Alert −${alertLevel}%`,
    });

    // Limit line
    ddSeries.createPriceLine({
      price: -limitLevel,
      color: redColor,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: `Limit −${limitLevel}%`,
    });

    chart.timeScale().fitContent();

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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, height, alertLevel, limitLevel]);

  if (!data.length) return null;

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
