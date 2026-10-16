/**
 * Which points of a long line to draw: an even spread of at most `max`, plus the first and
 * last, and each series' highest and lowest (so a peak or the deepest fall stays exact).
 * Drawing only: captions and tables keep using every point.
 */
export function thinIndices(length: number, series: (number | null)[][], max = 300): number[] {
  if (length <= max) return Array.from({ length }, (_, i) => i);
  const keep = new Set<number>([0, length - 1]);
  const step = (length - 1) / (max - 1);
  for (let k = 0; k < max; k++) keep.add(Math.round(k * step));
  for (const values of series) {
    let hi = -1;
    let lo = -1;
    for (let i = 0; i < length; i++) {
      const v = values[i];
      if (v == null) continue;
      if (hi < 0 || v > values[hi]!) hi = i;
      if (lo < 0 || v < values[lo]!) lo = i;
    }
    if (hi >= 0) keep.add(hi);
    if (lo >= 0) keep.add(lo);
  }
  return [...keep].sort((a, b) => a - b);
}
