import type { DashboardWatchlistMetric } from "@/api/client";

export type WatchlistSignalLevel = "strong" | "neutral" | "weak" | "unknown";
export type WatchlistVolumeLevel = "surge" | "normal" | "shrink" | "unknown";

export type WatchlistCardViewModel = {
  id: number;
  symbol: string;
  market: string;
  name: string;
  source: string;
  ts: string;
  price: number;
  change: number | null;
  changePercent: number | null;
  priceText: string;
  changeText: string;
  pctText: string;
  signalLevel: WatchlistSignalLevel;
  signalLabel: string;
  volumeLevel: WatchlistVolumeLevel;
  volumeLabel: string;
  supportText: string;
  resistanceText: string;
  recommendationTag: "持有" | "减仓" | "观察" | "待定";
  recommendationReason: string;
  unavailable: boolean;
};

function asFinite(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function median(values: number[]): number | null {
  if (!values.length) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[mid];
  }
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

function toPriceText(price: number, source: string): string {
  if (source === "unavailable") {
    return "--";
  }
  return price.toFixed(2);
}

function toChangeText(change: number | null | undefined, source: string): string {
  if (source === "unavailable") {
    return "--";
  }
  const v = asFinite(change);
  if (v == null) {
    return "--";
  }
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

function toPctText(changePercent: number | null | undefined, source: string): string {
  if (source === "unavailable") {
    return "--";
  }
  const v = asFinite(changePercent);
  if (v == null) {
    return "--";
  }
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export function deriveSignalLevel(changePercent: number | null | undefined): WatchlistSignalLevel {
  const value = asFinite(changePercent);
  if (value == null) {
    return "unknown";
  }
  if (value >= 2.0) {
    return "strong";
  }
  if (value >= 0.3) {
    return "neutral";
  }
  if (value > -0.3) {
    return "neutral";
  }
  if (value > -2.0) {
    return "weak";
  }
  return "weak";
}

export function deriveVolumeLevel(
  volume: number | null | undefined,
  medianVolume: number | null | undefined
): WatchlistVolumeLevel {
  const v = asFinite(volume);
  const m = asFinite(medianVolume);
  if (v == null || m == null || m <= 0) {
    return "unknown";
  }
  if (v >= m * 1.5) {
    return "surge";
  }
  if (v <= m * 0.7) {
    return "shrink";
  }
  return "normal";
}

export function buildRecommendation(
  level: WatchlistSignalLevel,
  volumeLevel: WatchlistVolumeLevel,
  source: string
): { tag: "持有" | "减仓" | "观察" | "待定"; reason: string } {
  if (source === "unavailable") {
    return {
      tag: "待定",
      reason: "行情暂不可用，建议等待下一个刷新周期确认后再决策。",
    };
  }

  if (level === "strong") {
    if (volumeLevel === "surge") {
      return {
        tag: "持有",
        reason: "趋势偏强且量能放大，短线动能仍在，优先持有观察延续性。",
      };
    }
    return {
      tag: "持有",
      reason: "趋势偏强，量能未见明显衰减，可继续持有并跟踪回撤强度。",
    };
  }

  if (level === "weak") {
    if (volumeLevel === "surge") {
      return {
        tag: "减仓",
        reason: "走弱且量能放大，抛压可能集中释放，建议降低仓位控制回撤。",
      };
    }
    return {
      tag: "减仓",
      reason: "价格动能偏弱，建议先降风险敞口并等待信号修复。",
    };
  }

  if (level === "neutral") {
    if (volumeLevel === "surge") {
      return {
        tag: "观察",
        reason: "震荡区间内量能变化明显，建议观察是否形成方向突破。",
      };
    }
    return {
      tag: "观察",
      reason: "趋势中性，建议维持观察，等待更清晰的方向信号。",
    };
  }

  return {
    tag: "待定",
    reason: "信号不足，暂不形成明确建议。",
  };
}

export function formatSupportResistance(
  price: number,
  changePercent: number | null | undefined
): { supportText: string; resistanceText: string } {
  if (!Number.isFinite(price) || price <= 0) {
    return { supportText: "估算 --", resistanceText: "估算 --" };
  }
  const pct = Math.abs(asFinite(changePercent) ?? 0);
  const k = Math.max(0.008, Math.min(0.03, pct / 100));
  const support = price * (1 - k);
  const resistance = price * (1 + k * 1.2);
  return {
    supportText: `估算 ${support.toFixed(2)}`,
    resistanceText: `估算 ${resistance.toFixed(2)}`,
  };
}

export function buildWatchlistCards(rows: DashboardWatchlistMetric[]): WatchlistCardViewModel[] {
  const volumes = rows
    .map((row) => asFinite(row.volume))
    .filter((value): value is number => value != null && value > 0);
  const medianVolume = median(volumes);

  return rows.map((row) => {
    const signalLevel = deriveSignalLevel(row.change_percent);
    const volumeLevel = deriveVolumeLevel(row.volume, medianVolume);
    const recommendation = buildRecommendation(signalLevel, volumeLevel, row.source);
    const sr = formatSupportResistance(row.price, row.change_percent);

    const signalLabel =
      signalLevel === "strong"
        ? "趋势偏强"
        : signalLevel === "weak"
          ? "趋势偏弱"
          : signalLevel === "neutral"
            ? "震荡观察"
            : "信号不足";

    const volumeLabel =
      volumeLevel === "surge"
        ? "量能放大"
        : volumeLevel === "shrink"
          ? "量能收缩"
          : volumeLevel === "normal"
            ? "量能正常"
            : "量能未知";

    return {
      id: row.id,
      symbol: row.symbol,
      market: row.market,
      name: row.display_name || row.alias || row.symbol,
      source: row.source,
      ts: row.ts,
      price: row.price,
      change: asFinite(row.change),
      changePercent: asFinite(row.change_percent),
      priceText: toPriceText(row.price, row.source),
      changeText: toChangeText(row.change, row.source),
      pctText: toPctText(row.change_percent, row.source),
      signalLevel,
      signalLabel,
      volumeLevel,
      volumeLabel,
      supportText: sr.supportText,
      resistanceText: sr.resistanceText,
      recommendationTag: recommendation.tag,
      recommendationReason: recommendation.reason,
      unavailable: row.source === "unavailable",
    };
  });
}
