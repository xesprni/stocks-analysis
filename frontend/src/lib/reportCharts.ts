import type { EChartsOption } from "echarts";

import type { ReportDetail, ReportSummary } from "@/api/client";

type JsonRecord = Record<string, unknown>;

type ThemePalette = {
  text: string;
  gridLine: string;
  axisLine: string;
  splitLine: string;
  card: string;
  accentA: string;
  accentB: string;
  accentC: string;
  up: string;
  down: string;
};

type PricePoint = {
  ts: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
};

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" ? (value as JsonRecord) : {};
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function toTheme(isDark: boolean): ThemePalette {
  if (isDark) {
    return {
      text: "#d4d4d8",
      gridLine: "rgba(161, 161, 170, 0.22)",
      axisLine: "rgba(161, 161, 170, 0.45)",
      splitLine: "rgba(161, 161, 170, 0.18)",
      card: "#18181b",
      accentA: "#22d3ee",
      accentB: "#a78bfa",
      accentC: "#34d399",
      up: "#22c55e",
      down: "#ef4444",
    };
  }
  return {
    text: "#3f3f46",
    gridLine: "rgba(63, 63, 70, 0.12)",
    axisLine: "rgba(63, 63, 70, 0.32)",
    splitLine: "rgba(63, 63, 70, 0.12)",
    card: "#ffffff",
    accentA: "#0284c7",
    accentB: "#7c3aed",
    accentC: "#059669",
    up: "#16a34a",
    down: "#dc2626",
  };
}

function toLabel(ts: string): string {
  const parsed = new Date(ts);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString(undefined, { month: "2-digit", day: "2-digit" });
  }
  return ts;
}

function toTooltipTime(ts: string): string {
  const parsed = new Date(ts);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleString();
  }
  return ts;
}

function parsePricePoints(toolResults: JsonRecord): PricePoint[] {
  const pricePayload = asRecord(toolResults.get_price_history);
  const bars = asArray<JsonRecord>(pricePayload.bars)
    .map((row) => {
      const ts = String(row.ts ?? "").trim();
      const close = toFiniteNumber(row.close);
      if (!ts || close == null) {
        return null;
      }
      return {
        ts,
        open: toFiniteNumber(row.open),
        high: toFiniteNumber(row.high),
        low: toFiniteNumber(row.low),
        close,
      };
    })
    .filter((row): row is PricePoint => row !== null)
    .sort((a, b) => {
      const t1 = new Date(a.ts).getTime();
      const t2 = new Date(b.ts).getTime();
      if (Number.isNaN(t1) || Number.isNaN(t2)) {
        return a.ts.localeCompare(b.ts);
      }
      return t1 - t2;
    });
  return bars;
}

function getToolResults(detail: ReportDetail): JsonRecord {
  const analysis = asRecord(detail.raw_data.analysis);
  const agent = asRecord(analysis.agent);
  const analysisInput = asRecord(agent.analysis_input);
  const direct = asRecord(analysisInput.tool_results);
  if (Object.keys(direct).length > 0) {
    return direct;
  }
  const fallbackRaw = asRecord(analysis.raw);
  return asRecord(fallbackRaw.tool_results);
}

export function buildReportPriceChartOption(detail: ReportDetail, isDark: boolean): EChartsOption | null {
  const toolResults = getToolResults(detail);
  const points = parsePricePoints(toolResults);
  if (!points.length) {
    return null;
  }

  const palette = toTheme(isDark);
  const labels = points.map((item) => toLabel(item.ts));
  const canUseCandles = points.every(
    (item) => item.open != null && item.high != null && item.low != null
  );

  if (canUseCandles) {
    return {
      backgroundColor: "transparent",
      grid: { left: 12, right: 16, top: 40, bottom: 24, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        formatter: (params: unknown) => {
          const rows = asArray<JsonRecord>(params);
          if (!rows.length) {
            return "";
          }
          const row = rows[0];
          const idx = Number(row.dataIndex ?? 0);
          const point = points[idx];
          if (!point) {
            return "";
          }
          return [
            toTooltipTime(point.ts),
            `Open: ${point.open?.toFixed(2) ?? "N/A"}`,
            `High: ${point.high?.toFixed(2) ?? "N/A"}`,
            `Low: ${point.low?.toFixed(2) ?? "N/A"}`,
            `Close: ${point.close.toFixed(2)}`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: true,
        axisLine: { lineStyle: { color: palette.axisLine } },
        axisLabel: { color: palette.text },
      },
      yAxis: {
        scale: true,
        axisLine: { lineStyle: { color: palette.axisLine } },
        axisLabel: { color: palette.text },
        splitLine: { lineStyle: { color: palette.splitLine } },
      },
      series: [
        {
          name: "Price",
          type: "candlestick",
          data: points.map((item) => [item.open, item.close, item.low, item.high]),
          itemStyle: {
            color: palette.up,
            color0: palette.down,
            borderColor: palette.up,
            borderColor0: palette.down,
          },
        },
      ],
    };
  }

  return {
    backgroundColor: "transparent",
    grid: { left: 12, right: 16, top: 40, bottom: 24, containLabel: true },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const rows = asArray<JsonRecord>(params);
        if (!rows.length) {
          return "";
        }
        const idx = Number(rows[0].dataIndex ?? 0);
        const point = points[idx];
        if (!point) {
          return "";
        }
        return `${toTooltipTime(point.ts)}<br/>Close: ${point.close.toFixed(2)}`;
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisLabel: { color: palette.text },
    },
    yAxis: {
      type: "value",
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisLabel: { color: palette.text },
      splitLine: { lineStyle: { color: palette.splitLine } },
    },
    series: [
      {
        name: "Close",
        type: "line",
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color: palette.accentA },
        areaStyle: { color: "rgba(14, 165, 233, 0.15)" },
        data: points.map((item) => item.close),
      },
    ],
  };
}

