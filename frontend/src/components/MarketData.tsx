import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { isActive, marketApi, type Freshness, type FreshnessStatus, type Job, type Quote, type Schedule } from "../api/client";
import { formatDate, formatFreshness, formatINR, formatNumber, formatPct } from "../lib/format";
import { Alert, Button, Card, ErrorState, SkeletonCard } from "./ui";
import { invalidateData } from "../lib/queries";

const BADGE: Record<FreshnessStatus, string> = {
  fresh: "border border-good-border bg-good-soft text-good",
  stale: "border border-caution-border bg-caution-soft text-caution",
  unavailable: "border border-neutral-border bg-neutral-soft text-neutral",
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
      void invalidateData(qc);
      setJobId(null);
    }
  }, [finished, qc]);

  const refresh = useMutation({
    mutationFn: (force: boolean) => marketApi.refresh("all", force),
    onSuccess: (j) => setJobId(j.id),
  });
  const [fundJobId, setFundJobId] = useState<number | null>(null);
  const lastFund = status.data?.last_fundamentals_job;
  const fundTracked = fundJobId ?? (isActive(lastFund) ? (lastFund?.id ?? null) : null);
  const fundJob = useQuery({
    queryKey: ["job", fundTracked],
    queryFn: () => marketApi.job(fundTracked as number),
    enabled: fundTracked !== null,
    refetchInterval: (q) => (isActive(q.state.data) || !q.state.data ? 2000 : false),
  });
  const refreshFund = useMutation({
    mutationFn: () => marketApi.refresh("fundamentals"),
    onSuccess: (j) => setFundJobId(j.id),
  });
  const fundRunning = isActive(fundJob.data) || refreshFund.isPending;
  const shownFund: Job | null | undefined = fundJob.data ?? lastFund;

  if (status.isError) return <ErrorState title="Couldn't load the market data status" detail={status.error.message} onRetry={() => void status.refetch()} />;
  if (!status.data) return <SkeletonCard label="market data" lines={6} />;
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
          <Button
            variant="secondary"
            disabled={fundRunning}
            title="Your holdings' fundamentals plus sector peers for medians. Can take 10–30 minutes the first time."
            onClick={() => refreshFund.mutate()}
          >
            {fundRunning ? "Fetching fundamentals…" : "Refresh fundamentals + peers"}
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
      </div>
      <ScheduleInfo schedule={s.schedule} />

      {refresh.isError && <Alert tone="error">{refresh.error.message}</Alert>}
      {shownJob && <JobLine job={shownJob} />}
      {shownFund && <JobLine job={shownFund} title="Fundamentals" />}
      {refreshFund.isError && <Alert tone="error">{refreshFund.error.message}</Alert>}

      {(["benchmark", "stock", "mf"] as const).map((kind) => {
        const rows = s.quotes.filter((q) => q.kind === kind);
        if (rows.length === 0) return null;
        return (
          <div key={kind} className="mt-4 overflow-x-auto">
            <h3 className="mb-1 text-sm font-semibold">{KIND_LABEL[kind]}</h3>
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-fg-subtle">
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
                  <tr key={q.code} className="border-t border-border align-top">
                    <td className="py-1 pr-2">{q.label}</td>
                    <td className="pr-2 font-mono text-xs">{q.code}</td>
                    <td className="pr-2 text-right tabular-nums">{price(q)}</td>
                    <td
                      className={`pr-2 text-right tabular-nums ${
                        (q.change_pct ?? 0) > 0 ? "text-good" : (q.change_pct ?? 0) < 0 ? "text-bad" : ""
                      }`}
                    >
                      {formatPct(q.change_pct)}
                    </td>
                    <td className="pr-2 whitespace-nowrap">{formatDate(q.as_of)}</td>
                    <td>
                      <FreshnessBadge f={q.freshness} />
                      {q.freshness.status !== "fresh" && (
                        <div className="text-xs text-fg-subtle">{q.freshness.reason}</div>
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
              <tr key={r.key} className="border-t border-border align-top">
                <td className="py-1 pr-2">{r.label}</td>
                <td className="pr-2 text-fg-subtle">{r.origin === "bundled" ? "bundled copy" : "downloaded"}</td>
                <td className="pr-2 whitespace-nowrap">{formatDate(r.as_of)}</td>
                <td>
                  <FreshnessBadge f={r.freshness} />
                  {r.freshness.status !== "fresh" && <div className="text-xs text-fg-subtle">{r.freshness.reason}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="mt-3 list-disc pl-5 text-xs text-fg-subtle">
        {s.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </Card>
  );
}

function JobLine({ job, title = "Last refresh" }: { job: Job; title?: string }) {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  const when = job.finished_at ?? job.started_at ?? job.created_at;
  return (
    <div className="mb-2 text-sm">
      {isActive(job) ? (
        <div>
          <div className="mb-1">
            {job.message ?? "Queued"} ({job.done}/{job.total})
          </div>
          <div className="h-2 w-full rounded bg-surface-3" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-2 rounded bg-accent" style={{ width: `${pct}%` }} />
          </div>
        </div>
      ) : (
        <div className="text-fg-muted">
          {title} ({job.trigger}) {job.status === "failed" ? "failed" : "finished"} {formatFreshness(new Date(when))}:{" "}
          {job.message}
        </div>
      )}
      {job.errors.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-caution">{job.errors.length} item(s) could not be refreshed</summary>
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

/** The refresh schedule with each job's next run, in IST. */
export function ScheduleInfo({ schedule }: { schedule: Schedule }) {
  if (!schedule.enabled) {
    return (
      <p className="mb-3 text-sm text-fg-subtle">
        Automatic refresh is off (<code>SCHEDULER_ENABLED=false</code>). Use the buttons above to refresh.
      </p>
    );
  }
  const next = new Map((schedule.jobs ?? []).map((j) => [j.id, j.next_run]));
  const rows: [string, string, string | null | undefined][] = [
    ["prices", `Prices and signals: ${schedule.prices}`, next.get("prices")],
    ["navs", `Mutual fund NAVs: ${schedule.navs}`, next.get("navs")],
    ["fundamentals", `Fundamentals: ${schedule.fundamentals}`, next.get("fundamentals")],
  ];
  return (
    <div className="mb-3 text-sm">
      <h3 className="font-medium">Automatic refresh</h3>
      <ul className="mt-1 space-y-0.5 text-fg-muted">
        {rows.map(([id, text, at]) => (
          <li key={id}>
            {text}
            {at ? ` · next ${formatFreshness(new Date(at))}` : ""}
            {id === "prices" && schedule.sheets_auto_export ? " · then exports to Google Sheets" : ""}
          </li>
        ))}
      </ul>
      {schedule.note && <p className="mt-1 text-xs text-fg-subtle">{schedule.note}</p>}
    </div>
  );
}
