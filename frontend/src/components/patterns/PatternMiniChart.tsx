import type { Direction, PatternMatch, PatternReport } from "../../api/client";
import { formatDate } from "../../lib/format";

const W = 360;
const H = 190;
const PAD = { l: 4, r: 92, t: 14, b: 18 };
const LEAD = 10; // bars shown before the pattern starts

const TONE: Record<Direction, string> = { bullish: "var(--good)", bearish: "var(--bad)", neutral: "var(--accent)" };

/** Spread labels at least `gap` apart vertically, keeping their order. */
function spread<T extends { y: number }>(items: T[], gap: number, lo: number, hi: number): T[] {
  const s = [...items].sort((a, b) => a.y - b.y);
  for (let i = 1; i < s.length; i++) if (s[i]!.y - s[i - 1]!.y < gap) s[i]!.y = s[i - 1]!.y + gap;
  const over = (s.at(-1)?.y ?? 0) - hi;
  if (over > 0) s.forEach((it) => (it.y = Math.max(lo, it.y - over)));
  return s;
}

/**
 * The pattern on the stock's own bars: candles, the pattern's lines and points, and its breakout,
 * target and cancel levels. Self-contained SVG, so every card can draw its own.
 */
export function PatternMiniChart({ window: w, match: m, px }: { window: PatternReport["window"]; match: PatternMatch; px: (v: number) => string }) {
  const index = new Map(w.t.map((t, i) => [t, i]));
  const startI = index.get(m.start) ?? 0;
  const endI = index.get(m.end) ?? w.t.length - 1;
  const s0 = Math.max(0, startI - LEAD);
  const s1 = w.t.length - 1;
  const n = s1 - s0 + 1;
  if (n < 2) return null;
  const levels = [
    { key: "breakout", label: m.direction === "neutral" ? "Up" : "Breakout", v: m.breakout, colour: "var(--fg)" },
    { key: "target", label: "Target", v: m.target, colour: TONE[m.direction] },
    { key: "cancel", label: m.direction === "neutral" ? "Down" : "Cancel", v: m.invalidation, colour: "var(--caution)" },
  ].filter((l): l is typeof l & { v: number } => l.v != null);

  let lo = Infinity;
  let hi = -Infinity;
  for (let i = s0; i <= s1; i++) {
    lo = Math.min(lo, w.low[i]!);
    hi = Math.max(hi, w.high[i]!);
  }
  // Levels widen the view, but a far-off target would squash the pattern: it is pinned to the
  // edge with an arrow instead.
  const reach = (hi - lo) * 0.5;
  const far = (v: number) => v < lo - reach || v > hi + reach;
  for (const l of levels) {
    if (far(l.v)) continue;
    lo = Math.min(lo, l.v);
    hi = Math.max(hi, l.v);
  }
  const padV = (hi - lo) * 0.04 || 1;
  lo -= padV;
  hi += padV;
  const plotW = W - PAD.l - PAD.r;
  const x = (i: number) => PAD.l + ((i - s0) / (n - 1)) * plotW;
  const y = (v: number) => PAD.t + ((hi - v) / (hi - lo)) * (H - PAD.t - PAD.b);
  const xAt = (t: string) => {
    const i = index.get(t);
    return i === undefined || i < s0 ? null : x(i);
  };
  const offSide = (v: number) => (v < lo ? "↓" : v > hi ? "↑" : "");
  const bodyW = Math.max(1, Math.min(6, (plotW / n) * 0.6));
  const colour = TONE[m.direction];
  const ly = (v: number) => Math.min(H - PAD.b, Math.max(PAD.t, y(v)));
  const labels = spread(
    levels.map((l) => ({ ...l, y: ly(l.v), off: offSide(l.v) })),
    11,
    PAD.t,
    H - PAD.b,
  );

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={`${m.name} on the chart from ${formatDate(m.start)}: ${m.text}`}>
      <rect x={x(startI)} y={PAD.t - 6} width={Math.max(2, x(endI) - x(startI))} height={H - PAD.t - PAD.b + 6} fill="var(--accent-soft)" opacity={0.55} rx={3} />
      {Array.from({ length: n }, (_, k) => {
        const i = s0 + k;
        const o = w.open[i]!;
        const c = w.close[i]!;
        const up = c >= o;
        const cx = x(i);
        const top = y(Math.max(o, c));
        return (
          <g key={i} stroke={up ? "var(--chart-up)" : "var(--chart-down)"} opacity={0.75}>
            <line x1={cx} x2={cx} y1={y(w.high[i]!)} y2={y(w.low[i]!)} strokeWidth={1} />
            <rect x={cx - bodyW / 2} y={top} width={bodyW} height={Math.max(1, y(Math.min(o, c)) - top)} fill={up ? "var(--chart-up)" : "var(--chart-down)"} strokeWidth={0} />
          </g>
        );
      })}
      {levels.map((l) => (
        <line key={l.key} x1={x(startI)} x2={PAD.l + plotW} y1={ly(l.v)} y2={ly(l.v)} stroke={l.colour} strokeWidth={1} strokeDasharray={l.key === "breakout" ? undefined : offSide(l.v) ? "1 4" : "4 3"} opacity={0.8} />
      ))}
      {m.lines.map((ln, li) => {
        const p = ln.points.map((pt) => [xAt(pt.t), y(pt.price)] as const).filter((q): q is readonly [number, number] => q[0] !== null);
        if (p.length < 2) return null;
        return (
          <polyline
            key={li}
            points={p.map(([a, b]) => `${a},${b}`).join(" ")}
            fill="none"
            stroke={colour}
            strokeWidth={ln.kind === "curve" ? 1.5 : 2}
            strokeDasharray={ln.kind === "curve" ? undefined : "6 4"}
            opacity={ln.kind === "curve" ? 0.7 : 0.95}
            strokeLinecap="round"
          />
        );
      })}
      {m.points.map((pt, k) => {
        const cx = xAt(pt.t);
        if (cx === null) return null;
        const i = index.get(pt.t)!;
        const above = pt.price >= (w.high[i]! + w.low[i]!) / 2;
        const cy = y(pt.price);
        return (
          <g key={k}>
            <circle cx={cx} cy={cy} r={3} fill={colour} stroke="var(--surface)" strokeWidth={1} />
            {pt.label && (
              <text x={cx} y={above ? cy - 6 : cy + 12} textAnchor="middle" fontSize={9} fontWeight={600} fill="var(--fg)" stroke="var(--surface)" strokeWidth={3} paintOrder="stroke">
                {pt.label}
              </text>
            )}
          </g>
        );
      })}
      {labels.map((l) => (
        <text key={l.key} x={PAD.l + plotW + 4} y={l.y + 3} fontSize={9.5} fill={l.colour} fontWeight={600}>
          {l.off}
          {l.label} {px(l.v)}
        </text>
      ))}
      <text x={PAD.l} y={H - 4} fontSize={9} fill="var(--fg-subtle)">
        {formatDate(w.t[s0])}
      </text>
      <text x={PAD.l + plotW} y={H - 4} fontSize={9} fill="var(--fg-subtle)" textAnchor="end">
        {formatDate(w.t[s1])}
      </text>
    </svg>
  );
}
