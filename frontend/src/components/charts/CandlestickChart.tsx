import { useEffect, useMemo, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type SeriesType,
  type Time,
} from "lightweight-charts";

import type { KLineBar } from "@/api/client";
import {
  atr,
  bbiboll,
  bollinger,
  cci,
  ema,
  kdj,
  macd,
  normalizeCandles,
  rsi,
  sma,
  williamsR,
  type CandlePoint,
} from "@/lib/technicalIndicators";

export type IndicatorVisibility = {
  sma5: boolean;
  sma10: boolean;
  sma20: boolean;
  ema12: boolean;
  ema26: boolean;
  boll: boolean;
  bbiboll: boolean;
  rsi: boolean;
  macd: boolean;
  kdj: boolean;
  wr: boolean;
  cci: boolean;
  atr: boolean;
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
  bbiboll: false,
  rsi: true,
  macd: true,
  kdj: false,
  wr: false,
  cci: false,
  atr: false,
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

function createBaseChart(
  container: HTMLDivElement,
  options: {
    isDaily: boolean;
    height: number;
    textColor: string;
  }
) {
  const { isDaily, height, textColor } = options;
  return createChart(container, {
    width: container.clientWidth,
    height,
    layout: {
      background: { type: ColorType.Solid, color: "#fffdf7" },
      textColor,
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
}

function bindVisibleRangeSync(charts: IChartApi[]) {
  if (charts.length <= 1) {
    return () => {};
  }
  let syncing = false;
  const unsubs: Array<() => void> = [];

  for (const source of charts) {
    const handler = (range: any) => {
      if (!range || syncing) {
        return;
      }
      syncing = true;
      try {
        for (const target of charts) {
          if (target === source) {
            continue;
          }
          target.timeScale().setVisibleRange(range);
        }
      } finally {
        syncing = false;
      }
    };
    source.timeScale().subscribeVisibleTimeRangeChange(handler);
    unsubs.push(() => source.timeScale().unsubscribeVisibleTimeRangeChange(handler));
  }

  return () => {
    for (const off of unsubs) {
      off();
    }
  };
}

type CrosshairTarget = {
  chart: IChartApi;
  series: ISeriesApi<SeriesType, Time>;
  valuesByTime: Map<number, number>;
};

function toTimeKey(time: unknown): number | null {
  const value = Number(time);
  if (!Number.isFinite(value)) {
    return null;
  }
  return value;
}

function bindCrosshairSync(targets: CrosshairTarget[]) {
  if (targets.length <= 1) {
    return () => {};
  }

  let syncing = false;
  const unsubs: Array<() => void> = [];

  for (const sourceTarget of targets) {
    const handler = (param: MouseEventParams<Time>) => {
      if (syncing) {
        return;
      }
      syncing = true;
      try {
        const key = toTimeKey(param.time);
        for (const target of targets) {
          if (target.chart === sourceTarget.chart) {
            continue;
          }
          if (key == null) {
            target.chart.clearCrosshairPosition();
            continue;
          }
          const price = target.valuesByTime.get(key);
          if (price == null || !Number.isFinite(price)) {
            target.chart.clearCrosshairPosition();
            continue;
          }
          target.chart.setCrosshairPosition(price, key as Time, target.series);
        }
      } finally {
        syncing = false;
      }
    };

    sourceTarget.chart.subscribeCrosshairMove(handler);
    unsubs.push(() => sourceTarget.chart.unsubscribeCrosshairMove(handler));
  }

  return () => {
    for (const off of unsubs) {
      off();
    }
  };
}

export function CandlestickChart({ data, indicators }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rsiContainerRef = useRef<HTMLDivElement | null>(null);
  const macdContainerRef = useRef<HTMLDivElement | null>(null);
  const kdjContainerRef = useRef<HTMLDivElement | null>(null);
  const wrContainerRef = useRef<HTMLDivElement | null>(null);
  const cciContainerRef = useRef<HTMLDivElement | null>(null);
  const atrContainerRef = useRef<HTMLDivElement | null>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);
  const kdjChartRef = useRef<IChartApi | null>(null);
  const wrChartRef = useRef<IChartApi | null>(null);
  const cciChartRef = useRef<IChartApi | null>(null);
  const atrChartRef = useRef<IChartApi | null>(null);

  const visibility = useMemo(
    () => ({ ...DEFAULT_INDICATORS, ...(indicators ?? {}) }),
    [indicators]
  );

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }
    if (rsiChartRef.current) {
      rsiChartRef.current.remove();
      rsiChartRef.current = null;
    }
    if (macdChartRef.current) {
      macdChartRef.current.remove();
      macdChartRef.current = null;
    }
    if (kdjChartRef.current) {
      kdjChartRef.current.remove();
      kdjChartRef.current = null;
    }
    if (wrChartRef.current) {
      wrChartRef.current.remove();
      wrChartRef.current = null;
    }
    if (cciChartRef.current) {
      cciChartRef.current.remove();
      cciChartRef.current = null;
    }
    if (atrChartRef.current) {
      atrChartRef.current.remove();
      atrChartRef.current = null;
    }

    const isDaily = data[0]?.interval === "1d";
    const lowerPaneCount =
      Number(visibility.rsi) +
      Number(visibility.macd) +
      Number(visibility.kdj) +
      Number(visibility.wr) +
      Number(visibility.cci) +
      Number(visibility.atr);
    const mainChart = createBaseChart(containerRef.current, {
      isDaily,
      height: lowerPaneCount > 0 ? 300 : 360,
      textColor: "#1f2937",
    });

    const candleSeries = mainChart.addCandlestickSeries({
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
    const closeValuesByTime = new Map<number, number>(
      mapped.map((item) => [item.time, item.close])
    );

    if (visibility.sma5) {
      const sma5 = mainChart.addLineSeries({
        color: "#2563eb",
        lineWidth: 2,
        priceLineVisible: false,
      });
      sma5.setData(toLineData(mapped, sma(closeValues, 5)));
    }
    if (visibility.sma10) {
      const sma10 = mainChart.addLineSeries({
        color: "#7c3aed",
        lineWidth: 2,
        priceLineVisible: false,
      });
      sma10.setData(toLineData(mapped, sma(closeValues, 10)));
    }
    if (visibility.sma20) {
      const sma20 = mainChart.addLineSeries({
        color: "#0d9488",
        lineWidth: 2,
        priceLineVisible: false,
      });
      sma20.setData(toLineData(mapped, sma(closeValues, 20)));
    }
    if (visibility.ema12) {
      const ema12 = mainChart.addLineSeries({
        color: "#ea580c",
        lineWidth: 2,
        priceLineVisible: false,
      });
      ema12.setData(toLineData(mapped, ema(closeValues, 12)));
    }
    if (visibility.ema26) {
      const ema26 = mainChart.addLineSeries({
        color: "#a16207",
        lineWidth: 2,
        priceLineVisible: false,
      });
      ema26.setData(toLineData(mapped, ema(closeValues, 26)));
    }
    if (visibility.boll) {
      const bands = bollinger(closeValues, 20, 2);
      const upper = mainChart.addLineSeries({
        color: "#9333ea",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const middle = mainChart.addLineSeries({
        color: "#db2777",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const lower = mainChart.addLineSeries({
        color: "#9333ea",
        lineWidth: 1,
        priceLineVisible: false,
      });
      upper.setData(toLineData(mapped, bands.upper));
      middle.setData(toLineData(mapped, bands.mid));
      lower.setData(toLineData(mapped, bands.lower));
    }
    if (visibility.bbiboll) {
      const bands = bbiboll(closeValues, 10, 3);
      const upper = mainChart.addLineSeries({
        color: "#0284c7",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const middle = mainChart.addLineSeries({
        color: "#0f766e",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const lower = mainChart.addLineSeries({
        color: "#0284c7",
        lineWidth: 1,
        priceLineVisible: false,
      });
      upper.setData(toLineData(mapped, bands.upper));
      middle.setData(toLineData(mapped, bands.bbi));
      lower.setData(toLineData(mapped, bands.lower));
    }

    candleSeries.setData(candleSeriesData);
    chartRef.current = mainChart;

    const linkedCharts: IChartApi[] = [mainChart];
    const crosshairTargets: CrosshairTarget[] = [
      {
        chart: mainChart,
        series: candleSeries,
        valuesByTime: closeValuesByTime,
      },
    ];

    if (visibility.rsi && rsiContainerRef.current) {
      const rsiChart = createBaseChart(rsiContainerRef.current, {
        isDaily,
        height: 130,
        textColor: "#475569",
      });
      const rsiValues = rsi(closeValues, 14);
      const rsiSeries = rsiChart.addLineSeries({
        color: "#0891b2",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const upperLine = rsiChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const lowerLine = rsiChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });
      rsiSeries.setData(toLineData(mapped, rsiValues));
      upperLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: 70 }))
      );
      lowerLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: 30 }))
      );

      const rsiValuesByTime = new Map<number, number>();
      rsiValues.forEach((value, index) => {
        if (value == null || !Number.isFinite(value)) {
          return;
        }
        const ts = mapped[index]?.time;
        if (ts != null) {
          rsiValuesByTime.set(ts, value);
        }
      });

      rsiChartRef.current = rsiChart;
      linkedCharts.push(rsiChart);
      crosshairTargets.push({
        chart: rsiChart,
        series: rsiSeries,
        valuesByTime: rsiValuesByTime,
      });
    }

    if (visibility.macd && macdContainerRef.current) {
      const macdChart = createBaseChart(macdContainerRef.current, {
        isDaily,
        height: 150,
        textColor: "#475569",
      });
      const lines = macd(closeValues);
      const hist = macdChart.addHistogramSeries({
        base: 0,
        priceLineVisible: false,
      });
      const dif = macdChart.addLineSeries({
        color: "#dc2626",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const dea = macdChart.addLineSeries({
        color: "#2563eb",
        lineWidth: 1,
        priceLineVisible: false,
      });
      hist.setData(
        mapped.flatMap((item, index) => {
          const value = lines.hist[index];
          if (value == null || !Number.isFinite(value)) {
            return [];
          }
          return [
            {
              time: item.time as Time,
              value,
              color: value >= 0 ? "#16a34a" : "#ef4444",
            },
          ];
        })
      );
      dif.setData(toLineData(mapped, lines.dif));
      dea.setData(toLineData(mapped, lines.dea));

      const macdValuesByTime = new Map<number, number>();
      lines.dif.forEach((value, index) => {
        if (value == null || !Number.isFinite(value)) {
          return;
        }
        const ts = mapped[index]?.time;
        if (ts != null) {
          macdValuesByTime.set(ts, value);
        }
      });

      macdChartRef.current = macdChart;
      linkedCharts.push(macdChart);
      crosshairTargets.push({
        chart: macdChart,
        series: dif,
        valuesByTime: macdValuesByTime,
      });
    }

    if (visibility.kdj && kdjContainerRef.current) {
      const kdjChart = createBaseChart(kdjContainerRef.current, {
        isDaily,
        height: 140,
        textColor: "#475569",
      });
      const kdjValues = kdj(mapped, 9);
      const kLine = kdjChart.addLineSeries({
        color: "#2563eb",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const dLine = kdjChart.addLineSeries({
        color: "#ea580c",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const jLine = kdjChart.addLineSeries({
        color: "#9333ea",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const upperLine = kdjChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const lowerLine = kdjChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });

      kLine.setData(toLineData(mapped, kdjValues.k));
      dLine.setData(toLineData(mapped, kdjValues.d));
      jLine.setData(toLineData(mapped, kdjValues.j));
      upperLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: 80 }))
      );
      lowerLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: 20 }))
      );

      const kdjValuesByTime = new Map<number, number>();
      kdjValues.k.forEach((value, index) => {
        if (value == null || !Number.isFinite(value)) {
          return;
        }
        const ts = mapped[index]?.time;
        if (ts != null) {
          kdjValuesByTime.set(ts, value);
        }
      });

      kdjChartRef.current = kdjChart;
      linkedCharts.push(kdjChart);
      crosshairTargets.push({
        chart: kdjChart,
        series: kLine,
        valuesByTime: kdjValuesByTime,
      });
    }

    if (visibility.wr && wrContainerRef.current) {
      const wrChart = createBaseChart(wrContainerRef.current, {
        isDaily,
        height: 130,
        textColor: "#475569",
      });
      const wrValues = williamsR(mapped, 14);
      const wrLine = wrChart.addLineSeries({
        color: "#0f766e",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const upperLine = wrChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const lowerLine = wrChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });

      wrLine.setData(toLineData(mapped, wrValues));
      upperLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: -20 }))
      );
      lowerLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: -80 }))
      );

      const wrValuesByTime = new Map<number, number>();
      wrValues.forEach((value, index) => {
        if (value == null || !Number.isFinite(value)) {
          return;
        }
        const ts = mapped[index]?.time;
        if (ts != null) {
          wrValuesByTime.set(ts, value);
        }
      });

      wrChartRef.current = wrChart;
      linkedCharts.push(wrChart);
      crosshairTargets.push({
        chart: wrChart,
        series: wrLine,
        valuesByTime: wrValuesByTime,
      });
    }

    if (visibility.cci && cciContainerRef.current) {
      const cciChart = createBaseChart(cciContainerRef.current, {
        isDaily,
        height: 130,
        textColor: "#475569",
      });
      const cciValues = cci(mapped, 20);
      const cciLine = cciChart.addLineSeries({
        color: "#0284c7",
        lineWidth: 2,
        priceLineVisible: false,
      });
      const upperLine = cciChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });
      const lowerLine = cciChart.addLineSeries({
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
      });

      cciLine.setData(toLineData(mapped, cciValues));
      upperLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: 100 }))
      );
      lowerLine.setData(
        mapped.map((item) => ({ time: item.time as Time, value: -100 }))
      );

      const cciValuesByTime = new Map<number, number>();
      cciValues.forEach((value, index) => {
        if (value == null || !Number.isFinite(value)) {
          return;
        }
        const ts = mapped[index]?.time;
        if (ts != null) {
          cciValuesByTime.set(ts, value);
        }
      });

      cciChartRef.current = cciChart;
      linkedCharts.push(cciChart);
      crosshairTargets.push({
        chart: cciChart,
        series: cciLine,
        valuesByTime: cciValuesByTime,
      });
    }

    if (visibility.atr && atrContainerRef.current) {
      const atrChart = createBaseChart(atrContainerRef.current, {
        isDaily,
        height: 120,
        textColor: "#475569",
      });
      const atrValues = atr(mapped, 14);
      const atrLine = atrChart.addLineSeries({
        color: "#d97706",
        lineWidth: 2,
        priceLineVisible: false,
      });

      atrLine.setData(toLineData(mapped, atrValues));

      const atrValuesByTime = new Map<number, number>();
      atrValues.forEach((value, index) => {
        if (value == null || !Number.isFinite(value)) {
          return;
        }
        const ts = mapped[index]?.time;
        if (ts != null) {
          atrValuesByTime.set(ts, value);
        }
      });

      atrChartRef.current = atrChart;
      linkedCharts.push(atrChart);
      crosshairTargets.push({
        chart: atrChart,
        series: atrLine,
        valuesByTime: atrValuesByTime,
      });
    }

    mainChart.timeScale().fitContent();
    if (rsiChartRef.current) {
      rsiChartRef.current.timeScale().fitContent();
    }
    if (macdChartRef.current) {
      macdChartRef.current.timeScale().fitContent();
    }
    if (kdjChartRef.current) {
      kdjChartRef.current.timeScale().fitContent();
    }
    if (wrChartRef.current) {
      wrChartRef.current.timeScale().fitContent();
    }
    if (cciChartRef.current) {
      cciChartRef.current.timeScale().fitContent();
    }
    if (atrChartRef.current) {
      atrChartRef.current.timeScale().fitContent();
    }

    const unbindSync = bindVisibleRangeSync(linkedCharts);
    const unbindCrosshair = bindCrosshairSync(crosshairTargets);

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
      if (rsiContainerRef.current && rsiChartRef.current) {
        rsiChartRef.current.applyOptions({ width: rsiContainerRef.current.clientWidth });
      }
      if (macdContainerRef.current && macdChartRef.current) {
        macdChartRef.current.applyOptions({
          width: macdContainerRef.current.clientWidth,
        });
      }
      if (kdjContainerRef.current && kdjChartRef.current) {
        kdjChartRef.current.applyOptions({
          width: kdjContainerRef.current.clientWidth,
        });
      }
      if (wrContainerRef.current && wrChartRef.current) {
        wrChartRef.current.applyOptions({
          width: wrContainerRef.current.clientWidth,
        });
      }
      if (cciContainerRef.current && cciChartRef.current) {
        cciChartRef.current.applyOptions({
          width: cciContainerRef.current.clientWidth,
        });
      }
      if (atrContainerRef.current && atrChartRef.current) {
        atrChartRef.current.applyOptions({
          width: atrContainerRef.current.clientWidth,
        });
      }
    });

    resizeObserver.observe(containerRef.current);
    if (rsiContainerRef.current) {
      resizeObserver.observe(rsiContainerRef.current);
    }
    if (macdContainerRef.current) {
      resizeObserver.observe(macdContainerRef.current);
    }
    if (kdjContainerRef.current) {
      resizeObserver.observe(kdjContainerRef.current);
    }
    if (wrContainerRef.current) {
      resizeObserver.observe(wrContainerRef.current);
    }
    if (cciContainerRef.current) {
      resizeObserver.observe(cciContainerRef.current);
    }
    if (atrContainerRef.current) {
      resizeObserver.observe(atrContainerRef.current);
    }

    return () => {
      unbindSync();
      unbindCrosshair();
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      if (rsiChartRef.current) {
        rsiChartRef.current.remove();
        rsiChartRef.current = null;
      }
      if (macdChartRef.current) {
        macdChartRef.current.remove();
        macdChartRef.current = null;
      }
      if (kdjChartRef.current) {
        kdjChartRef.current.remove();
        kdjChartRef.current = null;
      }
      if (wrChartRef.current) {
        wrChartRef.current.remove();
        wrChartRef.current = null;
      }
      if (cciChartRef.current) {
        cciChartRef.current.remove();
        cciChartRef.current = null;
      }
      if (atrChartRef.current) {
        atrChartRef.current.remove();
        atrChartRef.current = null;
      }
    };
  }, [data, visibility]);

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="w-full overflow-hidden rounded-md border" />
      {visibility.rsi && (
        <div className="space-y-1">
          <div className="px-1 text-[11px] text-muted-foreground">RSI(14)</div>
          <div
            ref={rsiContainerRef}
            className="w-full overflow-hidden rounded-md border"
          />
        </div>
      )}
      {visibility.macd && (
        <div className="space-y-1">
          <div className="px-1 text-[11px] text-muted-foreground">MACD(12,26,9)</div>
          <div
            ref={macdContainerRef}
            className="w-full overflow-hidden rounded-md border"
          />
        </div>
      )}
      {visibility.kdj && (
        <div className="space-y-1">
          <div className="px-1 text-[11px] text-muted-foreground">KDJ(9,3,3)</div>
          <div
            ref={kdjContainerRef}
            className="w-full overflow-hidden rounded-md border"
          />
        </div>
      )}
      {visibility.wr && (
        <div className="space-y-1">
          <div className="px-1 text-[11px] text-muted-foreground">WR(14)</div>
          <div
            ref={wrContainerRef}
            className="w-full overflow-hidden rounded-md border"
          />
        </div>
      )}
      {visibility.cci && (
        <div className="space-y-1">
          <div className="px-1 text-[11px] text-muted-foreground">CCI(20)</div>
          <div
            ref={cciContainerRef}
            className="w-full overflow-hidden rounded-md border"
          />
        </div>
      )}
      {visibility.atr && (
        <div className="space-y-1">
          <div className="px-1 text-[11px] text-muted-foreground">ATR(14)</div>
          <div
            ref={atrContainerRef}
            className="w-full overflow-hidden rounded-md border"
          />
        </div>
      )}
    </div>
  );
}
