import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { summaryApi, type PortfolioSummary } from "../api/client";
import { AllocationDonut, ComparisonLine, SectorBars } from "../charts/PortfolioCharts";
import { formatDate, formatINR } from "../lib/format";
import { Alert, Card } from "./ui";

const pct = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`);

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "up" | "down" }) {
  const cls = tone === "up" ? "text-emerald-700 dark:text-emerald-400" : tone === "down" ? "text-red-700 dark:text-red-400" : "";
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${cls}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

const tone = (v: number | null | undefined) => (v == null ? undefined : v >= 0 ? "up" : "down");

export function PortfolioSummaryCard({ sectorLimit }: { sectorLimit?: number | null }) {
  const q = useQuery({ queryKey: ["portfolio-summary"], queryFn: summaryApi.get });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card title="Portfolio">Loading…</Card>;
  return <PortfolioSummaryBody s={q.data} sectorLimit={sectorLimit} />;
}

export function PortfolioSummaryBody({ s, sectorLimit }: { s: PortfolioSummary; sectorLimit?: number | null }) {
  if (s.total_value <= 0)
    return (
      <Alert tone="info">
        No holdings yet. <Link className="underline" to="/import">Import your Groww files</Link> to see your portfolio.
      </Alert>
    );
  const last = s.performance_portfolio.length - 1;
  return (
    <Card title={`Portfolio${s.as_of ? ` · prices as of ${formatDate(s.as_of)}` : ""}`}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Kpi label="Value" value={formatINR(s.total_value, 0)} sub={`stocks ${formatINR(s.stock_value, 0)} · funds ${formatINR(s.fund_value, 0)}`} />
        <Kpi label="Invested" value={formatINR(s.invested, 0)} sub={s.invested_note ? "partly unknown" : undefined} />
        <Kpi label="Unrealised P&L" value={formatINR(s.pnl, 0)} sub={pct(s.pnl_pct)} tone={tone(s.pnl)} />
        <Kpi label="Day change" value={formatINR(s.day_change, 0)} sub={pct(s.day_change_pct, 2)} tone={tone(s.day_change)} />
        <Kpi label="XIRR" value={pct(s.xirr)} sub={s.xirr == null ? "needs dates" : `covers ${Math.round(s.xirr_coverage * 100)}%`} />
      </div>
      <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
        {[s.invested_note, s.day_change_note, `XIRR: ${s.xirr_basis}.`].filter(Boolean).map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      {s.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {s.warnings.map((w) => (
            <li key={w} className="text-amber-800 dark:text-amber-300">
              ⚠ {w}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <AllocationPicker s={s} />
        <SectorBars items={s.by_sector} limit={sectorLimit ?? null} />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="text-sm">
          <h3 className="mb-1 font-semibold">Value vs Nifty 50</h3>
          {last > 0 ? (
            <>
              <ComparisonLine
                dates={s.performance_dates}
                series={[
                  { name: "Portfolio", values: s.performance_portfolio },
                  { name: "Nifty 50", values: s.performance_nifty, dashed: true },
                ]}
              />
              <p className="mt-1">
                Since {formatDate(s.performance_dates[0])}: portfolio {pct((s.performance_portfolio[last] ?? 100) - 100)}, Nifty 50{" "}
                {pct((s.performance_nifty[last] ?? 100) - 100)}
                <span className="block text-xs text-slate-500">Growth of 100. {s.performance_basis}</span>
              </p>
            </>
          ) : (
            <p className="text-slate-500">Not enough price history yet. Run Refresh now in Settings.</p>
          )}
          <p className="mt-3">
            Portfolio beta {s.beta?.toFixed(2) ?? "—"} <span className="text-xs text-slate-500">({s.beta_basis})</span>
          </p>
          {s.notes.map((n) => (
            <p key={n} className="mt-1 text-xs text-slate-500">
              {n}
            </p>
          ))}
        </div>
        {s.correlation_labels.length > 1 && (
          <div className="overflow-x-auto">
            <h3 className="mb-1 text-sm font-semibold">Correlation of top holdings</h3>
            <table className="text-xs">
              <thead>
                <tr>
                  <th />
                  {s.correlation_labels.map((l, i) => (
                    <th key={l} className="px-1 font-normal text-slate-500" title={l}>
                      {i + 1}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {s.correlation.map((row, i) => (
                  <tr key={s.correlation_labels[i]}>
                    <th className="max-w-48 truncate pr-2 text-left font-normal" title={s.correlation_labels[i]}>
                      {i + 1}. {s.correlation_labels[i]}
                    </th>
                    {row.map((v, j) => (
                      <td
                        key={j}
                        className="px-1 text-center tabular-nums"
                        style={v !== null && i !== j ? { backgroundColor: `rgba(220, 38, 38, ${Math.max(0, v) * 0.5})` } : undefined}
                      >
                        {v === null ? "" : v.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-slate-500">{s.correlation_basis}. Values near 1 move together; shading is darker the closer to 1.</p>
          </div>
        )}
      </div>
    </Card>
  );
}

const DIMENSIONS = [
  { key: "by_holding", label: "Holding" },
  { key: "by_asset_class", label: "Asset class" },
  { key: "by_mcap", label: "Market cap" },
] as const;

function AllocationPicker({ s }: { s: PortfolioSummary }) {
  const [dim, setDim] = useState<(typeof DIMENSIONS)[number]["key"]>("by_holding");
  const label = DIMENSIONS.find((d) => d.key === dim)?.label ?? "";
  return (
    <div>
      <div role="tablist" aria-label="Allocation by" className="mb-2 flex gap-1 text-xs">
        {DIMENSIONS.map((d) => (
          <button
            key={d.key}
            type="button"
            role="tab"
            aria-selected={dim === d.key}
            onClick={() => setDim(d.key)}
            className={`rounded px-2 py-1 ${dim === d.key ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "border border-slate-300 dark:border-slate-700"}`}
          >
            {d.label}
          </button>
        ))}
      </div>
      <AllocationDonut items={s[dim]} title={`Allocation by ${label.toLowerCase()}`} />
    </div>
  );
}
