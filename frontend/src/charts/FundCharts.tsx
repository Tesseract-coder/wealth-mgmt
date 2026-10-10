import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { chartApi, type FundChart } from "../api/client";
import { Alert, Card } from "../components/ui";
import { formatDate } from "../lib/format";
import { ComparisonLine } from "./PortfolioCharts";

const YEARS = [1, 3, 5, 10];

export function FundCharts({ code }: { code: string }) {
  const [years, setYears] = useState(5);
  const q = useQuery({ queryKey: ["mf-chart", code, years], queryFn: () => chartApi.fund(code, years) });
  return (
    <Card
      title="NAV vs benchmark"
      actions={
        <div role="group" aria-label="Range" className="inline-flex overflow-hidden rounded border border-slate-300 text-sm dark:border-slate-700">
          {YEARS.map((y) => (
            <button
              key={y}
              type="button"
              aria-pressed={years === y}
              onClick={() => setYears(y)}
              className={`px-2 py-1 ${years === y ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}
            >
              {y}Y
            </button>
          ))}
        </div>
      }
    >
      {q.isError ? <Alert tone="error">{q.error.message}</Alert> : !q.data ? <p className="text-sm text-slate-500">Loading…</p> : <FundChartsBody c={q.data} />}
    </Card>
  );
}

export function FundChartsBody({ c }: { c: FundChart }) {
  if (c.fund.length === 0) return <p className="text-sm text-slate-500">{c.notes.join(". ")}. Run Refresh now in Settings → Data refresh.</p>;
  const last = c.fund.length - 1;
  const benchLast = c.bench[last];
  const label = c.benchmark?.label ?? "Benchmark";
  return (
    <div className="space-y-6">
      <div>
        <ComparisonLine
          dates={c.dates}
          series={[
            { name: "Fund", values: c.fund },
            ...(c.benchmark ? [{ name: label, values: c.bench, dashed: true }] : []),
          ]}
        />
        <p className="mt-1 text-sm">
          Growth of 100 since {formatDate(c.dates[0])}: fund {c.fund[last]?.toFixed(1)}
          {benchLast != null && `, ${label} ${benchLast.toFixed(1)}`}.
        </p>
      </div>
      {c.rolling.map((r) => {
        const ex = r.fund.map((f, i) => +(f - (r.benchmark[i] ?? 0)).toFixed(2));
        const beat = ex.filter((x) => x > 0).length;
        return (
          <div key={r.years}>
            <h3 className="mb-1 text-sm font-semibold">
              Rolling {r.years}-year returns (CAGR, % a year) by window start
            </h3>
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
            <p className="mt-1 text-sm">
              Beat {label} in {beat} of {ex.length} windows ({Math.round((beat / ex.length) * 100)}%); excess ranged {Math.min(...ex).toFixed(1)} to{" "}
              {Math.max(...ex).toFixed(1)} pp.
            </p>
          </div>
        );
      })}
      {c.rolling.length === 0 && c.benchmark && <p className="text-sm text-slate-500">Not enough shared history for rolling returns yet.</p>}
      <ul className="space-y-0.5 text-xs text-slate-500">
        {c.notes.map((n) => (
          <li key={n}>{n}.</li>
        ))}
      </ul>
    </div>
  );
}
