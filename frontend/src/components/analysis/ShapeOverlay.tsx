import { AXIS_LABEL, AXIS_SHORT, formatScore, point, pts, type ShapeAxis } from "./ScoreShape";

export interface OverlaySeries {
  name: string;
  axes: ShapeAxis[];
  total: number;
  maxTotal: number;
}

/** Colours and dash patterns for up to four shapes: each series differs by line style too, not just colour. */
const STYLES = [
  { color: "var(--chart-1)", dash: undefined },
  { color: "var(--chart-2)", dash: "6 3" },
  { color: "var(--chart-3)", dash: "2 3" },
  { color: "var(--chart-4)", dash: "8 3 2 3" },
];

/**
 * Two to four Score Shapes on one set of axes, for comparing stocks. The axes follow the first
 * series' order; a legend names each shape with its line style and total.
 */
export function ShapeOverlay({ series, max = 6 }: { series: OverlaySeries[]; max?: number }) {
  const keys = series[0]?.axes.map((a) => a.key) ?? [];
  const n = keys.length;
  const R = 100;
  if (n < 3) return null;
  const title = `Score Shapes compared: ${series
    .map((s) => `${s.name} ${formatScore(s.total)} of ${formatScore(s.maxTotal)} (${s.axes.map((a) => `${AXIS_LABEL[a.key] ?? a.label} ${a.score === null ? "no data" : formatScore(a.score)}`).join(", ")})`)
    .join("; ")}.`;
  return (
    <div className="flex flex-col items-center gap-3">
      <svg role="img" aria-label={title} viewBox="-175 -140 350 285" className="h-auto w-full max-w-[400px] overflow-visible">
        <title>{title}</title>
        {[max / 3, (2 * max) / 3, max].map((r) => (
          <polygon key={r} points={pts(keys.map((_, i) => point(i, n, (r / max) * R)))} fill={r === max ? "var(--surface-2)" : "none"} stroke="var(--border)" />
        ))}
        {keys.map((k, i) => {
          const [x, y] = point(i, n, R);
          const [lx, ly] = point(i, n, R + 18);
          return (
            <g key={k}>
              <line x1={0} y1={0} x2={x} y2={y} stroke="var(--border)" />
              <text x={lx} y={ly + 4} textAnchor={Math.abs(lx) < 4 ? "middle" : lx > 0 ? "start" : "end"} className="fill-[var(--fg-muted)] text-xs" aria-hidden="true">
                {AXIS_SHORT[k] ?? k}
              </text>
            </g>
          );
        })}
        {series.map((s, si) => {
          const st = STYLES[si % STYLES.length]!;
          const by = new Map(s.axes.map((a) => [a.key, a.score]));
          const v = keys.map((k, i) => point(i, n, (Math.max(0, Math.min(by.get(k) ?? 0, max)) / max) * R));
          return (
            <g key={s.name} className="shape-in">
              <polygon points={pts(v)} fill={st.color} fillOpacity={0.12} stroke={st.color} strokeWidth={2.25} strokeDasharray={st.dash} strokeLinejoin="round" />
              {v.map(([x, y], i) => (
                <circle key={keys[i]} cx={x} cy={y} r={3} fill={st.color} />
              ))}
            </g>
          );
        })}
      </svg>
      <ul className="flex flex-wrap justify-center gap-x-5 gap-y-1 text-sm" aria-label="Legend">
        {series.map((s, si) => {
          const st = STYLES[si % STYLES.length]!;
          return (
            <li key={s.name} className="flex items-center gap-2">
              <svg width="28" height="8" aria-hidden="true">
                <line x1="1" y1="4" x2="27" y2="4" stroke={st.color} strokeWidth="2.5" strokeDasharray={st.dash} />
              </svg>
              <span className="text-fg">{s.name}</span>
              <span className="text-fg-subtle">
                {formatScore(s.total)}/{formatScore(s.maxTotal)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
