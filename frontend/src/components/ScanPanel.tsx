import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { isActive, marketApi, screenerApi, type Job, type Scan, type ScreenerConfig, type UniverseKey } from "../api/client";
import { formatFreshness } from "../lib/format";
import { Alert, Button, Card, inputClass } from "./ui";

/** Rough first-scan duration, from the backend's per-stock estimate (rate limits + pause). */
export const scanMinutes = (stocks: number, secondsPerStock: number): number =>
  stocks > 0 ? Math.max(1, Math.round((stocks * secondsPerStock) / 60)) : 0;

export function ScanSummary({ scan }: { scan: Scan }) {
  return (
    <div className="text-sm">
      <p>
        <span className="font-medium">{scan.universe_label}</span> · {scan.style_label} · {scan.risk_label} risk ·{" "}
        {scan.scored} of {scan.total} scored · {formatFreshness(new Date(scan.finished_at ?? scan.created_at))}
        {scan.fetch === "cached" && " · cached data only"}
      </p>
      {scan.status === "partial" && <p className="text-amber-800 dark:text-amber-300">This scan was stopped early and covers part of the universe.</p>}
      {scan.notes.map((n) => (
        <p key={n} className="text-xs text-slate-500">
          {n}
        </p>
      ))}
    </div>
  );
}

export function ScanProgress({ job, onStop, stopping, label }: { job: Job; onStop: () => void; stopping: boolean; label?: string }) {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  return (
    <div className="space-y-1 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          {label && <span className="font-medium">Scanning {label} · </span>}
          {job.message ?? "Queued"} · {pct}%
        </span>
        <Button variant="danger" onClick={onStop} disabled={stopping}>
          {stopping ? "Stopping…" : "Stop"}
        </Button>
      </div>
      <div className="h-2 w-full rounded bg-slate-200 dark:bg-slate-800" role="progressbar" aria-label="Scan progress" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-2 rounded bg-slate-700 transition-all dark:bg-slate-300" style={{ width: `${pct}%` }} />
      </div>
      {job.errors.length > 0 && <p className="text-xs text-amber-800 dark:text-amber-300">{job.errors.length} stock(s) could not be downloaded so far.</p>}
    </div>
  );
}

/** Universe + data mode + Run, the running job's progress, and the last scan. */
export function ScanPanel({ config }: { config: ScreenerConfig }) {
  const qc = useQueryClient();
  const last = config.universes.find((u) => u.key === config.latest_scan?.universe && u.key !== "custom");
  const [universe, setUniverse] = useState<UniverseKey>(last?.key ?? config.default_universe);
  const [symbols, setSymbols] = useState("");
  const [fetchMode, setFetchMode] = useState<"missing" | "cached">("missing");
  const [jobId, setJobId] = useState<number | null>(null);
  const active = useQuery({ queryKey: ["screener-active"], queryFn: screenerApi.active });
  const tracked = jobId ?? active.data?.job.id ?? null;
  const job = useQuery({
    queryKey: ["screener-job", tracked],
    queryFn: () => screenerApi.job(tracked!),
    enabled: tracked !== null,
    refetchInterval: (q) => (!q.state.data || isActive(q.state.data.job) ? 1500 : false),
  });
  const run = useMutation({
    mutationFn: () => screenerApi.run({ universe, fetch: fetchMode, symbols: universe === "custom" ? symbols : undefined }),
    onSuccess: (r) => setJobId(r.job.id),
  });
  const stop = useMutation({ mutationFn: (id: number) => marketApi.cancel(id) });
  const running = isActive(job.data?.job) || run.isPending;
  const runningUniverse = running ? (job.data?.job.params.universe as UniverseKey | undefined) : undefined;
  const finishedId = job.data && !isActive(job.data.job) ? job.data.job.id : null;

  useEffect(() => {
    if (finishedId === null) return;
    void qc.invalidateQueries({ queryKey: ["screener-config"] });
    void qc.invalidateQueries({ queryKey: ["screen"] });
    void qc.invalidateQueries({ queryKey: ["screener-active"] });
    stop.reset();
    // Once per finished job; the other values are read at that moment on purpose.
  }, [finishedId]);

  const size = config.universes.find((u) => u.key === universe)?.size;
  const customCount = symbols.split(/[\s,]+/).filter(Boolean).length;
  const n = universe === "custom" ? customCount : (size ?? 0);
  const firstRunMinutes = scanMinutes(n, config.seconds_per_stock);
  return (
    <Card title="Scan">
      <div className="space-y-3">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label>
            <span className="mb-1 block text-slate-500">Universe</span>
            <select className={inputClass} value={runningUniverse ?? universe} disabled={running} onChange={(e) => setUniverse(e.target.value as UniverseKey)}>
              {config.universes.map((u) => (
                <option key={u.key} value={u.key}>
                  {u.label}
                  {u.size ? ` (${u.size})` : ""}
                </option>
              ))}
            </select>
          </label>
          <fieldset disabled={running}>
            <legend className="mb-1 text-slate-500">Data</legend>
            <label className="mr-3">
              <input type="radio" name="fetch" checked={fetchMode === "missing"} onChange={() => setFetchMode("missing")} /> Download what's missing
            </label>
            <label>
              <input type="radio" name="fetch" checked={fetchMode === "cached"} onChange={() => setFetchMode("cached")} /> Cached data only (fast)
            </label>
          </fieldset>
          <Button onClick={() => run.mutate()} disabled={running || (universe === "custom" && customCount === 0)}>
            {running ? "Scanning…" : "Run scan"}
          </Button>
        </div>
        {universe === "custom" && (
          <label className="block text-sm">
            <span className="mb-1 block text-slate-500">
              NSE symbols, separated by commas or new lines ({customCount}/{config.custom_universe_max})
            </span>
            <textarea className={`${inputClass} h-20 font-mono`} value={symbols} disabled={running} onChange={(e) => setSymbols(e.target.value)} placeholder="TCS, INFY, HDFCBANK" />
          </label>
        )}
        {fetchMode === "missing" && !running && (
          <p className="text-xs text-slate-500">
            Downloads prices and fundamentals that aren't cached or are out of date, at the free sources' rate limits
            {firstRunMinutes ? `: a first ${n}-stock scan takes about ${firstRunMinutes} minutes` : ""}. Later scans reuse the cache
            and are much quicker. It runs in the background, so you can leave this page and come back.
          </p>
        )}
        {run.isError && <Alert tone="error">{run.error.message}</Alert>}
        {stop.isError && <Alert tone="error">{stop.error.message}</Alert>}
        {job.data && isActive(job.data.job) ? (
          <ScanProgress
            job={job.data.job}
            label={config.universes.find((u) => u.key === job.data!.job.params.universe)?.label}
            stopping={stop.isPending || stop.isSuccess}
            onStop={() => stop.mutate(job.data!.job.id)}
          />
        ) : job.data?.job.status === "failed" ? (
          <Alert tone="error">The scan failed: {job.data.job.message}</Alert>
        ) : config.latest_scan ? (
          <ScanSummary scan={config.latest_scan} />
        ) : (
          <p className="text-sm text-slate-500">No scan yet. Run one to get ranked ideas.</p>
        )}
      </div>
    </Card>
  );
}
