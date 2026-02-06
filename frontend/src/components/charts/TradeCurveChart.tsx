import { useEffect, useRef } from "react";
import { ColorType, createChart, type IChartApi } from "lightweight-charts";

import type { CurvePoint } from "@/api/client";

type Props = {
  data: CurvePoint[];
};

export function TradeCurveChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      height: 260,
      layout: {
        background: { type: ColorType.Solid, color: "#fffdf7" },
        textColor: "#1f2937",
      },
      rightPriceScale: { borderColor: "#d1d5db" },
      timeScale: { borderColor: "#d1d5db" },
      grid: {
        vertLines: { color: "#f1f5f9" },
        horzLines: { color: "#f1f5f9" },
      },
    });

    const series = chart.addLineSeries({
      color: "#0d9488",
      lineWidth: 2,
      priceLineVisible: false,
    });

    const mapped = data.map((item) => ({
      time: Math.floor(new Date(item.ts).getTime() / 1000),
      value: item.price,
    }));

    // @ts-expect-error lightweight-charts time type accepts unix epoch seconds.
    series.setData(mapped);
    chart.timeScale().fitContent();

    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  return <div ref={containerRef} className="w-full overflow-hidden rounded-md border" />;
}
