import { useId, useState, type KeyboardEvent } from "react";
import type { PortfolioShape, SectionResult, StyleKey } from "../../api/client";
import { Badge } from "../ui";

/** One spoke of the shape. `score` null = not enough data (drawn at the centre, dashed spoke). */
export interface ShapeAxis {
  key: string;
  label: string;
  score: number | null;
  /** Shown when the axis is hovered, tapped or reached with the arrow keys (e.g. "Top pass: …"). */
  detail?: string[];
}

export type ShapeSize = "sm" | "md" | "lg";

/** Full names, for tooltips and the accessible label. */
export const AXIS_LABEL: Record<string, string> = {
  valuation: "Valuation",
  growth: "Future Growth",
  past: "Past Performance",
  health: "Financial Health",
  momentum: "Momentum",
  dividends: "Dividends",
  returns: "Returns",
  consistency: "Consistency",
  risk: "Risk",
  risk_adjusted: "Risk-adjusted",
  cost: "Cost",
};

/** Short names that fit around the large shape. */
export const AXIS_SHORT: Record<string, string> = {
  valuation: "Value",
  growth: "Future",
  past: "Past",
  health: "Health",
  momentum: "Momentum",
  dividends: "Dividends",
  returns: "Returns",
  consistency: "Consistency",
  risk: "Risk",
  risk_adjusted: "Risk-adj.",
  cost: "Cost",
};

const FUNDAMENTAL_AXES = new Set(["valuation", "growth", "past", "health", "dividends"]);
const SHORT_TERM: StyleKey[] = ["swing", "intraday"];
const STYLE_NAME: Record<StyleKey, string> = { intraday: "Intraday", swing: "Swing", positional: "Positional", long_term: "Long-term", custom: "Custom" };

/** Same thresholds as checks.yaml `axis.score_steps`: share of the maximum → colour step 1 (weak) … 5 (strong). */
export const SCORE_STEPS = [0.2, 0.4, 0.6, 0.8];

export function stepFor(score: number, max: number, steps: number[] = SCORE_STEPS): number {
  if (max <= 0) return 1;
  const share = score / max;
  return 1 + steps.filter((s) => share >= s).length;
}

export const formatScore = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

/**
 * Display order for a style. Swing and intraday traders see Momentum first; everyone else sees the
 * fundamentals first. Only the order and emphasis change, never the scores.
 */
export function orderAxes(axes: ShapeAxis[], style?: StyleKey | null): ShapeAxis[] {
  if (!style || !SHORT_TERM.includes(style)) return axes;
  const m = axes.filter((a) => a.key === "momentum");
  return [...m, ...axes.filter((a) => a.key !== "momentum")];
}

export function isEmphasised(key: string, style?: StyleKey | null): boolean {
  if (!style) return false;
  if (SHORT_TERM.includes(style)) return key === "momentum";
  if (style === "long_term") return FUNDAMENTAL_AXES.has(key);
  return false;
}

/** Axes from a stock's or fund's sections, with the first passing and failing check as the detail. */
export function axesFromSections(sections: SectionResult[]): ShapeAxis[] {
  return sections.map((s) => {
    // Checks flagged as rewards/risks are the headline ones, so they lead.
    const ranked = [...s.checks].sort((a, b) => b.highlight.length - a.highlight.length);
    const pass = ranked.find((c) => c.status === "pass");
    const fail = ranked.find((c) => c.status === "fail");
    const detail = [
      `${s.passed} of ${s.checks.length} checks passed`,
      ...(pass ? [`Top pass: ${pass.label}`] : []),
      ...(fail ? [`Top fail: ${fail.label}`] : []),
      ...(s.note ? [s.note] : []),
    ];
    return { key: s.key, label: s.label, score: s.score, detail };
  });
}

/** Axes from a bare `{key: score}` record (holding rows, watchlist items, screener results). */
export function axesFromRecord(axes: Record<string, number | null>, labels: Record<string, string> = AXIS_LABEL): ShapeAxis[] {
  return Object.entries(axes).map(([key, score]) => ({ key, label: labels[key] ?? key, score }));
}

/** The portfolio's value-weighted axes, with how much of the stock value each one covers. */
export function axesFromPortfolio(p: PortfolioShape): ShapeAxis[] {
  return p.axes.map((a) => ({
    key: a.key,
    label: a.label,
    score: a.score,
    detail: [`Weighted average of your stocks`, `Covers ${Math.round(a.coverage * 100)}% of stock value`],
  }));
}

