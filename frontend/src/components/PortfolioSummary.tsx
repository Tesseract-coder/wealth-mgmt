import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { summaryApi, type HoldingsChecks, type PortfolioSummary } from "../api/client";
import { AllocationDonut, ComparisonLine, SectorBars } from "../charts/PortfolioCharts";
import { formatDate, formatINR, formatINRCompact, formatPct } from "../lib/format";
import { axesFromPortfolio, ChartCaption, ScoreShape } from "./analysis";
import { Alert, Card, Delta, Disclosure, EmptyState, ErrorState, Loading, Segmented, Skeleton, SkeletonText, Stat } from "./ui";

export function PortfolioSummaryCard({ sectorLimit }: { sectorLimit?: number | null }) {
  const q = useQuery({ queryKey: ["portfolio-summary"], queryFn: summaryApi.get });
  if (q.isError) return <ErrorState title="Couldn't load the portfolio summary" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SummarySkeleton />;
  return <PortfolioSummaryBody s={q.data} sectorLimit={sectorLimit} />;
}

export function SummarySkeleton() {
  return (
    <Loading label="your portfolio">
      <div className="grid gap-6 rounded-card border border-border bg-surface p-5 md:grid-cols-[minmax(0,22rem)_1fr]">
        <Skeleton className="mx-auto aspect-[6/5] w-full max-w-80" />
        <SkeletonText lines={6} />
      </div>
    </Loading>
  );
}

export function NoHoldings() {
  return (
    <EmptyState
      title="No holdings yet"
      action={
        <Link to="/import" className="text-sm font-medium text-accent-text underline">
          Import your Groww files
        </Link>
      }
    >
      Import your Groww holdings to see your portfolio score, signals and what needs attention.
    </EmptyState>
  );
}

/**
 * The hero row: the portfolio's Score Shape (stocks, value-weighted) beside value, invested,
 * unrealised P&L, XIRR and the day's change.
 */
