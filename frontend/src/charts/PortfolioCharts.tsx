import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Slice } from "../api/client";
import { useIsDark } from "../hooks/useIsDark";
import { formatDate, formatINR } from "../lib/format";
import { palette, seriesColor } from "./palette";
import { thinIndices } from "./thin";

const pct1 = (w: number) => `${(w * 100).toFixed(1)}%`;

/** Small slices folded into "Other" so the donut stays readable. */
export function topSlices(items: Slice[], n = 7): Slice[] {
  if (items.length <= n) return items;
  const head = items.slice(0, n - 1);
  const rest = items.slice(n - 1);
  return [
    ...head,
    { key: "_other", label: `Other (${rest.length})`, value: rest.reduce((a, s) => a + s.value, 0), weight: rest.reduce((a, s) => a + s.weight, 0) },
  ];
}

/** Donut with a text legend (label, share, value), so nothing depends on colour. */
export function AllocationDonut({ items, title }: { items: Slice[]; title: string }) {
  const p = palette(useIsDark());
  const data = topSlices(items);
  return (
    <figure>
      <figcaption className="mb-1 text-sm font-semibold text-fg">{title}</figcaption>
      <div className="flex flex-col items-center gap-3 sm:flex-row">
        <div className="h-44 w-44 shrink-0" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart accessibilityLayer={false}>
              <Pie rootTabIndex={-1} data={data} dataKey="value" nameKey="label" innerRadius="58%" outerRadius="100%" stroke={p.bg} isAnimationActive={false}>
                {data.map((s, i) => (
                  <Cell key={s.key} fill={seriesColor(p, i)} />
                ))}
              </Pie>
              <Tooltip formatter={(v, name) => [formatINR(Number(v), 0), String(name)]} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="w-full space-y-1 text-sm">
          {data.map((s, i) => (
            <li key={s.key} className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2">
                <span aria-hidden="true" className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: seriesColor(p, i) }} />
                <span className="truncate">{s.label}</span>
              </span>
              <span className="whitespace-nowrap tabular-nums text-fg-muted">
                {pct1(s.weight)} · {formatINR(s.value, 0)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </figure>
  );
}

/** Horizontal sector bars with the risk level's sector limit as a dashed line. */
export function SectorBars({ items, limit }: { items: Slice[]; limit: number | null }) {
  const p = palette(useIsDark());
  const data = items.map((s) => ({ ...s, pct: +(s.weight * 100).toFixed(1), over: limit !== null && s.limited !== false && s.weight > limit }));
  return (
    <figure>
      <figcaption className="mb-1 text-sm font-semibold text-fg">
        Sectors{limit !== null && <span className="font-normal text-fg-subtle"> · dashed line = your {Math.round(limit * 100)}% sector limit</span>}
      </figcaption>
      <div style={{ height: Math.max(120, data.length * 28 + 30) }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart accessibilityLayer={false} data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
            <CartesianGrid horizontal={false} stroke={p.grid} />
            <XAxis type="number" unit="%" tick={{ fill: p.text, fontSize: 12 }} />
            <YAxis type="category" dataKey="label" width={150} tick={{ fill: p.text, fontSize: 12 }} />
            <Tooltip formatter={(v) => [`${v}%`, "Share"]} />
            {limit !== null && <ReferenceLine x={limit * 100} stroke={p.down} strokeDasharray="4 3" />}
            <Bar dataKey="pct" isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.key} fill={d.over ? p.resistance : p.series[0]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">
        {data.map((d) => (
          <li key={d.key}>
            {d.label}: {d.pct}%{d.over ? " (above your limit)" : ""}
          </li>
        ))}
      </ul>
      {data.some((d) => d.over) && (
        <p className="text-xs text-caution">
          <span aria-hidden="true">⚠ </span>Above limit: {data.filter((d) => d.over).map((d) => `${d.label} ${d.pct}%`).join(", ")}
        </p>
      )}
    </figure>
  );
}

/** Two or more series on one date axis, e.g. portfolio vs Nifty 50 (growth of 100). */
export function ComparisonLine({
  dates,
  series,
  unit = "",
  height = 240,
  zeroLine = false,
}: {
  dates: string[];
  series: { name: string; values: (number | null)[]; dashed?: boolean }[];
  unit?: string;
  height?: number;
  zeroLine?: boolean;
}) {
  const p = palette(useIsDark());
  // A few hundred points are all a chart this wide can show; thousands block a phone's main thread.
  const data = thinIndices(dates.length, series.map((s) => s.values)).map((i) => {
    const d = dates[i]!;
    const row: Record<string, string | number | null> = { d };
    for (const s of series) row[s.name] = s.values[i] ?? null;
    return row;
  });
  return (
    <div style={{ height }} aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart accessibilityLayer={false} data={data} margin={{ left: 0, right: 12, top: 8 }}>
          <CartesianGrid stroke={p.grid} vertical={false} />
          <XAxis dataKey="d" tickFormatter={(d: string) => formatDate(d).slice(3)} minTickGap={40} tick={{ fill: p.text, fontSize: 12 }} />
          <YAxis domain={["auto", "auto"]} unit={unit} width={52} tick={{ fill: p.text, fontSize: 12 }} />
          <Tooltip
            labelFormatter={(d) => formatDate(String(d))}
            formatter={(v, n) => [`${Number(v).toFixed(2)}${unit}`, String(n)]}
            contentStyle={{ background: p.bg, border: `1px solid ${p.grid}`, borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: p.text }}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: p.text }} />
          {zeroLine && <ReferenceLine y={0} stroke={p.neutral} />}
          {series.map((s, i) => (
            <Line key={s.name} dataKey={s.name} stroke={seriesColor(p, i)} strokeDasharray={s.dashed ? "5 4" : undefined} dot={false} strokeWidth={2} connectNulls isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
