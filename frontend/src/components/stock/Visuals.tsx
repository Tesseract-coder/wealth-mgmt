/* Small infographics for the stock page, drawn with HTML and SVG (no chart library, so they load
 * with the page). Each one also says its numbers in text: nothing is told by colour alone. */
import type { FairValue } from "../../api/client";
import { formatINR } from "../../lib/format";

/** Price against the fair-value estimate, with the gap written out. */
export function FairValueBar({ fv }: { fv: FairValue }) {
  const max = Math.max(fv.price, fv.value) * 1.15;
  const below = fv.price <= fv.value;
  const rows = [
    { label: "Fair value (estimate)", value: fv.value, cls: "bg-accent" },
    { label: "Price", value: fv.price, cls: below ? "bg-good" : "bg-bad" },
  ];
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[8.5rem_1fr] items-center gap-2 text-sm max-sm:grid-cols-1 max-sm:gap-1">
          <span className="text-fg-muted">{r.label}</span>
          <div className="flex items-center gap-2">
            <div className="h-6 rounded-[4px] bg-surface-2" style={{ width: "100%" }}>
              <div className={`h-6 rounded-[4px] ${r.cls}`} style={{ width: `${(r.value / max) * 100}%` }} />
            </div>
            <span className="w-24 shrink-0 text-right font-semibold text-fg">{formatINR(r.value)}</span>
          </div>
        </div>
      ))}
      <p className={`text-sm font-semibold ${below ? "text-good" : "text-bad"}`}>
        {Math.abs(fv.gap_pct) < 1 ? "About at fair value" : `${Math.abs(fv.gap_pct).toFixed(1)}% ${below ? "below" : "above"} fair value`}
      </p>
    </div>
  );
}

export interface CompareItem {
  label: string;
  value: number | null;
  display: string;
  /** The subject (this stock): drawn in the accent colour and bold. */
  self?: boolean;
}

/** Horizontal bars comparing one figure across a few references (P/E vs sector vs own history). */
export function CompareBars({ items, label }: { items: CompareItem[]; label: string }) {
  const max = Math.max(...items.map((i) => i.value ?? 0), 0) * 1.1 || 1;
  return (
    <ul aria-label={label} className="space-y-2">
      {items.map((i) => (
        <li key={i.label} className="grid grid-cols-[9rem_1fr_4.5rem] items-center gap-2 text-sm max-sm:grid-cols-[7rem_1fr_4rem]">
          <span className={i.self ? "font-semibold text-fg" : "text-fg-muted"}>{i.label}</span>
          <div className="h-4 rounded-[3px] bg-surface-2">
            {i.value !== null && i.value > 0 && <div className={`h-4 rounded-[3px] ${i.self ? "bg-accent" : "bg-border-strong"}`} style={{ width: `${(i.value / max) * 100}%` }} />}
          </div>
          <span className={`text-right ${i.self ? "font-semibold text-fg" : "text-fg-muted"}`}>{i.display}</span>
        </li>
      ))}
    </ul>
  );
}

/** A half-circle RSI gauge with the app's zones and the reading in words. */
export function RsiGauge({ rsi, band, oversold, zone }: { rsi: number; band: [number, number]; oversold: number; zone: string }) {
  const R = 70;
  const at = (v: number) => {
    const a = Math.PI * (1 - Math.max(0, Math.min(100, v)) / 100);
    return [Math.cos(a) * R, -Math.sin(a) * R] as const;
  };
  const arc = (from: number, to: number) => {
    const [x0, y0] = at(from);
    const [x1, y1] = at(to);
    return `M${x0},${y0} A${R},${R} 0 0 1 ${x1},${y1}`;
  };
  const zones = [
    { from: 0, to: oversold, color: "var(--score-2)", name: "Oversold" },
    { from: oversold, to: band[0], color: "var(--score-1)", name: "Weak" },
    { from: band[0], to: band[1], color: "var(--score-5)", name: "Healthy" },
    { from: band[1], to: 100, color: "var(--score-3)", name: "Overbought" },
  ];
  const [nx, ny] = at(rsi);
  return (
    <figure className="flex flex-col items-center" aria-label={`RSI ${rsi.toFixed(1)}: ${zone}`} role="img">
      <svg viewBox="-85 -82 170 100" className="w-48 max-w-full" aria-hidden="true">
        {zones.map((z) => (
          <path key={z.name} d={arc(z.from, z.to)} stroke={z.color} strokeWidth={12} fill="none" />
        ))}
        <line x1={0} y1={0} x2={nx * 0.88} y2={ny * 0.88} stroke="var(--fg)" strokeWidth={2.5} strokeLinecap="round" />
        <circle r={4} fill="var(--fg)" />
        <text x={-R} y={14} textAnchor="middle" className="fill-[var(--fg-subtle)] text-[9px]">0</text>
        <text x={R} y={14} textAnchor="middle" className="fill-[var(--fg-subtle)] text-[9px]">100</text>
      </svg>
      <p className="-mt-1 text-lg font-semibold text-fg">RSI {rsi.toFixed(1)}</p>
      <p className="text-center text-xs text-fg-muted">
        Zones: oversold &lt;{oversold} · weak · healthy {band[0]}–{band[1]} · overbought &gt;{band[1]}
      </p>
    </figure>
  );
}

/** Who owns the company: promoters, FIIs, DIIs and everyone else, as one stacked bar with a text legend. */
export function OwnershipBar({ promoter, fii, dii }: { promoter: number | null; fii: number | null; dii: number | null }) {
  const parts = [
    { label: "Promoters", value: promoter, color: "var(--chart-1)" },
    { label: "Foreign institutions (FII)", value: fii, color: "var(--chart-3)" },
    { label: "Domestic institutions (DII)", value: dii, color: "var(--chart-2)" },
  ].filter((p): p is { label: string; value: number; color: string } => p.value !== null);
  const known = parts.reduce((s, p) => s + p.value, 0);
  const all = [...parts, ...(known < 100 ? [{ label: "Public and others", value: 100 - known, color: "var(--surface-3)" }] : [])];
  return (
    <div>
      <div className="flex h-6 overflow-hidden rounded-[4px] border border-border" aria-hidden="true">
        {all.map((p) => (
          <div key={p.label} style={{ width: `${p.value}%`, background: p.color }} />
        ))}
      </div>
      <ul className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
        {all.map((p) => (
          <li key={p.label} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-fg-muted">
              <span aria-hidden="true" className="inline-block size-2.5 rounded-sm border border-border" style={{ background: p.color }} />
              {p.label}
            </span>
            <span className="font-semibold text-fg">{p.value.toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
