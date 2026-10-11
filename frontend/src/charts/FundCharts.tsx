import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { chartApi, type FundChart } from "../api/client";
import { ChartCaption } from "../components/analysis";
import { Card, ErrorState, Loading, Segmented, Skeleton } from "../components/ui";
import { formatDate, formatPct } from "../lib/format";
import { ComparisonLine } from "./PortfolioCharts";

const YEARS = ["1", "3", "5", "10"] as const;

/** Fall from the running peak at each point, in % (0 at a new high). */
export function drawdowns(values: (number | null)[]): (number | null)[] {
  let peak = -Infinity;
  return values.map((v) => {
    if (v === null) return null;
    peak = Math.max(peak, v);
    return +((v / peak - 1) * 100).toFixed(2);
  });
}

export function FundCharts({ code }: { code: string }) {
  const [years, setYears] = useState<(typeof YEARS)[number]>("5");
  const q = useQuery({ queryKey: ["mf-chart", code, Number(years)], queryFn: () => chartApi.fund(code, Number(years)) });
  return (
    <Card
      title="NAV vs benchmark"
      description="Growth of ₹100, rolling returns and falls from the peak"
      actions={<Segmented label="Range" value={years} onChange={setYears} options={YEARS.map((y) => ({ value: y, label: `${y}Y` }))} />}
    >
      {q.isError ? (
        <ErrorState title="Couldn't load the NAV history" detail={q.error.message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <Loading label="the NAV chart">
          <Skeleton className="h-60 w-full" />
        </Loading>
      ) : (
        <FundChartsBody c={q.data} />
      )}
    </Card>
  );
}

export function FundChartsBody({ c }: { c: FundChart }) {
  if (c.fund.length === 0) return <p className="text-sm text-fg-muted">{c.notes.join(". ")}. Run Refresh now in Settings → Data refresh.</p>;
  const last = c.fund.length - 1;
  const benchLast = c.bench[last];
  const label = c.benchmark?.label ?? "Benchmark";
  const ddFund = drawdowns(c.fund);
  const ddBench = drawdowns(c.bench);
  const worst = (xs: (number | null)[]) => Math.min(...xs.filter((x): x is number => x !== null));
  const fundWorst = worst(ddFund);
  const benchWorst = c.benchmark ? worst(ddBench) : null;
  return (
    <div className="space-y-8">
      <figure aria-label={`Line chart of the fund's NAV against ${label}, as growth of 100`}>
        <ComparisonLine
          dates={c.dates}
          series={[
            { name: "Fund", values: c.fund },
            ...(c.benchmark ? [{ name: label, values: c.bench, dashed: true }] : []),
          ]}
        />
        <ChartCaption>
          ₹100 invested on {formatDate(c.dates[0])} is now ₹{c.fund[last]?.toFixed(1)} in the fund
          {benchLast != null ? ` and ₹${benchLast.toFixed(1)} in ${label}: the fund is ${(c.fund[last] ?? 0) >= benchLast ? "ahead" : "behind"}.` : "."}
        </ChartCaption>
      </figure>

      {c.rolling.map((r) => {
        const ex = r.fund.map((f, i) => +(f - (r.benchmark[i] ?? 0)).toFixed(2));
        const beat = ex.filter((x) => x > 0).length;
        return (
          <figure key={r.years} aria-label={`Line chart of rolling ${r.years}-year returns for the fund and ${label}`}>
            <h3 className="mb-1 text-sm font-semibold text-fg">Rolling {r.years}-year returns (% a year) by start date</h3>
            <ComparisonLine
              dates={r.starts}
              unit="%"
              height={200}
              zeroLine
              series={[
                { name: "Fund", values: r.fund },
                { name: label, values: r.benchmark, dashed: true },
              ]}
            />
            <ChartCaption>
              Beat {label} in {beat} of {ex.length} {r.years}-year windows ({Math.round((beat / ex.length) * 100)}%); the gap ranged from {formatPct(Math.min(...ex)).replace("%", " pp")} to{" "}
              {formatPct(Math.max(...ex)).replace("%", " pp")}.
            </ChartCaption>
          </figure>
        );
      })}
      {c.rolling.length === 0 && c.benchmark && <p className="text-sm text-fg-muted">Not enough shared history for rolling returns yet.</p>}

      <figure aria-label={`Line chart of how far the fund and ${label} fell from their peaks`}>
        <h3 className="mb-1 text-sm font-semibold text-fg">Falls from the peak (drawdown)</h3>
        <ComparisonLine
          dates={c.dates}
          unit="%"
          height={180}
          series={[{ name: "Fund", values: ddFund }, ...(c.benchmark ? [{ name: label, values: ddBench, dashed: true }] : [])]}
        />
        <ChartCaption>
          The fund's worst fall in this period was {formatPct(fundWorst)}
          {benchWorst !== null ? `, against ${formatPct(benchWorst)} for ${label}: ${fundWorst >= benchWorst ? "a smoother ride" : "a bumpier ride"}.` : "."}
        </ChartCaption>
      </figure>

      <ul className="space-y-0.5 text-xs text-fg-subtle">
        {c.notes.map((n) => (
          <li key={n}>{n}.</li>
        ))}
      </ul>
    </div>
  );
}