export function PortfolioHero({ s, shape, shapeLoading = false }: { s: PortfolioSummary; shape?: HoldingsChecks; shapeLoading?: boolean }) {
  const p = shape?.portfolio;
  return (
    <section aria-label="Portfolio" className="rounded-card border border-border bg-surface p-4 shadow-card sm:p-6">
      <div className="grid items-center gap-6 md:grid-cols-[minmax(0,22rem)_1fr]">
        <div className="flex flex-col items-center">
          {p && p.holdings > 0 ? (
            <>
              <ScoreShape axes={axesFromPortfolio(p)} total={p.total} maxTotal={p.max_total} step={p.step} size="lg" name="your stocks" style={shape.style} />
              <p className="mt-1 text-center text-xs text-fg-subtle">
                Your {p.holdings} stocks ({formatINRCompact(p.stock_value)}), weighted by value
              </p>
            </>
          ) : shapeLoading ? (
            <Skeleton className="aspect-[6/5] w-full max-w-80" />
          ) : (
            <p className="text-sm text-fg-muted">No stocks to score: the portfolio shape covers stocks only.</p>
          )}
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-fg-muted">Total value</p>
          <p className="text-2xl font-semibold text-fg">{formatINR(s.total_value, 0)}</p>
          <p className="text-xs text-fg-subtle">
            Stocks {formatINR(s.stock_value, 0)} · funds {formatINR(s.fund_value, 0)}
          </p>
          <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-5 lg:grid-cols-4">
            <Stat label="Invested" value={formatINR(s.invested, 0)} hint={s.invested_note ? "partly unknown" : undefined} />
            <Stat label="Unrealised P&L" value={<Delta value={s.pnl} format="inr" />} hint={formatPct(s.pnl_pct)} />
            <Stat
              label="Day change"
              value={<Delta value={s.day_change} format="inr" />}
              hint={formatPct(s.day_change_pct)}
              help="Today's change in value from the last two closes of each holding."
            />
            <Stat
              label="XIRR"
              value={s.xirr == null ? "—" : formatPct(s.xirr)}
              hint={s.xirr == null ? "needs purchase dates" : `covers ${Math.round(s.xirr_coverage * 100)}% of the value`}
              help="Your yearly return, allowing for when each rupee went in."
            />
          </dl>
          <p className="mt-4 text-xs text-fg-subtle">{s.as_of ? `Prices as of ${formatDate(s.as_of)}.` : "No prices yet."}</p>
          <ul className="mt-1 space-y-0.5 text-xs text-fg-subtle">
            {[s.invested_note, s.day_change_note, `XIRR: ${s.xirr_basis.replace(/\.$/, "")}.`].filter(Boolean).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

const DIMENSIONS = [
  { value: "by_sector", label: "Sector" },
  { value: "by_holding", label: "Holding" },
  { value: "by_asset_class", label: "Asset class" },
  { value: "by_mcap", label: "Market cap" },
] as const;
type Dim = (typeof DIMENSIONS)[number]["value"];

function allocationCaption(s: PortfolioSummary, dim: Dim, sectorLimit: number | null): string {
  // Buckets that aren't a real sector (e.g. "Mutual funds (not split by sector)") don't count.
  const top = s[dim].find((x) => x.limited !== false);
  if (!top) return "No holdings to break down.";
  const what = DIMENSIONS.find((d) => d.value === dim)!.label.toLowerCase();
  const share = `${(top.weight * 100).toFixed(1)}%`;
  if (dim === "by_sector" && sectorLimit !== null)
    return `Your biggest sector is ${top.label} at ${share} of the portfolio, ${top.weight > sectorLimit ? "above" : "within"} your ${Math.round(sectorLimit * 100)}% limit.`;
  return `Your biggest ${what} is ${top.label} at ${share} of the portfolio, across ${s[dim].length} in all.`;
}

function performanceCaption(s: PortfolioSummary): string {
  const last = s.performance_portfolio.length - 1;
  const port = (s.performance_portfolio[last] ?? 100) - 100;
  const nifty = (s.performance_nifty[last] ?? 100) - 100;
  const gap = port - nifty;
  const verdict = Math.abs(gap) < 0.05 ? "level with it" : `${gap > 0 ? "ahead" : "behind"} by ${Math.abs(gap).toFixed(1)} pp`;
  return `Since ${formatDate(s.performance_dates[0])}: portfolio ${formatPct(port)}, Nifty 50 ${formatPct(nifty)}, so you're ${verdict}.`;
}

/** Allocation donut and value against the Nifty 50, each with a caption; the rest in an expander. */
export function PortfolioCharts({ s, sectorLimit }: { s: PortfolioSummary; sectorLimit?: number | null }) {
  const [dim, setDim] = useState<Dim>("by_sector");
  const label = DIMENSIONS.find((d) => d.value === dim)!.label;
  const last = s.performance_portfolio.length - 1;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Allocation" actions={<Segmented label="Allocation by" value={dim} onChange={setDim} options={DIMENSIONS.map((d) => ({ value: d.value, label: d.label }))} />}>
          <AllocationDonut items={s[dim]} title={`By ${label.toLowerCase()}`} />
          <p className="mt-2 text-sm text-fg-muted">{allocationCaption(s, dim, sectorLimit ?? null)}</p>
        </Card>
        <Card title="Value vs Nifty 50" description="Growth of ₹100 in your current holdings, held unchanged">
          {last > 0 ? (
            <figure aria-label="Line chart of the portfolio's value against the Nifty 50">
              <ComparisonLine
                dates={s.performance_dates}
                series={[
                  { name: "Portfolio", values: s.performance_portfolio },
                  { name: "Nifty 50", values: s.performance_nifty, dashed: true },
                ]}
              />
              <ChartCaption source={s.performance_basis}>{performanceCaption(s)}</ChartCaption>
            </figure>
          ) : (
            <p className="text-sm text-fg-muted">Not enough price history yet. Run Refresh now in Settings.</p>
          )}
        </Card>
      </div>
      <Disclosure summary="Sector limits, beta and correlation">
        <div className="grid gap-6 lg:grid-cols-2">
          <SectorBars items={s.by_sector} limit={sectorLimit ?? null} />
          <div className="space-y-4 text-sm">
            <p className="text-fg">
              Portfolio beta {s.beta?.toFixed(2) ?? "—"} <span className="text-xs text-fg-subtle">({s.beta_basis})</span>
            </p>
            {s.correlation_labels.length > 1 && <Correlation s={s} />}
            {s.notes.map((n) => (
              <p key={n} className="text-xs text-fg-subtle">
                {n}
              </p>
            ))}
          </div>
        </div>
      </Disclosure>
    </div>
  );
}

function Correlation({ s }: { s: PortfolioSummary }) {
  return (
    <div className="overflow-x-auto">
      <h3 className="mb-1 text-sm font-semibold text-fg">Correlation of top holdings</h3>
      <table className="text-xs">
        <thead>
          <tr>
            <th />
            {s.correlation_labels.map((l, i) => (
              <th key={l} className="px-1 font-normal text-fg-subtle" title={l}>
                {i + 1}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {s.correlation.map((row, i) => (
            <tr key={s.correlation_labels[i]}>
              <th className="max-w-48 truncate pr-2 text-left font-normal text-fg-muted" title={s.correlation_labels[i]}>
                {i + 1}. {s.correlation_labels[i]}
              </th>
              {row.map((v, j) => (
                <td
                  key={j}
                  className="px-1 text-center text-fg"
                  style={v !== null && i !== j ? { backgroundColor: `color-mix(in srgb, var(--bad) ${Math.round(Math.max(0, v) * 45)}%, transparent)` } : undefined}
                >
                  {v === null ? "" : v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-xs text-fg-subtle">{s.correlation_basis}. Values near 1 move together; shading is darker the closer to 1.</p>
    </div>
  );
}

/** Hero, warnings and charts together (the Overview lays them out with other sections between). */
export function PortfolioSummaryBody({ s, sectorLimit, shape }: { s: PortfolioSummary; sectorLimit?: number | null; shape?: HoldingsChecks }) {
  if (s.total_value <= 0) return <NoHoldings />;
  return (
    <div className="space-y-4">
      <PortfolioHero s={s} shape={shape} />
      {s.warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      <PortfolioCharts s={s} sectorLimit={sectorLimit} />
    </div>
  );
}
