import { useEffect, useRef } from "react";
import { ColorType, createChart, type IChartApi } from "lightweight-charts";

import type { CurvePoint } from "@/api/client";

type Props = {
  data: CurvePoint[];
};

function parseEpochSeconds(rawTs: string): number | null {
  const raw = String(rawTs || "").trim();
  if (!raw) {
    return null;
  }

  const direct = Date.parse(raw);
  if (!Number.isNaN(direct)) {
    return Math.floor(direct / 1000);
  }

  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const normalizedParsed = Date.parse(normalized);
  if (!Number.isNaN(normalizedParsed)) {
    return Math.floor(normalizedParsed / 1000);
  }

  const match = normalized.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/
  );
  if (!match) {
    return null;
  }
  const [, y, m, d, hh = "0", mm = "0", ss = "0"] = match;
  const epochMs = new Date(
    Number(y),
    Number(m) - 1,
    Number(d),
    Number(hh),
    Number(mm),
    Number(ss)
  ).getTime();
  return Math.floor(epochMs / 1000);
}

function normalizeCurve(data: CurvePoint[]) {
  const rows = data
    .map((item) => {
      const parsed = parseEpochSeconds(item.ts);
      if (parsed == null || !Number.isFinite(parsed)) {
        return null;
      }
      return {
        time: parsed,
        value: item.price,
      };
    })
    .filter((item): item is { time: number; value: number } => Boolean(item))
    .sort((a, b) => a.time - b.time);

  const deduped: Array<{ time: number; value: number }> = [];
  for (const row of rows) {
    const last = deduped[deduped.length - 1];
    if (last && last.time === row.time) {
      deduped[deduped.length - 1] = row;
    } else {
      deduped.push(row);
    }
  }
  return deduped;
}

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
      timeScale: {
        borderColor: "#d1d5db",
        timeVisible: true,
        secondsVisible: false,
      },
      grid: {
        vertLines: { color: "#f1f5f9" },
        horzLines: { color: "#f1f5f9" },
      },
      localization: {
        timeFormatter: (time: unknown) => {
          const value = Number(time);
          if (!Number.isFinite(value)) {
            return "";
          }
          const dt = new Date(value * 1000);
          const mm = String(dt.getMonth() + 1).padStart(2, "0");
          const dd = String(dt.getDate()).padStart(2, "0");
          const hh = String(dt.getHours()).padStart(2, "0");
          const min = String(dt.getMinutes()).padStart(2, "0");
          return `${mm}-${dd} ${hh}:${min}`;
        },
      },
    });

    const series = chart.addLineSeries({
      color: "#0d9488",
      lineWidth: 2,
      priceLineVisible: false,
    });

    const mapped = normalizeCurve(data);

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
