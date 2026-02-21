import { useEffect, useMemo, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";

import type { KLineBar } from "@/api/client";
import {
  bollinger,
  ema,
  macd,
  normalizeCandles,
  rsi,
  sma,
  type CandlePoint,
} from "@/lib/technicalIndicators";

export type IndicatorVisibility = {
  sma5: boolean;
  sma10: boolean;
  sma20: boolean;
  ema12: boolean;
  ema26: boolean;
  boll: boolean;
  rsi: boolean;
  macd: boolean;
};

type Props = {
  data: KLineBar[];
  indicators?: IndicatorVisibility;
};

const DEFAULT_INDICATORS: IndicatorVisibility = {
  sma5: true,
  sma10: true,
  sma20: false,
  ema12: false,
  ema26: false,
  boll: false,
  rsi: true,
  macd: true,
};

function toLineData(candles: CandlePoint[], values: Array<number | null>) {
  return candles.flatMap((item, index) => {
    const value = values[index];
    if (value == null || !Number.isFinite(value)) {
      return [];
    }
    return [{ time: item.time as Time, value }];
  });
}

export function CandlestickChart({ data, indicators }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const oscillatorContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const oscillatorChartRef = useRef<IChartApi | null>(null);

  const visibility = useMemo(
    () => ({ ...DEFAULT_INDICATORS, ...(indicators ?? {}) }),
    [indicators]
  );

  useEffect(() => {
    if (!containerRef.current) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }
    if (oscillatorChartRef.current) {
      oscillatorChartRef.current.remove();
      oscillatorChartRef.current = null;
    }

    const isDaily = data[0]?.interval === "1d";
    const showOscillator = visibility.rsi || visibility.macd;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: showOscillator ? 300 : 360,
      layout: {
        background: { type: ColorType.Solid, color: "#fffdf7" },
        textColor: "#1f2937",
      },
      rightPriceScale: { borderColor: "#d1d5db" },
      timeScale: {
        borderColor: "#d1d5db",
        timeVisible: !isDaily,
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
          const yyyy = dt.getFullYear();
          const mm = String(dt.getMonth() + 1).padStart(2, "0");
          const dd = String(dt.getDate()).padStart(2, "0");
          if (isDaily) {
            return `${yyyy}-${mm}-${dd}`;
          }
          const hh = String(dt.getHours()).padStart(2, "0");
          const min = String(dt.getMinutes()).padStart(2, "0");
          return `${mm}-${dd} ${hh}:${min}`;
        },
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#0f766e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#0f766e",
      wickDownColor: "#ef4444",
    });

    const mapped = normalizeCandles(data);
    const candleSeriesData = mapped.map((item) => ({
      time: item.time as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));
    const closeValues = mapped.map((item) => item.close);

    if (visibility.sma5) {
      const sma5 = chart.addLineSeries({ color: "#2563eb", lineWidth: 2, priceLineVisible: false });
      sma5.setData(toLineData(mapped, sma(closeValues, 5)));
    }
    if (visibility.sma10) {
      const sma10 = chart.addLineSeries({ color: "#7c3aed", lineWidth: 2, priceLineVisible: false });
      sma10.setData(toLineData(mapped, sma(closeValues, 10)));
    }
    if (visibility.sma20) {
      const sma20 = chart.addLineSeries({ color: "#0d9488", lineWidth: 2, priceLineVisible: false });
      sma20.setData(toLineData(mapped, sma(closeValues, 20)));
    }
    if (visibility.ema12) {
      const ema12 = chart.addLineSeries({ color: "#ea580c", lineWidth: 2, priceLineVisible: false });
      ema12.setData(toLineData(mapped, ema(closeValues, 12)));
    }
    if (visibility.ema26) {
      const ema26 = chart.addLineSeries({ color: "#a16207", lineWidth: 2, priceLineVisible: false });
      ema26.setData(toLineData(mapped, ema(closeValues, 26)));
    }
    if (visibility.boll) {
      const bands = bollinger(closeValues, 20, 2);
      const upper = chart.addLineSeries({ color: "#9333ea", lineWidth: 1, priceLineVisible: false });
      const middle = chart.addLineSeries({ color: "#db2777", lineWidth: 1, priceLineVisible: false });
      const lower = chart.addLineSeries({ color: "#9333ea", lineWidth: 1, priceLineVisible: false });
      upper.setData(toLineData(mapped, bands.upper));
      middle.setData(toLineData(mapped, bands.mid));
      lower.setData(toLineData(mapped, bands.lower));
    }

    series.setData(candleSeriesData);
    chart.timeScale().fitContent();

    chartRef.current = chart;

    if (showOscillator && oscillatorContainerRef.current) {
      const oscillatorChart = createChart(oscillatorContainerRef.current, {
        width: oscillatorContainerRef.current.clientWidth,
        height: 140,
        layout: {
          background: { type: ColorType.Solid, color: "#fffdf7" },
          textColor: "#475569",
        },
        rightPriceScale: { borderColor: "#d1d5db" },
        timeScale: {
          borderColor: "#d1d5db",
          timeVisible: !isDaily,
          secondsVisible: false,
        },
        grid: {
          vertLines: { color: "#f1f5f9" },
          horzLines: { color: "#f1f5f9" },
        },
      });

      if (visibility.rsi) {
        const rsiSeries = oscillatorChart.addLineSeries({
          color: "#0891b2",
          lineWidth: 2,
          priceLineVisible: false,
        });
        rsiSeries.setData(toLineData(mapped, rsi(closeValues, 14)));
        const upperLine = oscillatorChart.addLineSeries({ color: "#94a3b8", lineWidth: 1, priceLineVisible: false });
        const lowerLine = oscillatorChart.addLineSeries({ color: "#94a3b8", lineWidth: 1, priceLineVisible: false });
        upperLine.setData(mapped.map((item) => ({ time: item.time as Time, value: 70 })));
        lowerLine.setData(mapped.map((item) => ({ time: item.time as Time, value: 30 })));
      }

      if (visibility.macd) {
        const lines = macd(closeValues);
        const hist = oscillatorChart.addHistogramSeries({
          base: 0,
          priceLineVisible: false,
        });
        const dif = oscillatorChart.addLineSeries({ color: "#dc2626", lineWidth: 1, priceLineVisible: false });
        const dea = oscillatorChart.addLineSeries({ color: "#2563eb", lineWidth: 1, priceLineVisible: false });
        hist.setData(
          mapped.flatMap((item, index) => {
            const value = lines.hist[index];
            if (value == null || !Number.isFinite(value)) {
              return [];
            }
            return [{ time: item.time as Time, value, color: value >= 0 ? "#16a34a" : "#ef4444" }];
          })
        );
        dif.setData(toLineData(mapped, lines.dif));
        dea.setData(toLineData(mapped, lines.dea));
      }

      oscillatorChart.timeScale().fitContent();
      chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
        if (!range) return;
        oscillatorChart.timeScale().setVisibleRange(range);
      });
      oscillatorChartRef.current = oscillatorChart;
    }

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
      if (oscillatorContainerRef.current && oscillatorChartRef.current) {
        oscillatorChartRef.current.applyOptions({
          width: oscillatorContainerRef.current.clientWidth,
        });
      }
    });
    resizeObserver.observe(containerRef.current);
    if (oscillatorContainerRef.current) {
      resizeObserver.observe(oscillatorContainerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      if (oscillatorChartRef.current) {
        oscillatorChartRef.current.remove();
        oscillatorChartRef.current = null;
      }
    };
  }, [data, visibility]);

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="w-full overflow-hidden rounded-md border" />
      {(visibility.rsi || visibility.macd) && (
        <div
          ref={oscillatorContainerRef}
          className="w-full overflow-hidden rounded-md border"
        />
      )}
    </div>
  );
}
