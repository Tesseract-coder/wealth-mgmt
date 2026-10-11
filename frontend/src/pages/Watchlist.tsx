import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { isActive, marketApi, watchlistApi, type WatchItem, type Watchlist as WatchlistData } from "../api/client";
import { FreshnessBadge } from "../components/MarketData";
import { ConfidenceTag, SignalPill } from "../components/SignalView";
import { Alert, Button, Card, inputClass } from "../components/ui";
import { formatDate, formatINR, formatPct } from "../lib/format";

const tone = (v: number | null) =>
  v === null || v === 0 ? "" : v > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400";

function AddForm() {
  const qc = useQueryClient();
  const [ticker, setTicker] = useState("");
  const [note, setNote] = useState("");
  const add = useMutation({
    mutationFn: () => watchlistApi.add(ticker, "Manual", note || undefined),
    onSuccess: () => {
      setTicker("");
      setNote("");
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
      void qc.invalidateQueries({ queryKey: ["watch-tickers"] });
    },
  });
  return (
    <form
      className="flex flex-wrap items-end gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        if (ticker.trim()) add.mutate();
      }}
    >
      <label>
        <span className="mb-1 block text-slate-500">NSE symbol</span>
        <input className={`${inputClass} !w-40`} value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="e.g. TITAN" />
      </label>
      <label className="min-w-48 flex-1">
        <span className="mb-1 block text-slate-500">Note (optional)</span>
        <input className={inputClass} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Why you're watching it" />
      </label>
      <Button type="submit" disabled={add.isPending || !ticker.trim()}>
        Add
      </Button>
      {add.isError && <p className="basis-full text-red-700 dark:text-red-400">{add.error.message}</p>}
    </form>
  );
}

