/* Year-by-year charts for the stock page (Recharts). Loaded lazily: they sit below the fold. Each
 * chart has a text legend, exact values in its tooltip, and a hidden table for screen readers. */
import type { ReactElement, ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { FinancialHistory } from "../../api/client";
import { palette, type Palette } from "../../charts/palette";
import { useIsDark } from "../../hooks/useIsDark";
import { formatNumber } from "../../lib/format";

type Years = FinancialHistory["years"];
type Quarters = FinancialHistory["quarters"];

const byDate = <T extends { year_end?: string; period_end?: string }>(rows: T[]) =>
  [...rows].sort((a, b) => (a.year_end ?? a.period_end ?? "").localeCompare(b.year_end ?? b.period_end ?? ""));

const cr = (unit: string) => (v: unknown) => (typeof v === "number" ? `${unit === "₹ Cr" ? "₹" : ""}${formatNumber(v, 0)}${unit === "₹ Cr" ? " Cr" : ` ${unit}`}` : "—");
const pctFmt = (v: unknown) => (typeof v === "number" ? `${v.toFixed(1)}%` : "—");
/** Axis ticks in lakh crore (from ₹10,000 Cr) or thousand crore, so they stay short. */
const short = (v: number) => (Math.abs(v) >= 10_000 ? `${(v / 100_000).toFixed(1)}L` : Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(Math.round(v)));

function axes(p: Palette) {
  return {
    grid: <CartesianGrid vertical={false} stroke={p.grid} />,
    tick: { fill: p.text, fontSize: 12 },
    tooltip: { contentStyle: { background: p.bg, border: `1px solid ${p.grid}`, borderRadius: 8, fontSize: 12 }, labelStyle: { color: p.text } },
  };
}

function Frame({ height = 220, table, children }: { height?: number; table: ReactNode; children: ReactElement }) {
  return (
    <>
      <div style={{ height }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
      {table}
    </>
  );
}

function SrTable({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>
          {head.map((h) => (
            <th key={h}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={String(r[0])}>
            {r.map((c, i) => (
              <td key={i}>{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Revenue and net profit by financial year. */
export function RevenueProfitChart({ years, unit }: { years: Years; unit: string }) {
  const p = palette(useIsDark());
  const a = axes(p);
  const data = byDate(years).map((y) => ({ fy: y.fy, Revenue: y.revenue, "Net profit": y.net_income }));
  const f = cr(unit);
  return (
    <Frame table={<SrTable caption={`Revenue and net profit (${unit})`} head={["Year", "Revenue", "Net profit"]} rows={data.map((d) => [d.fy, f(d.Revenue), f(d["Net profit"])])} />}>
      <BarChart accessibilityLayer={false} data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        {a.grid}
        <XAxis dataKey="fy" tick={a.tick} stroke={p.grid} />
        <YAxis tick={a.tick} tickFormatter={short} width={44} stroke={p.grid} />
        <Tooltip formatter={(v, n) => [f(v), String(n)]} {...a.tooltip} cursor={{ fill: p.grid, opacity: 0.4 }} />
        <Legend wrapperStyle={{ fontSize: 12, color: p.text }} />
        <Bar dataKey="Revenue" fill={p.series[0]} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="Net profit" fill={p.series[2]} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </Frame>
  );
}

/** The last few quarters' revenue and profit. */
export function QuarterChart({ quarters, unit }: { quarters: Quarters; unit: string }) {
  const p = palette(useIsDark());
  const a = axes(p);
  const data = byDate(quarters)
    .slice(-6)
    .map((q) => ({ q: q.label.replace(" quarter", ""), Revenue: q.revenue, "Net profit": q.net_income }));
  const f = cr(unit);
  return (
    <Frame height={200} table={<SrTable caption={`Quarterly revenue and net profit (${unit})`} head={["Quarter", "Revenue", "Net profit"]} rows={data.map((d) => [d.q, f(d.Revenue), f(d["Net profit"])])} />}>
      <BarChart accessibilityLayer={false} data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        {a.grid}
        <XAxis dataKey="q" tick={a.tick} stroke={p.grid} />
        <YAxis tick={a.tick} tickFormatter={short} width={44} stroke={p.grid} />
        <Tooltip formatter={(v, n) => [f(v), String(n)]} {...a.tooltip} cursor={{ fill: p.grid, opacity: 0.4 }} />
        <Legend wrapperStyle={{ fontSize: 12, color: p.text }} />
        <Bar dataKey="Revenue" fill={p.series[0]} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="Net profit" fill={p.series[2]} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </Frame>
  );
}

/** Operating margin, net margin and ROE by year (all %). */
export function MarginRoeChart({ years }: { years: Years }) {
  const p = palette(useIsDark());
  const a = axes(p);
  const data = byDate(years).map((y) => ({ fy: y.fy, "Operating margin": y.op_margin, "Net margin": y.net_margin, ROE: y.roe }));
  const keys = (["Operating margin", "Net margin", "ROE"] as const).filter((k) => data.some((d) => d[k] !== null));
  return (
    <Frame table={<SrTable caption="Margins and ROE (%)" head={["Year", ...keys]} rows={data.map((d) => [d.fy, ...keys.map((k) => pctFmt(d[k]))])} />}>
      <LineChart accessibilityLayer={false} data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        {a.grid}
        <XAxis dataKey="fy" tick={a.tick} stroke={p.grid} />
        <YAxis tick={a.tick} unit="%" width={44} stroke={p.grid} />
        <Tooltip formatter={(v, n) => [pctFmt(v), String(n)]} {...a.tooltip} />
        <Legend wrapperStyle={{ fontSize: 12, color: p.text }} />
        {keys.map((k, i) => (
          <Line key={k} dataKey={k} stroke={p.series[[0, 2, 1][i]!]} strokeWidth={2} strokeDasharray={k === "ROE" ? "5 3" : undefined} dot={{ r: 3 }} isAnimationActive={false} connectNulls />
        ))}
      </LineChart>
    </Frame>
  );
}

/** Debt, equity and cash on the balance sheet at each year-end. */
export function BalanceChart({ years, unit }: { years: Years; unit: string }) {
  const p = palette(useIsDark());
  const a = axes(p);
  const data = byDate(years).map((y) => ({ fy: y.fy, Debt: y.total_debt, Equity: y.equity, Cash: y.cash }));
  const f = cr(unit);
  return (
    <Frame table={<SrTable caption={`Debt, equity and cash (${unit})`} head={["Year", "Debt", "Equity", "Cash"]} rows={data.map((d) => [d.fy, f(d.Debt), f(d.Equity), f(d.Cash)])} />}>
      <BarChart accessibilityLayer={false} data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        {a.grid}
        <XAxis dataKey="fy" tick={a.tick} stroke={p.grid} />
        <YAxis tick={a.tick} tickFormatter={short} width={44} stroke={p.grid} />
        <Tooltip formatter={(v, n) => [f(v), String(n)]} {...a.tooltip} cursor={{ fill: p.grid, opacity: 0.4 }} />
        <Legend wrapperStyle={{ fontSize: 12, color: p.text }} />
        <Bar dataKey="Debt" fill={p.down} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="Equity" fill={p.series[0]} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="Cash" fill={p.series[2]} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </Frame>
  );
}

/** Dividends paid each year, with the payout ratio as a line on its own axis. */
export function DividendChart({ years, unit }: { years: Years; unit: string }) {
  const p = palette(useIsDark());
  const a = axes(p);
  const data = byDate(years).map((y) => ({ fy: y.fy, "Dividends paid": y.dividends_paid, "Payout (% of profit)": y.payout_pct }));
  const f = cr(unit);
  return (
    <Frame
      table={<SrTable caption={`Dividends paid (${unit}) and payout ratio`} head={["Year", "Dividends paid", "Payout"]} rows={data.map((d) => [d.fy, f(d["Dividends paid"]), pctFmt(d["Payout (% of profit)"])])} />}
    >
      <ComposedChart accessibilityLayer={false} data={data} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
        {a.grid}
        <XAxis dataKey="fy" tick={a.tick} stroke={p.grid} />
        <YAxis yAxisId="amt" tick={a.tick} tickFormatter={short} width={44} stroke={p.grid} />
        <YAxis yAxisId="pct" orientation="right" tick={a.tick} unit="%" width={44} stroke={p.grid} />
        <Tooltip formatter={(v, n) => [String(n).startsWith("Payout") ? pctFmt(v) : f(v), String(n)]} {...a.tooltip} cursor={{ fill: p.grid, opacity: 0.4 }} />
        <Legend wrapperStyle={{ fontSize: 12, color: p.text }} />
        <Bar yAxisId="amt" dataKey="Dividends paid" fill={p.series[1]} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        <Line yAxisId="pct" dataKey="Payout (% of profit)" stroke={p.series[0]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} connectNulls />
      </ComposedChart>
    </Frame>
  );
}
