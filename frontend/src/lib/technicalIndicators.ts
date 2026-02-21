import type { KLineBar } from "@/api/client";

export type CandlePoint = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};

export function parseEpochSeconds(rawTs: string): number | null {
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

export function normalizeCandles(data: KLineBar[]): CandlePoint[] {
  const rows = data
    .map((item) => {
      const parsed = parseEpochSeconds(item.ts);
      if (parsed == null || !Number.isFinite(parsed)) {
        return null;
      }
      return {
        time: parsed,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
        volume: item.volume ?? null,
      };
    })
    .filter((item): item is CandlePoint => Boolean(item))
    .sort((a, b) => a.time - b.time);

  const deduped: CandlePoint[] = [];
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

export function sma(values: number[], period: number): Array<number | null> {
  const output: Array<number | null> = Array(values.length).fill(null);
  if (period <= 0 || values.length < period) {
    return output;
  }
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) {
      sum -= values[i - period];
    }
    if (i >= period - 1) {
      output[i] = sum / period;
    }
  }
  return output;
}

export function ema(values: number[], period: number): Array<number | null> {
  const output: Array<number | null> = Array(values.length).fill(null);
  if (period <= 0 || values.length < period) {
    return output;
  }

  let seed = 0;
  for (let i = 0; i < period; i++) {
    seed += values[i];
  }
  let prev = seed / period;
  output[period - 1] = prev;
  const multiplier = 2 / (period + 1);
  for (let i = period; i < values.length; i++) {
    prev = (values[i] - prev) * multiplier + prev;
    output[i] = prev;
  }
  return output;
}

function stddevWindow(values: number[], endIndex: number, period: number): number {
  const start = endIndex - period + 1;
  const segment = values.slice(start, endIndex + 1);
  const mean = segment.reduce((acc, item) => acc + item, 0) / segment.length;
  const variance = segment.reduce((acc, item) => acc + (item - mean) ** 2, 0) / segment.length;
  return Math.sqrt(variance);
}

export function bollinger(
  values: number[],
  period = 20,
  multiplier = 2
): {
  mid: Array<number | null>;
  upper: Array<number | null>;
  lower: Array<number | null>;
} {
  const mid = sma(values, period);
  const upper: Array<number | null> = Array(values.length).fill(null);
  const lower: Array<number | null> = Array(values.length).fill(null);
  for (let i = period - 1; i < values.length; i++) {
    const m = mid[i];
    if (m == null) {
      continue;
    }
    const sd = stddevWindow(values, i, period);
    upper[i] = m + multiplier * sd;
    lower[i] = m - multiplier * sd;
  }
  return { mid, upper, lower };
}

export function bbiboll(
  values: number[],
  period = 10,
  multiplier = 3
): {
  bbi: Array<number | null>;
  upper: Array<number | null>;
  lower: Array<number | null>;
} {
  const ma3 = sma(values, 3);
  const ma6 = sma(values, 6);
  const ma12 = sma(values, 12);
  const ma24 = sma(values, 24);

  const bbi: Array<number | null> = values.map((_, index) => {
    const a = ma3[index];
    const b = ma6[index];
    const c = ma12[index];
    const d = ma24[index];
    if (a == null || b == null || c == null || d == null) {
      return null;
    }
    return (a + b + c + d) / 4;
  });

  const upper: Array<number | null> = Array(values.length).fill(null);
  const lower: Array<number | null> = Array(values.length).fill(null);
  for (let i = 0; i < values.length; i++) {
    const mid = bbi[i];
    if (mid == null) {
      continue;
    }
    const start = i - period + 1;
    if (start < 0) {
      continue;
    }
    const segment: number[] = [];
    let valid = true;
    for (let j = start; j <= i; j++) {
      const value = bbi[j];
      if (value == null || !Number.isFinite(value)) {
        valid = false;
        break;
      }
      segment.push(value);
    }
    if (!valid || segment.length < period) {
      continue;
    }
    const mean = segment.reduce((sum, item) => sum + item, 0) / segment.length;
    const variance =
      segment.reduce((sum, item) => sum + (item - mean) ** 2, 0) /
      segment.length;
    const sd = Math.sqrt(variance);
    upper[i] = mid + multiplier * sd;
    lower[i] = mid - multiplier * sd;
  }

  return { bbi, upper, lower };
}