function NoteCell({ w }: { w: WatchItem }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(w.note ?? "");
  const save = useMutation({
    mutationFn: () => watchlistApi.note(w.ticker, text),
    onSuccess: () => {
      setEdit(false);
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
  if (!edit)
    return (
      <div className="max-w-48 text-xs">
        {w.note && <p className="mb-1">{w.note}</p>}
        <button type="button" className="text-slate-500 underline" onClick={() => setEdit(true)}>
          {w.note ? "Edit note" : "Add note"}
        </button>
      </div>
    );
  return (
    <form
      className="flex max-w-56 flex-col gap-1"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <input aria-label={`Note for ${w.label}`} className={inputClass} value={text} maxLength={500} onChange={(e) => setText(e.target.value)} />
      <div className="flex gap-1">
        <Button type="submit" className="!px-2 !py-0.5 text-xs" disabled={save.isPending}>
          Save
        </Button>
        <Button variant="secondary" className="!px-2 !py-0.5 text-xs" onClick={() => setEdit(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Row({ w }: { w: WatchItem }) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: () => watchlistApi.remove(w.ticker),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
      void qc.invalidateQueries({ queryKey: ["watch-tickers"] });
    },
  });
  return (
    <tr className="border-t border-slate-100 align-top dark:border-slate-800">
      <td className="py-1.5 pr-2">
        <Link to={`/analysis/${encodeURIComponent(w.ticker)}`} className="font-medium underline">
          {w.label}
        </Link>
        <div className="font-mono text-xs text-slate-500">
          {w.ticker}
          {w.sector ? ` · ${w.sector}` : ""}
          {w.held ? " · you hold this" : ""}
        </div>
        <div className="text-xs text-slate-500">
          Added {formatDate(w.added_at)}
          {w.source ? ` · ${w.source}` : ""}
        </div>
        {w.status === "ok" && (
          <details className="text-xs">
            <summary className="cursor-pointer text-slate-600 dark:text-slate-400">Why</summary>
            <div className="mt-1 max-w-md space-y-0.5">
              <p>{w.rule}</p>
              {w.bullish.map((r) => (
                <p key={r} className="text-emerald-800 dark:text-emerald-300">
                  ▲ {r}
                </p>
              ))}
              {w.bearish.map((r) => (
                <p key={r} className="text-red-800 dark:text-red-300">
                  ▼ {r}
                </p>
              ))}
              {w.flags.map((f) => (
                <p key={f.key} className="text-amber-800 dark:text-amber-300">
                  ⚠ {f.text}
                </p>
              ))}
            </div>
          </details>
        )}
      </td>
      {w.status === "no_data" ? (
        <td colSpan={5} className="pr-2 text-sm text-slate-500">
          No prices downloaded yet. A download runs in the background; refresh in a minute.
        </td>
      ) : (
        <>
          <td className="pr-2">
            {w.signal && w.signal_label && <SignalPill signal={w.signal} label={w.signal_label} />}
            <div>
              <ConfidenceTag c={w.confidence} />
            </div>
            {w.signal_changed_since_added && w.added_signal_label && (
              <div className="text-xs font-medium text-amber-800 dark:text-amber-300">Was {w.added_signal_label} when added</div>
            )}
          </td>
          <td className="pr-2 text-right tabular-nums">
            <div className="font-semibold">{w.composite?.toFixed(0) ?? "—"}</div>
            {w.score_change !== null && (
              <div className={`text-xs ${tone(w.score_change)}`}>
                {w.score_change > 0 ? "+" : ""}
                {w.score_change.toFixed(1)} since added
              </div>
            )}
          </td>
          <td className="pr-2 text-right tabular-nums whitespace-nowrap">
            <div>{formatINR(w.price)}</div>
            {w.price_change_pct !== null && <div className={`text-xs ${tone(w.price_change_pct)}`}>{formatPct(w.price_change_pct)} since added</div>}
            {w.stop !== null && <div className="text-xs text-slate-500">Stop {formatINR(w.stop)}</div>}
            {w.price_freshness && <FreshnessBadge f={w.price_freshness} />}
          </td>
          <td className="pr-2 text-xs">
            {w.last_change ? (
              <>
                {w.last_change.previous_label} → <span className="font-medium">{w.last_change.current_label}</span>
                <div className="text-slate-500">on {formatDate(w.last_change.day)}</div>
              </>
            ) : (
              <span className="text-slate-500">No change recorded</span>
            )}
          </td>
          <td className="pr-2">
            <NoteCell w={w} />
          </td>
        </>
      )}
      <td>
        <Button variant="secondary" className="!px-2 !py-1 text-xs" aria-label={`Remove ${w.label}`} disabled={remove.isPending} onClick={() => remove.mutate()}>
          Remove
        </Button>
      </td>
    </tr>
  );
}

export function WatchlistTable({ d }: { d: WatchlistData }) {
  if (d.items.length === 0)
    return <Alert tone="info">Nothing on your watchlist yet. Add a symbol above, or press Watch on a Screener idea.</Alert>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-slate-500">
          <tr>
            <th className="py-1 pr-2">Stock</th>
            <th className="pr-2">Signal now</th>
            <th className="pr-2 text-right">Score</th>
            <th className="pr-2 text-right">Price</th>
            <th className="pr-2">Last signal change</th>
            <th className="pr-2">Note</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {d.items.map((w) => (
            <Row key={w.ticker} w={w} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Stocks you're tracking, scored live with your style and risk, and what changed since you added them. */
export function Watchlist() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["watchlist"], queryFn: watchlistApi.list });
  const jobId = q.data?.fetching_job_id ?? null;
  useQuery({
    queryKey: ["watch-fetch", jobId],
    queryFn: async () => {
      const job = await marketApi.job(jobId!);
      if (!isActive(job)) void qc.invalidateQueries({ queryKey: ["watchlist"] });
      return job;
    },
    enabled: jobId !== null,
    refetchInterval: (s) => (s.state.data && !isActive(s.state.data) ? false : 2000),
  });
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Watchlist</h1>
        <p className="text-sm text-slate-500">
          Ideas you're tracking. Scores and signals are recomputed from cached data each time you open this page; the daily
          refresh downloads their prices and records their signals, so changes show with a date.
        </p>
      </div>
      <Card title="Add a stock">
        <AddForm />
      </Card>
      {q.isError ? (
        <Alert tone="error">{q.error.message}</Alert>
      ) : !q.data ? (
        <Card>Scoring your watchlist…</Card>
      ) : (
        <Card title={`${q.data.items.length} stock(s) · ${q.data.style_label} · ${q.data.risk_label} risk`}>
          {jobId !== null && (
            <div className="mb-3">
              <Alert tone="info">Downloading data for newly added stocks…</Alert>
            </div>
          )}
          <WatchlistTable d={q.data} />
        </Card>
      )}
    </div>
  );
}