const GEOMETRY: Record<ShapeSize, { w: number; h: number; r: number; px: number }> = {
  sm: { w: 32, h: 32, r: 14, px: 32 },
  md: { w: 116, h: 116, r: 50, px: 116 },
  lg: { w: 360, h: 300, r: 96, px: 360 },
};

function point(i: number, n: number, radius: number): [number, number] {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
  return [Math.cos(a) * radius, Math.sin(a) * radius];
}

const pts = (list: [number, number][]) => list.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");

/**
 * The Score Shape: one spoke per section, each scored 0 … max by the share of its checks that pass,
 * so the shape and the check lists always agree. A big shape is strong, a small one weak; the fill
 * colour follows the total on a 5-step scale and the total is always written out as text too.
 *
 * sm (32 px) is a static thumbnail for table rows. md and lg read out each axis on hover, tap or
 * focus + arrow keys.
 */
export function ScoreShape({
  axes,
  max = 6,
  total,
  maxTotal,
  step,
  size = "md",
  style,
  name,
  showTotal = size !== "sm",
  animate = true,
  className = "",
}: {
  axes: ShapeAxis[];
  max?: number;
  total?: number | null;
  maxTotal?: number | null;
  step?: number | null;
  size?: ShapeSize;
  /** The active style: changes the order and emphasis of the axes, never the scores. */
  style?: StyleKey | null;
  /** What the shape describes, for screen readers ("Reliance Industries Ltd"). */
  name?: string;
  showTotal?: boolean;
  animate?: boolean;
  className?: string;
}) {
  const ordered = orderAxes(axes, style);
  const n = ordered.length;
  const g = GEOMETRY[size];
  const interactive = size !== "sm" && n > 0;
  const [active, setActive] = useState<number | null>(null);
  const readoutId = useId();

  const sum = total ?? ordered.reduce((s, a) => s + (a.score ?? 0), 0);
  const outOf = maxTotal ?? max * n;
  const colourStep = step ?? (n ? stepFor(sum, outOf) : null);
  const colour = colourStep ? `var(--score-${colourStep})` : "var(--neutral)";
  const shortTerm = !!style && SHORT_TERM.includes(style);

  const describe = (a: ShapeAxis) => `${AXIS_LABEL[a.key] ?? a.label} ${a.score === null ? "not enough data" : `${formatScore(a.score)} of ${max}`}`;
  const totalText = `total ${formatScore(sum)} of ${formatScore(outOf)}`;
  const title = `Score Shape${name ? ` for ${name}` : ""}: ${ordered.map(describe).join(", ")}; ${totalText}.`;

  if (n < 3) {
    // A shape needs at least three spokes; fall back to the numbers.
    return (
      <p className={`text-xs text-fg-muted ${className}`} aria-label={title}>
        {ordered.length ? ordered.map(describe).join(" · ") : "No Score Shape yet"}
      </p>
    );
  }

  const vertices = ordered.map((a, i) => point(i, n, (Math.max(0, Math.min(a.score ?? 0, max)) / max) * g.r));
  const rings = size === "sm" ? [max] : [max / 3, (2 * max) / 3, max];
  const half = Math.PI / n;

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") setActive((v) => ((v ?? -1) + 1) % n);
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") setActive((v) => ((v ?? 0) - 1 + n) % n);
    else if (e.key === "Escape") setActive(null);
    else return;
    e.preventDefault();
  };

  const svg = (
    <svg
      role="img"
      aria-label={title}
      width={g.px}
      height={(g.px * g.h) / g.w}
      viewBox={`${-g.w / 2} ${-g.h / 2} ${g.w} ${g.h}`}
      className="h-auto max-w-full overflow-visible"
      onPointerLeave={interactive ? () => setActive(null) : undefined}
    >
      <title>{title}</title>
      {/* Grid: rings at a third, two thirds and the full score, then the spokes. */}
      {rings.map((r) => (
        <polygon
          key={r}
          points={pts(ordered.map((_, i) => point(i, n, (r / max) * g.r)))}
          fill={r === max ? "var(--surface-2)" : "none"}
          stroke="var(--border)"
          strokeWidth={size === "sm" ? 1 : 1}
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {size !== "sm" &&
        ordered.map((a, i) => {
          const [x, y] = point(i, n, g.r);
          return (
            <line
              key={a.key}
              x1={0}
              y1={0}
              x2={x}
              y2={y}
              stroke={active === i ? "var(--accent)" : "var(--border)"}
              strokeWidth={active === i ? 2 : 1}
              strokeDasharray={a.score === null ? "3 3" : undefined}
            />
          );
        })}

      <g className={animate ? "shape-in" : undefined} data-testid="shape-fill">
        <polygon
          points={pts(vertices)}
          fill={colour}
          fillOpacity={0.38}
          stroke={colour}
          strokeWidth={size === "sm" ? 1.25 : 2}
          strokeLinejoin="round"
        />
        {size !== "sm" &&
          vertices.map(([x, y], i) => (
            <circle key={ordered[i]?.key ?? i} cx={x} cy={y} r={active === i ? 4.5 : size === "lg" ? 3 : 2} fill={colour} stroke="var(--surface)" strokeWidth={1} />
          ))}
      </g>

      {size === "lg" &&
        ordered.map((a, i) => {
          const [x, y] = point(i, n, g.r + 16);
          const anchor = Math.abs(x) < 4 ? "middle" : x > 0 ? "start" : "end";
          const top = y < -g.r / 2;
          const bottom = y > g.r / 2;
          const dy = top ? -18 : bottom ? 14 : -4;
          const strong = isEmphasised(a.key, style);
          return (
            <text key={a.key} x={x} y={y + dy} textAnchor={anchor} className="text-xs" aria-hidden="true">
              <tspan x={x} fill={strong ? "var(--fg)" : "var(--fg-muted)"} fontWeight={strong ? 650 : 500}>
                {AXIS_SHORT[a.key] ?? a.label}
              </tspan>
              <tspan x={x} dy={15} fill="var(--fg)" fontWeight={650}>
                {a.score === null ? "—" : formatScore(a.score)}
                <tspan fill="var(--fg-subtle)" fontWeight={400}>{a.score === null ? " no data" : `/${max}`}</tspan>
              </tspan>
            </text>
          );
        })}

      {/* Invisible wedges catch hover and tap for each axis. */}
      {interactive &&
        ordered.map((a, i) => {
          const R = g.r + (size === "lg" ? 40 : 8);
          const a0 = -Math.PI / 2 + (i * 2 * Math.PI) / n - half;
          const a1 = a0 + 2 * half;
          const d = `M0,0 L${Math.cos(a0) * R},${Math.sin(a0) * R} A${R},${R} 0 0 1 ${Math.cos(a1) * R},${Math.sin(a1) * R} Z`;
          return (
            <path
              key={a.key}
              d={d}
              fill="transparent"
              data-axis={a.key}
              onPointerEnter={() => setActive(i)}
              onClick={() => setActive(i)}
            />
          );
        })}
    </svg>
  );

  if (!interactive) {
    return <span className={`inline-flex shrink-0 ${className}`}>{svg}</span>;
  }

  const current = active === null ? null : ordered[active];
  return (
    <div className={`relative inline-flex max-w-full flex-col items-center ${className}`}>
      <div
        role="group"
        tabIndex={0}
        aria-label="Score Shape. Use the arrow keys to read each axis."
        aria-describedby={readoutId}
        onKeyDown={onKey}
        onFocus={() => setActive((v) => v ?? 0)}
        onBlur={() => setActive(null)}
        className="max-w-full rounded-card"
      >
        {svg}
      </div>

      {showTotal && (
        <p className={`flex flex-wrap items-center justify-center gap-2 ${size === "lg" ? "mt-1 text-sm" : "mt-0.5 text-xs"}`}>
          <span className="font-semibold text-fg">
            {size === "lg" ? "Total " : ""}
            {formatScore(sum)}
            <span className="font-normal text-fg-subtle">/{formatScore(outOf)}</span>
          </span>
          {shortTerm && style && <Badge tone="accent">Style: {STYLE_NAME[style]}</Badge>}
        </p>
      )}

      <div
        id={readoutId}
        aria-live="polite"
        className={
          size === "lg"
            ? "mt-2 min-h-10 max-w-xs text-center text-xs text-fg-muted"
            : `pointer-events-none absolute left-1/2 top-full z-10 mt-1 w-56 -translate-x-1/2 rounded-control border border-border bg-surface-3 px-2.5 py-1.5 text-xs text-fg shadow-pop ${current ? "" : "sr-only"}`
        }
      >
        {current ? (
          <>
            <span className="font-semibold text-fg">
              {AXIS_LABEL[current.key] ?? current.label}: {current.score === null ? "Not enough data" : `${formatScore(current.score)}/${max}`}
            </span>
            {current.detail?.map((d) => (
              <span key={d} className="block">
                {d}
              </span>
            ))}
          </>
        ) : size === "lg" ? (
          "Hover, tap or use the arrow keys to read each axis."
        ) : null}
      </div>
    </div>
  );
}