export function rsi(values: number[], period = 14): Array<number | null> {
  const output: Array<number | null> = Array(values.length).fill(null);
  if (period <= 0 || values.length <= period) {
    return output;
  }

  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = values[i] - values[i - 1];
    if (diff >= 0) {
      gain += diff;
    } else {
      loss += -diff;
    }
  }

  let avgGain = gain / period;
  let avgLoss = loss / period;
  output[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);

  for (let i = period + 1; i < values.length; i++) {
    const diff = values[i] - values[i - 1];
    const nextGain = diff > 0 ? diff : 0;
    const nextLoss = diff < 0 ? -diff : 0;
    avgGain = (avgGain * (period - 1) + nextGain) / period;
    avgLoss = (avgLoss * (period - 1) + nextLoss) / period;
    output[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return output;
}

function emaNullable(values: Array<number | null>, period: number): Array<number | null> {
  const output: Array<number | null> = Array(values.length).fill(null);
  if (period <= 0) {
    return output;
  }
  const first = values.findIndex((item) => item != null && Number.isFinite(item));
  if (first < 0 || values.length - first < period) {
    return output;
  }

  let seed = 0;
  for (let i = first; i < first + period; i++) {
    seed += Number(values[i]);
  }
  let prev = seed / period;
  output[first + period - 1] = prev;
  const multiplier = 2 / (period + 1);
  for (let i = first + period; i < values.length; i++) {
    const value = values[i];
    if (value == null || !Number.isFinite(value)) {
      continue;
    }
    prev = (Number(value) - prev) * multiplier + prev;
    output[i] = prev;
  }
  return output;
}

export function macd(values: number[]): {
  dif: Array<number | null>;
  dea: Array<number | null>;
  hist: Array<number | null>;
} {
  const fast = ema(values, 12);
  const slow = ema(values, 26);
  const dif: Array<number | null> = values.map((_, index) => {
    const f = fast[index];
    const s = slow[index];
    if (f == null || s == null) {
      return null;
    }
    return f - s;
  });
  const dea = emaNullable(dif, 9);
  const hist: Array<number | null> = dif.map((value, index) => {
    const signal = dea[index];
    if (value == null || signal == null) {
      return null;
    }
    return value - signal;
  });
  return { dif, dea, hist };
}

export function kdj(
  candles: CandlePoint[],
  period = 9
): {
  k: Array<number | null>;
  d: Array<number | null>;
  j: Array<number | null>;
} {
  const outputK: Array<number | null> = Array(candles.length).fill(null);
  const outputD: Array<number | null> = Array(candles.length).fill(null);
  const outputJ: Array<number | null> = Array(candles.length).fill(null);
  if (period <= 0 || candles.length < period) {
    return { k: outputK, d: outputD, j: outputJ };
  }

  let prevK = 50;
  let prevD = 50;
  for (let i = period - 1; i < candles.length; i++) {
    let highN = Number.NEGATIVE_INFINITY;
    let lowN = Number.POSITIVE_INFINITY;
    for (let j = i - period + 1; j <= i; j++) {
      highN = Math.max(highN, candles[j].high);
      lowN = Math.min(lowN, candles[j].low);
    }

    const close = candles[i].close;
    const rsv = highN === lowN ? 50 : ((close - lowN) / (highN - lowN)) * 100;
    const nextK = (2 * prevK + rsv) / 3;
    const nextD = (2 * prevD + nextK) / 3;
    const nextJ = 3 * nextK - 2 * nextD;

    outputK[i] = nextK;
    outputD[i] = nextD;
    outputJ[i] = nextJ;

    prevK = nextK;
    prevD = nextD;
  }

  return { k: outputK, d: outputD, j: outputJ };
}

export function williamsR(
  candles: CandlePoint[],
  period = 14
): Array<number | null> {
  const output: Array<number | null> = Array(candles.length).fill(null);
  if (period <= 0 || candles.length < period) {
    return output;
  }

  for (let i = period - 1; i < candles.length; i++) {
    let highest = Number.NEGATIVE_INFINITY;
    let lowest = Number.POSITIVE_INFINITY;
    for (let j = i - period + 1; j <= i; j++) {
      highest = Math.max(highest, candles[j].high);
      lowest = Math.min(lowest, candles[j].low);
    }
    const span = highest - lowest;
    if (span === 0) {
      output[i] = -50;
      continue;
    }
    output[i] = ((highest - candles[i].close) / span) * -100;
  }
  return output;
}

export function cci(
  candles: CandlePoint[],
  period = 20
): Array<number | null> {
  const output: Array<number | null> = Array(candles.length).fill(null);
  if (period <= 0 || candles.length < period) {
    return output;
  }

  const tp = candles.map((item) => (item.high + item.low + item.close) / 3);
  const tpSma = sma(tp, period);
  for (let i = period - 1; i < candles.length; i++) {
    const ma = tpSma[i];
    if (ma == null) {
      continue;
    }
    let md = 0;
    for (let j = i - period + 1; j <= i; j++) {
      md += Math.abs(tp[j] - ma);
    }
    md /= period;
    if (md === 0) {
      output[i] = 0;
      continue;
    }
    output[i] = (tp[i] - ma) / (0.015 * md);
  }
  return output;
}

export function atr(
  candles: CandlePoint[],
  period = 14
): Array<number | null> {
  const output: Array<number | null> = Array(candles.length).fill(null);
  if (period <= 0 || candles.length < period) {
    return output;
  }

  const tr: number[] = Array(candles.length).fill(0);
  for (let i = 0; i < candles.length; i++) {
    const current = candles[i];
    if (i === 0) {
      tr[i] = current.high - current.low;
      continue;
    }
    const prevClose = candles[i - 1].close;
    tr[i] = Math.max(
      current.high - current.low,
      Math.abs(current.high - prevClose),
      Math.abs(current.low - prevClose)
    );
  }

  let seed = 0;
  for (let i = 0; i < period; i++) {
    seed += tr[i];
  }
  let prevAtr = seed / period;
  output[period - 1] = prevAtr;
  for (let i = period; i < candles.length; i++) {
    prevAtr = (prevAtr * (period - 1) + tr[i]) / period;
    output[i] = prevAtr;
  }
  return output;
}

export function latestValue(values: Array<number | null>): number | null {
  for (let index = values.length - 1; index >= 0; index--) {
    const value = values[index];
    if (value != null && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}
