import type { Bar, IndicatorSeries } from "../api/client";

/** Points for one chart line; `value` undefined means a gap (lightweight-charts whitespace). */
export interface LinePoint {
  time: string;
  value?: number;
}

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartData {
  candles: Candle[];
  volume: { time: string; value: number; up: boolean }[];
  lines: Record<string, LinePoint[]>;
}

/** Daily bars come as "2026-10-09"; anything longer is cut to the date. */
const day = (t: string) => t.slice(0, 10);

/** Candles from bars, skipping bars without a full OHLC (Yahoo sometimes sends close only). */
export function buildChartData(bars: Bar[], ind: IndicatorSeries | undefined): ChartData {
  const candles: Candle[] = [];
  const volume: ChartData["volume"] = [];
  const seen = new Set<string>();
  for (const b of bars) {
    const time = day(b.t);
    if (seen.has(time)) continue;
    seen.add(time);
    const open = b.open ?? b.close;
    const high = b.high ?? Math.max(open, b.close);
    const low = b.low ?? Math.min(open, b.close);
    candles.push({ time, open, high, low, close: b.close });
    if (b.volume != null) volume.push({ time, value: b.volume, up: b.close >= open });
  }
  const lines: Record<string, LinePoint[]> = {};
  if (ind) {
    const times = ind.t.map(day);
    for (const [name, vals] of Object.entries(ind.columns)) {
      lines[name] = times.map((time, i) => {
        const v = vals[i];
        return v == null ? { time } : { time, value: v };
      });
    }
    // Supertrend as two lines so each side can have its own colour (and legend text).
    const st = ind.columns.supertrend;
    const dir = ind.columns.supertrend_dir;
    if (st && dir) {
      lines.supertrend_up = times.map((time, i) => (dir[i] === 1 && st[i] != null ? { time, value: st[i]! } : { time }));
      lines.supertrend_down = times.map((time, i) => (dir[i] === -1 && st[i] != null ? { time, value: st[i]! } : { time }));
    }
  }
  return { candles, volume, lines };
}

/** Moving-average columns present in the series, e.g. ["sma20", "sma50", "sma200", "ema9"]. */
export function movingAverages(ind: IndicatorSeries | undefined): string[] {
  if (!ind) return [];
  const keys = Object.keys(ind.columns).filter((k) => /^(sma|ema)\d+$/.test(k));
  return keys.sort((a, b) => (a.slice(0, 3) === b.slice(0, 3) ? Number(a.slice(3)) - Number(b.slice(3)) : a < b ? 1 : -1));
}

export function rsiColumn(ind: IndicatorSeries | undefined): string | null {
  return ind ? (Object.keys(ind.columns).find((k) => /^rsi\d+$/.test(k)) ?? null) : null;
}

/** ISO date `months` before today, for the range selector. */
export function startFor(months: number, today = new Date()): string {
  const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - months, today.getUTCDate()));
  return d.toISOString().slice(0, 10);
}

/** The `n` nearest support levels below and resistance levels above the close: more is clutter. */
export function nearestLevels<T extends { price: number; kind: "support" | "resistance" }>(levels: T[], close: number, n = 2): T[] {
  const by = (kind: T["kind"], side: (p: number) => boolean) =>
    levels
      .filter((l) => l.kind === kind && side(l.price))
      .sort((a, b) => Math.abs(a.price - close) - Math.abs(b.price - close))
      .slice(0, n);
  return [...by("support", (p) => p <= close), ...by("resistance", (p) => p >= close)];
}
