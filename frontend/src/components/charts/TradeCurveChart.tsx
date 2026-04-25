import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type SeriesType,
  type Time,
} from "lightweight-charts";

import type { CurvePoint } from "@/api/client";
import { macd as macdIndicator } from "@/lib/technicalIndicators";

type Props = {
  data: CurvePoint[];
};

const MARKET_TZ_OFFSET: Record<string, string> = {
  CN: "+08:00",
  HK: "+08:00",
};

const ET_FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function hasExplicitTimezone(value: string): boolean {
  return /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(value);
}

function formatMmDdHhMm(dt: Date): string {
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  const hh = String(dt.getHours()).padStart(2, "0");
  const min = String(dt.getMinutes()).padStart(2, "0");
  return `${mm}-${dd} ${hh}:${min}`;
}

function formatEtMmDdHhMm(dt: Date): string {
  const parts = ET_FORMATTER.formatToParts(dt);
  const partMap = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const mm = partMap.month ?? "00";
  const dd = partMap.day ?? "00";
  const hh = partMap.hour ?? "00";
  const min = partMap.minute ?? "00";
  return `${mm}-${dd} ${hh}:${min}`;
}

function normalizeDateTime(raw: string): string {
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return `${normalized}T00:00:00`;
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(normalized)) {
    return `${normalized}:00`;
  }
  return normalized;
}

