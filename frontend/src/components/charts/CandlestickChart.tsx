import { useEffect, useRef } from "react";
import { ColorType, createChart, type IChartApi } from "lightweight-charts";

import type { KLineBar } from "@/api/client";

type Props = {
  data: KLineBar[];
};

export function CandlestickChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      height: 320,
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

    const series = chart.addCandlestickSeries({
      upColor: "#0f766e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#0f766e",
      wickDownColor: "#ef4444",
    });

    const mapped = data.map((item) => ({
      time: Math.floor(new Date(item.ts).getTime() / 1000),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
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
