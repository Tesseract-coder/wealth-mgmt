import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { isActive, marketApi, type Freshness, type FreshnessStatus, type Job, type Quote } from "../api/client";
import { formatDate, formatFreshness, formatINR, formatNumber, formatPct } from "../lib/format";
import { Alert, Button, Card } from "./ui";

const BADGE: Record<FreshnessStatus, string> = {
  fresh: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  stale: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-300",
  unavailable: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

const LABEL: Record<FreshnessStatus, string> = { fresh: "Fresh", stale: "Stale", unavailable: "Unavailable" };

export function FreshnessBadge({ f }: { f: Freshness }) {
  return (
    <span title={f.reason} className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${BADGE[f.status]}`}>
      {LABEL[f.status]}
    </span>
  );
}

const KIND_LABEL: Record<Quote["kind"], string> = { benchmark: "Benchmarks", stock: "Stocks", mf: "Mutual funds" };

function price(q: Quote): string {
  if (q.kind === "benchmark") return formatNumber(q.price);
  return formatINR(q.price, q.kind === "mf" ? 4 : 2);
}

/** Data freshness overview: every holding's latest price/NAV, the reference lists, and a refresh button. */
export function MarketData() {
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const status = useQuery({ queryKey: ["market-status"], queryFn: marketApi.status });

  const lastJob = status.data?.last_job;
  const trackedId = jobId ?? (isActive(lastJob) ? (lastJob?.id ?? null) : null);
  const job = useQuery({
    queryKey: ["job", trackedId],
    queryFn: () => marketApi.job(trackedId as number),
    enabled: trackedId !== null,
    refetchInterval: (q) => (isActive(q.state.data) || !q.state.data ? 1000 : false),
  });

  const finished = job.data && !isActive(job.data);
  useEffect(() => {
    if (finished) {
      void qc.invalidateQueries({ queryKey: ["market-status"] });
      setJobId(null);
    }
  }, [finished, qc]);

  const refresh = useMutation({
    mutationFn: (force: boolean) => marketApi.refresh("all", force),
    onSuccess: (j) => setJobId(j.id),
  });

  if (status.isError) return <Alert tone="error">Could not load market data status: {status.error.message}</Alert>;
  if (!status.data) return <Card title="Market data">Loading…</Card>;
  const s = status.data;
  const running = isActive(job.data) || refresh.isPending;
  const shownJob: Job | null | undefined = job.data ?? lastJob;

  return (
    <Card
      title="Market data"
      actions={
        <div className="flex gap-2">
          <Button disabled={running} onClick={() => refresh.mutate(false)}>
            {running ? "Refreshing…" : "Refresh now"}
          </Button>
          <Button
            variant="secondary"
            disabled={running}
            title="Re-download everything, even data that is already fresh"
            onClick={() => refresh.mutate(true)}
          >
            Force re-download
          </Button>
        </div>
      }
    >
      <div className="mb-3 flex flex-wrap gap-3 text-sm" aria-label="Freshness summary">
        {(["fresh", "stale", "unavailable"] as const).map((k) => (
          <span key={k}>
            <FreshnessBadge f={{ status: k, reason: LABEL[k] }} /> {s.summary[k]}
          </span>
        ))}
        <span className="text-slate-500">
          {s.schedule.enabled
            ? `Auto-refresh: prices ${s.schedule.prices}, NAVs ${s.schedule.navs}`
            : "Auto-refresh is off"}
        </span>
      </div>

      {refresh.isError && <Alert tone="error">{refresh.error.message}</Alert>}
      {shownJob && <JobLine job={shownJob} />}

      {(["benchmark", "stock", "mf"] as const).map((kind) => {
        const rows = s.quotes.filter((q) => q.kind === kind);
        if (rows.length === 0) return null;
        return (
          <div key={kind} className="mt-4 overflow-x-auto">
            <h3 className="mb-1 text-sm font-semibold">{KIND_LABEL[kind]}</h3>
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-1 pr-2">Name</th>
                  <th className="pr-2">Code</th>
                  <th className="pr-2 text-right">{kind === "mf" ? "NAV" : "Close"}</th>
                  <th className="pr-2 text-right">Change</th>
                  <th className="pr-2">As of</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((q) => (
                  <tr key={q.code} className="border-t border-slate-100 align-top dark:border-slate-800">
                    <td className="py-1 pr-2">{q.label}</td>
                    <td className="pr-2 font-mono text-xs">{q.code}</td>
                    <td className="pr-2 text-right tabular-nums">{price(q)}</td>
                    <td
                      className={`pr-2 text-right tabular-nums ${
                        (q.change_pct ?? 0) > 0 ? "text-emerald-700 dark:text-emerald-400" : (q.change_pct ?? 0) < 0 ? "text-red-700 dark:text-red-400" : ""
                      }`}
                    >
                      {formatPct(q.change_pct)}
                    </td>
                    <td className="pr-2 whitespace-nowrap">{formatDate(q.as_of)}</td>
                    <td>
                      <FreshnessBadge f={q.freshness} />
                      {q.freshness.status !== "fresh" && (
                        <div className="text-xs text-slate-500">{q.freshness.reason}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}

      <div className="mt-4 overflow-x-auto">
        <h3 className="mb-1 text-sm font-semibold">Reference lists</h3>
        <table className="w-full text-sm">
          <tbody>
            {s.references.map((r) => (
              <tr key={r.key} className="border-t border-slate-100 align-top dark:border-slate-800">
                <td className="py-1 pr-2">{r.label}</td>
                <td className="pr-2 text-slate-500">{r.origin === "bundled" ? "bundled copy" : "downloaded"}</td>
                <td className="pr-2 whitespace-nowrap">{formatDate(r.as_of)}</td>
                <td>
                  <FreshnessBadge f={r.freshness} />
                  {r.freshness.status !== "fresh" && <div className="text-xs text-slate-500">{r.freshness.reason}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="mt-3 list-disc pl-5 text-xs text-slate-500">
        {s.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </Card>
  );
}

function JobLine({ job }: { job: Job }) {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  const when = job.finished_at ?? job.started_at ?? job.created_at;
  return (
    <div className="mb-2 text-sm">
      {isActive(job) ? (
        <div>
          <div className="mb-1">
            {job.message ?? "Queued"} ({job.done}/{job.total})
          </div>
          <div className="h-2 w-full rounded bg-slate-200 dark:bg-slate-800" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-2 rounded bg-slate-700 dark:bg-slate-300" style={{ width: `${pct}%` }} />
          </div>
        </div>
      ) : (
        <div className="text-slate-600 dark:text-slate-400">
          Last refresh ({job.trigger}) {job.status === "failed" ? "failed" : "finished"} {formatFreshness(new Date(when))}:{" "}
          {job.message}
        </div>
      )}
      {job.errors.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-amber-800 dark:text-amber-300">{job.errors.length} item(s) could not be refreshed</summary>
          <ul className="list-disc pl-5 text-xs">
            {job.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