function parseEpochSeconds(rawTs: string, market: string): number | null {
  const raw = String(rawTs || "").trim();
  if (!raw) {
    return null;
  }

  const normalized = normalizeDateTime(raw);
  const marketCode = String(market || "").trim().toUpperCase();
  const parseCandidates: string[] = [];

  if (hasExplicitTimezone(normalized)) {
    parseCandidates.push(normalized);
  } else {
    const offset = MARKET_TZ_OFFSET[marketCode];
    if (offset) {
      parseCandidates.push(`${normalized}${offset}`);
    }
    parseCandidates.push(normalized);
  }

  for (const candidate of parseCandidates) {
    const parsed = Date.parse(candidate);
    if (!Number.isNaN(parsed)) {
      return Math.floor(parsed / 1000);
    }
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

type CurveChartPoint = {
  time: number;
  value: number;
  volume: number | null;
};

function normalizeCurve(data: CurvePoint[]): CurveChartPoint[] {
  const rows = data
    .map((item) => {
      const parsed = parseEpochSeconds(item.ts, item.market);
      if (parsed == null || !Number.isFinite(parsed)) {
        return null;
      }
      return {
        time: parsed,
        value: item.price,
        volume: item.volume ?? null,
      };
    })
    .filter((item): item is CurveChartPoint => Boolean(item))
    .sort((a, b) => a.time - b.time);

  const deduped: CurveChartPoint[] = [];
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

function createBaseChart(
  container: HTMLDivElement,
  options: {
    height: number;
    textColor: string;
    showEt: boolean;
  }
) {
  const { height, textColor, showEt } = options;
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
        const localText = formatMmDdHhMm(dt);
        if (!showEt) {
          return localText;
        }
        return `${localText} / ET ${formatEtMmDdHhMm(dt)}`;
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
          if (target !== source) {
            target.timeScale().setVisibleRange(range);
          }
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

export function TradeCurveChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const volumeContainerRef = useRef<HTMLDivElement | null>(null);
  const macdContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const volumeChartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);
  const market = String(data[0]?.market || "").trim().toUpperCase();
  const showEt = market === "US";

  useEffect(() => {
    if (!containerRef.current || !volumeContainerRef.current || !macdContainerRef.current) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }
    if (volumeChartRef.current) {
      volumeChartRef.current.remove();
      volumeChartRef.current = null;
    }
    if (macdChartRef.current) {
      macdChartRef.current.remove();
      macdChartRef.current = null;
    }

    const chart = createBaseChart(containerRef.current, {
      height: 230,
      textColor: "#1f2937",
      showEt,
    });
    const volumeChart = createBaseChart(volumeContainerRef.current, {
      height: 110,
      textColor: "#475569",
      showEt,
    });
    const macdChart = createBaseChart(macdContainerRef.current, {
      height: 140,
      textColor: "#475569",
      showEt,
    });

    const series = chart.addLineSeries({
      color: "#0d9488",
      lineWidth: 2,
      priceLineVisible: false,
    });
    const volumeSeries = volumeChart.addHistogramSeries({
      priceLineVisible: false,
      base: 0,
    });
    const macdHistSeries = macdChart.addHistogramSeries({
      priceLineVisible: false,
      base: 0,
    });
    const difSeries = macdChart.addLineSeries({
      color: "#dc2626",
      lineWidth: 1,
      priceLineVisible: false,
    });
    const deaSeries = macdChart.addLineSeries({
      color: "#2563eb",
      lineWidth: 1,
      priceLineVisible: false,
    });

    const mapped = normalizeCurve(data);
    const prices = mapped.map((item) => item.value);
    const macdValues = macdIndicator(prices);
    const priceValuesByTime = new Map<number, number>(
      mapped.map((item) => [item.time, item.value])
    );
    const volumeValuesByTime = new Map<number, number>();
    const macdValuesByTime = new Map<number, number>();

    series.setData(mapped.map((item) => ({ time: item.time as Time, value: item.value })));
    volumeSeries.setData(
      mapped.flatMap((item, index) => {
        if (item.volume == null || !Number.isFinite(item.volume)) {
          return [];
        }
        volumeValuesByTime.set(item.time, item.volume);
        const previous = mapped[index - 1]?.value ?? item.value;
        return [
          {
            time: item.time as Time,
            value: item.volume,
            color: item.value >= previous ? "#16a34a" : "#ef4444",
          },
        ];
      })
    );
    macdHistSeries.setData(
      mapped.flatMap((item, index) => {
        const value = macdValues.hist[index];
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
    difSeries.setData(
      mapped.flatMap((item, index) => {
        const value = macdValues.dif[index];
        if (value == null || !Number.isFinite(value)) {
          return [];
        }
        macdValuesByTime.set(item.time, value);
        return [{ time: item.time as Time, value }];
      })
    );
    deaSeries.setData(
      mapped.flatMap((item, index) => {
        const value = macdValues.dea[index];
        if (value == null || !Number.isFinite(value)) {
          return [];
        }
        return [{ time: item.time as Time, value }];
      })
    );

    chart.timeScale().fitContent();
    volumeChart.timeScale().fitContent();
    macdChart.timeScale().fitContent();

    chartRef.current = chart;
    volumeChartRef.current = volumeChart;
    macdChartRef.current = macdChart;

    const unbindSync = bindVisibleRangeSync([chart, volumeChart, macdChart]);
    const unbindCrosshair = bindCrosshairSync([
      { chart, series, valuesByTime: priceValuesByTime },
      { chart: volumeChart, series: volumeSeries, valuesByTime: volumeValuesByTime },
      { chart: macdChart, series: difSeries, valuesByTime: macdValuesByTime },
    ]);

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
      if (volumeContainerRef.current && volumeChartRef.current) {
        volumeChartRef.current.applyOptions({
          width: volumeContainerRef.current.clientWidth,
        });
      }
      if (macdContainerRef.current && macdChartRef.current) {
        macdChartRef.current.applyOptions({
          width: macdContainerRef.current.clientWidth,
        });
      }
    });
    resizeObserver.observe(containerRef.current);
    resizeObserver.observe(volumeContainerRef.current);
    resizeObserver.observe(macdContainerRef.current);

    return () => {
      unbindSync();
      unbindCrosshair();
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      if (volumeChartRef.current) {
        volumeChartRef.current.remove();
        volumeChartRef.current = null;
      }
      if (macdChartRef.current) {
        macdChartRef.current.remove();
        macdChartRef.current = null;
      }
    };
  }, [data, showEt]);

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="w-full overflow-hidden rounded-md border" />
      <div className="space-y-1">
        <div className="px-1 text-[11px] text-muted-foreground">成交量</div>
        <div ref={volumeContainerRef} className="w-full overflow-hidden rounded-md border" />
      </div>
      <div className="space-y-1">
        <div className="px-1 text-[11px] text-muted-foreground">MACD(12,26,9)</div>
        <div ref={macdContainerRef} className="w-full overflow-hidden rounded-md border" />
      </div>
    </div>
  );
}
