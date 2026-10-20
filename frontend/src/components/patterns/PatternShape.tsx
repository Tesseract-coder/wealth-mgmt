import { useId } from "react";
import type { Direction } from "../../api/client";

type Pt = [number, number];
interface Sketch {
  /** The price path; its last leg is the breakout, drawn in the pattern's colour. */
  path: Pt[];
  /** Dashed guide lines: necklines, rims, trendlines. */
  guides: Pt[][];
  /** A smooth curve drawn instead of the path's first part (saucers and cups). */
  curve?: string;
}

// Ideal shapes on a 120 × 64 canvas (y grows downward). Bearish ones are mostly the bullish
// ones flipped, as on a chart.
const H = 64;
const flip = (s: Sketch): Sketch => ({
  path: s.path.map(([x, y]) => [x, H - y]),
  guides: s.guides.map((g) => g.map(([x, y]) => [x, H - y] as Pt)),
});

const HS: Sketch = {
  path: [[4, 58], [20, 30], [32, 42], [50, 10], [68, 42], [84, 28], [98, 42], [116, 60]],
  guides: [[[26, 42], [108, 42]]],
};
const DOUBLE_TOP: Sketch = {
  path: [[4, 58], [28, 14], [52, 40], [76, 14], [98, 40], [116, 58]],
  guides: [[[40, 40], [108, 40]], [[16, 14], [88, 14]]],
};
const RISING_WEDGE: Sketch = {
  path: [[6, 58], [22, 36], [36, 46], [56, 24], [70, 32], [88, 18], [96, 23], [116, 52]],
  guides: [[[4, 60], [100, 20]], [[4, 42], [100, 14]]],
};
const BULL_FLAG: Sketch = {
  path: [[4, 60], [36, 14], [46, 24], [54, 18], [64, 28], [72, 22], [82, 32], [116, 4]],
  guides: [[[36, 12], [90, 28]], [[42, 26], [90, 38]]],
};
const BULL_PENNANT: Sketch = {
  path: [[4, 60], [36, 12], [48, 32], [58, 18], [68, 28], [76, 21], [84, 25], [116, 4]],
  guides: [[[36, 10], [92, 22]], [[40, 36], [92, 26]]],
};
const ASC_TRIANGLE: Sketch = {
  path: [[4, 58], [22, 16], [36, 46], [54, 16], [66, 34], [82, 16], [92, 26], [116, 2]],
  guides: [[[12, 16], [104, 16]], [[20, 60], [100, 20]]],
};
const SYM_TRIANGLE: Sketch = {
  path: [[4, 12], [20, 54], [38, 20], [54, 46], [68, 27], [80, 39], [90, 32], [116, 10]],
  guides: [[[4, 8], [100, 32]], [[12, 58], [100, 34]]],
};

const SKETCH: Record<string, Sketch> = {
  head_and_shoulders: HS,
  inverse_head_and_shoulders: flip(HS),
  double_top: DOUBLE_TOP,
  double_bottom: flip(DOUBLE_TOP),
  rounding_bottom: { path: [[94, 16], [116, 4]], guides: [[[6, 14], [110, 14]]], curve: "M4,12 C24,62 74,62 94,16" },
  cup_and_handle: { path: [[80, 16], [88, 26], [96, 22], [116, 4]], guides: [[[6, 16], [108, 16]]], curve: "M4,14 C18,62 66,62 80,16" },
  rising_wedge: RISING_WEDGE,
  falling_wedge: flip(RISING_WEDGE),
  bull_flag: BULL_FLAG,
  bear_flag: flip(BULL_FLAG),
  bull_pennant: BULL_PENNANT,
  bear_pennant: flip(BULL_PENNANT),
  ascending_triangle: ASC_TRIANGLE,
  descending_triangle: flip(ASC_TRIANGLE),
  symmetrical_triangle: SYM_TRIANGLE,
};

const TONE: Record<Direction, string> = { bullish: "var(--good)", bearish: "var(--bad)", neutral: "var(--accent)" };

const pts = (p: Pt[]) => p.map(([x, y]) => `${x},${y}`).join(" ");

/** The textbook shape of a pattern, as a small drawing. Decorative: the name sits beside it. */
export function PatternShape({ patternKey, direction, className = "h-12 w-24" }: { patternKey: string; direction: Direction; className?: string }) {
  const id = `ps${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const s = SKETCH[patternKey];
  if (!s) return null;
  const body = s.path.slice(0, -1);
  const brk = s.path.slice(-2);
  const colour = TONE[direction];
  return (
    <svg viewBox="0 0 120 64" className={`shrink-0 ${className}`} aria-hidden="true">
      <defs>
        <marker id={`${id}-arrow`} viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill={colour} />
        </marker>
      </defs>
      {s.guides.map((g, i) => (
        <polyline key={i} points={pts(g)} fill="none" stroke="var(--fg-subtle)" strokeWidth={1.25} strokeDasharray="3 3" />
      ))}
      {s.curve && <path d={s.curve} fill="none" stroke="var(--fg-muted)" strokeWidth={2} strokeLinecap="round" />}
      {body.length > 1 && <polyline points={pts(body)} fill="none" stroke="var(--fg-muted)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
      <polyline points={pts(brk)} fill="none" stroke={colour} strokeWidth={2.5} strokeLinecap="round" markerEnd={`url(#${id}-arrow)`} />
    </svg>
  );
}