export function buildReportIndicatorChartOption(detail: ReportDetail, isDark: boolean): EChartsOption | null {
  const toolResults = getToolResults(detail);
  const values = asRecord(asRecord(toolResults.compute_indicators).values);
  const rows = Object.entries(values)
    .map(([name, value]) => ({ name, value: toFiniteNumber(value) }))
    .filter((row): row is { name: string; value: number } => row.value != null)
    .slice(0, 24);

  if (!rows.length) {
    return null;
  }

  const palette = toTheme(isDark);

  return {
    backgroundColor: "transparent",
    grid: { left: 12, right: 16, top: 36, bottom: 40, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: {
      type: "category",
      data: rows.map((row) => row.name),
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisLabel: { color: palette.text, rotate: 35 },
    },
    yAxis: {
      type: "value",
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisLabel: { color: palette.text },
      splitLine: { lineStyle: { color: palette.splitLine } },
    },
    series: [
      {
        name: "Indicator",
        type: "bar",
        data: rows.map((row) => row.value),
        itemStyle: { color: palette.accentB, borderRadius: [4, 4, 0, 0] },
      },
    ],
  };
}

export function buildReportNewsChartOption(detail: ReportDetail, isDark: boolean): EChartsOption | null {
  const toolResults = getToolResults(detail);
  const items = asArray<JsonRecord>(asRecord(toolResults.search_news).items);
  if (!items.length) {
    return null;
  }

  const mediaCounter = new Map<string, number>();
  for (const row of items) {
    const media = String(row.media ?? "Unknown").trim() || "Unknown";
    mediaCounter.set(media, (mediaCounter.get(media) ?? 0) + 1);
  }

  const sorted = Array.from(mediaCounter.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, value]) => ({ name, value }));

  if (!sorted.length) {
    return null;
  }

  const palette = toTheme(isDark);

  return {
    backgroundColor: "transparent",
    tooltip: { trigger: "item" },
    legend: {
      bottom: 0,
      textStyle: { color: palette.text, fontSize: 11 },
      type: "scroll",
    },
    graphic: [
      {
        type: "text",
        right: 16,
        top: 6,
        style: {
          text: `Total ${items.length}`,
          fill: palette.text,
          fontSize: 12,
          fontWeight: 600,
        },
      },
    ],
    series: [
      {
        type: "pie",
        radius: ["38%", "68%"],
        center: ["50%", "44%"],
        itemStyle: {
          borderRadius: 8,
          borderColor: palette.card,
          borderWidth: 2,
        },
        label: { color: palette.text, formatter: "{b}: {d}%" },
        data: sorted,
      },
    ],
  };
}

export function buildReportHistoryChartOption(
  reports: ReportSummary[],
  isDark: boolean
): EChartsOption | null {
  if (!reports.length) {
    return null;
  }

  const sorted = [...reports]
    .sort((a, b) => {
      const t1 = new Date(a.generated_at).getTime();
      const t2 = new Date(b.generated_at).getTime();
      if (Number.isNaN(t1) || Number.isNaN(t2)) {
        return a.run_id.localeCompare(b.run_id);
      }
      return t1 - t2;
    })
    .slice(-100);

  if (!sorted.length) {
    return null;
  }

  const palette = toTheme(isDark);

  return {
    backgroundColor: "transparent",
    grid: { left: 12, right: 16, top: 36, bottom: 24, containLabel: true },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const rows = asArray<JsonRecord>(params);
        if (!rows.length) {
          return "";
        }
        const idx = Number(rows[0].dataIndex ?? 0);
        const row = sorted[idx];
        if (!row) {
          return "";
        }
        const confidence = toFiniteNumber(row.confidence);
        return [
          toTooltipTime(row.generated_at),
          `confidence: ${confidence == null ? "N/A" : confidence.toFixed(2)}`,
          `warnings: ${row.warnings_count}`,
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: sorted.map((item) => toLabel(item.generated_at)),
      axisLine: { lineStyle: { color: palette.axisLine } },
      axisLabel: { color: palette.text },
    },
    yAxis: [
      {
        type: "value",
        min: 0,
        max: 1,
        name: "confidence",
        nameTextStyle: { color: palette.text },
        axisLine: { lineStyle: { color: palette.axisLine } },
        axisLabel: { color: palette.text },
        splitLine: { lineStyle: { color: palette.splitLine } },
      },
      {
        type: "value",
        minInterval: 1,
        name: "warnings",
        nameTextStyle: { color: palette.text },
        axisLine: { lineStyle: { color: palette.axisLine } },
        axisLabel: { color: palette.text },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "confidence",
        type: "line",
        yAxisIndex: 0,
        connectNulls: false,
        smooth: 0.25,
        symbolSize: 6,
        lineStyle: { width: 2, color: palette.accentA },
        itemStyle: { color: palette.accentA },
        data: sorted.map((row) => toFiniteNumber(row.confidence)),
      },
      {
        name: "warnings",
        type: "bar",
        yAxisIndex: 1,
        itemStyle: { color: palette.accentC, borderRadius: [4, 4, 0, 0] },
        data: sorted.map((row) => row.warnings_count),
      },
    ],
  };
}
