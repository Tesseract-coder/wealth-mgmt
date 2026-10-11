import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, CircleAlert, LayoutGrid, Minus, Table2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { isActive, marketApi, watchlistApi, type WatchItem, type WeekChange, type Watchlist as WatchlistData } from "../api/client";
import { AXIS_LABEL, axesFromRecord, ScoreShape, SignalPill } from "../components/analysis";
import { FreshnessBadge } from "../components/MarketData";
import { ConfidenceTag } from "../components/SignalView";
import { Alert, Badge, Button, Card, Disclosure, EmptyState, ErrorState, inputClass, Loading, PageHeader, Segmented, Skeleton } from "../components/ui";
import { formatDate, formatINR, formatPct } from "../lib/format";

const tone = (v: number | null) => (v === null || v === 0 ? "text-fg-muted" : v > 0 ? "text-good" : "text-bad");
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v)}`;

/** "Since 4 Oct: −3 · Valuation −1, Momentum −2 · was Reduce" (only the axes that moved). */
export function weekChangeText(wc: WeekChange): string {
  const moved = Object.entries(wc.axes)
    .filter(([, v]) => v !== null && v !== 0)
    .map(([k, v]) => `${AXIS_LABEL[k] ?? k} ${signed(v!)}`);
  const parts = [`Since ${formatDate(wc.since)}: ${wc.total === 0 ? "no change in total" : `total ${signed(wc.total)}`}`];
  if (moved.length) parts.push(moved.join(", "));
  if (wc.signal_changed && wc.previous_signal_label) parts.push(`was ${wc.previous_signal_label}`);
  return parts.join(" · ");
}

const WEEK_TONE = {
  good: "border-good-border bg-good-soft text-good",
  bad: "border-bad-border bg-bad-soft text-bad",
  caution: "border-caution-border bg-caution-soft text-caution",
  neutral: "border-neutral-border bg-neutral-soft text-neutral",
};

/** The "changed since last week" note: arrow, sign and words, not just colour. */
export function WeekBadge({ wc }: { wc: WeekChange | null | undefined }) {
  if (!wc) return <p className="text-xs text-fg-subtle">Week-on-week change shows after a week of history.</p>;
  const changed = wc.total !== 0 || wc.signal_changed || Object.values(wc.axes).some((v) => v);
  const tone = wc.total > 0 ? "good" : wc.total < 0 ? "bad" : wc.signal_changed ? "caution" : "neutral";
  const Icon = wc.total > 0 ? ArrowUpRight : wc.total < 0 ? ArrowDownRight : Minus;
  return (
    <p className={`flex items-start gap-1.5 rounded-control border px-2 py-1 text-xs font-medium ${WEEK_TONE[tone]}`}>
      <Icon aria-hidden className="mt-px size-3.5 shrink-0" />
      <span>{changed ? weekChangeText(wc) : `No change since ${formatDate(wc.since)}`}</span>
    </p>
  );
}

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
        <span className="mb-1 block text-xs font-medium text-fg-muted">NSE symbol</span>
        <input className={`${inputClass} !w-40`} value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="e.g. TITAN" />
      </label>
      <label className="min-w-48 flex-1">
        <span className="mb-1 block text-xs font-medium text-fg-muted">Note (optional)</span>
        <input className={inputClass} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} placeholder="Why you're watching it" />
      </label>
      <Button type="submit" disabled={add.isPending || !ticker.trim()}>
        Add
      </Button>
      {add.isError && <p className="basis-full text-bad">{add.error.message}</p>}
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
      <div className="max-w-56 text-xs">
        {w.note && <p className="mb-1 text-fg">{w.note}</p>}
        <button type="button" className="text-fg-muted underline hover:text-fg" onClick={() => setEdit(true)}>
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
        <Button type="submit" size="sm" disabled={save.isPending}>
          Save
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setEdit(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function useRemove(w: WatchItem) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => watchlistApi.remove(w.ticker),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
      void qc.invalidateQueries({ queryKey: ["watch-tickers"] });
    },
  });
}

function Why({ w }: { w: WatchItem }) {
  if (w.status !== "ok") return null;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-fg-muted hover:text-fg">Why</summary>
      <div className="mt-1 max-w-md space-y-0.5">
        <p className="text-fg">{w.rule}</p>
        {w.bullish.map((r) => (
          <p key={r} className="flex items-start gap-1 text-good">
            <ArrowUpRight aria-hidden className="mt-px size-3.5 shrink-0" />
            <span className="sr-only">For: </span>
            {r}
          </p>
        ))}
        {w.bearish.map((r) => (
          <p key={r} className="flex items-start gap-1 text-bad">
            <ArrowDownRight aria-hidden className="mt-px size-3.5 shrink-0" />
            <span className="sr-only">Against: </span>
            {r}
          </p>
        ))}
        {w.flags.map((f) => (
          <p key={f.key} className="flex items-start gap-1 text-caution">
            <CircleAlert aria-hidden className="mt-px size-3.5 shrink-0" />
            <span className="sr-only">Red flag: </span>
            {f.text}
          </p>
        ))}
      </div>
    </details>
  );
}

function Row({ w }: { w: WatchItem }) {
  const remove = useRemove(w);
  return (
    <tr className="border-b border-border align-top">
      <td className="py-2 pr-3">
        <Link to={`/analysis/${encodeURIComponent(w.ticker)}`} className="font-medium text-fg hover:underline">
          {w.label}
        </Link>
        <div className="font-mono text-xs text-fg-subtle">
          {w.ticker}
          {w.sector ? ` · ${w.sector}` : ""}
          {w.held ? " · you hold this" : ""}
        </div>
        <div className="text-xs text-fg-subtle">
          Added {formatDate(w.added_at)}
          {w.source ? ` · ${w.source}` : ""}
        </div>
        <Why w={w} />
      </td>
      {w.status === "no_data" ? (
        <td colSpan={6} className="py-2 pr-3 text-sm text-fg-muted">
          No prices downloaded yet. A download runs in the background; refresh in a minute.
        </td>
      ) : (
        <>
          <td className="py-2 pr-3">
            {w.axes ? (
              <span className="flex items-center gap-1.5">
                <ScoreShape axes={axesFromRecord(w.axes)} total={w.shape_total} maxTotal={w.shape_max} step={w.shape_step} size="sm" name={w.label} animate={false} />
                <span className="whitespace-nowrap text-fg">
                  {w.shape_total}
                  <span className="text-fg-subtle">/{w.shape_max}</span>
                </span>
              </span>
            ) : (
              <span className="text-fg-subtle">—</span>
            )}
          </td>
          <td className="py-2 pr-3">
            {w.signal && w.signal_label && <SignalPill signal={w.signal} label={w.signal_label} />}
            <div>
              <ConfidenceTag c={w.confidence} />
            </div>
            {w.signal_changed_since_added && w.added_signal_label && <div className="text-xs font-medium text-caution">Was {w.added_signal_label} when added</div>}
          </td>
          <td className="py-2 pr-3 text-right">
            <div className="font-semibold text-fg">{w.composite?.toFixed(0) ?? "—"}</div>
            {w.score_change !== null && (
              <div className={`text-xs ${tone(w.score_change)}`}>
                {w.score_change > 0 ? "+" : ""}
                {w.score_change.toFixed(1)} since added
              </div>
            )}
          </td>
          <td className="whitespace-nowrap py-2 pr-3 text-right">
            <div className="text-fg">{formatINR(w.price)}</div>
            {w.price_change_pct !== null && <div className={`text-xs ${tone(w.price_change_pct)}`}>{formatPct(w.price_change_pct)} since added</div>}
            {w.stop !== null && <div className="text-xs text-fg-subtle">Stop {formatINR(w.stop)}</div>}
            {w.price_freshness && <FreshnessBadge f={w.price_freshness} />}
          </td>
          <td className="py-2 pr-3 text-xs">
            {w.last_change ? (
              <>
                {w.last_change.previous_label} → <span className="font-medium text-fg">{w.last_change.current_label}</span>
                <div className="text-fg-subtle">on {formatDate(w.last_change.day)}</div>
              </>
            ) : (
              <span className="text-fg-subtle">No change recorded</span>
            )}
          </td>
          <td className="py-2 pr-3">
            <NoteCell w={w} />
          </td>
        </>
      )}
      <td className="py-2">
        <Button variant="secondary" size="sm" aria-label={`Remove ${w.label}`} disabled={remove.isPending} onClick={() => remove.mutate()}>
          Remove
        </Button>
      </td>
    </tr>
  );
}

function Empty() {
  return <EmptyState title="Nothing on your watchlist yet">Add a symbol above, or press Watch on a Screener idea or a stock page.</EmptyState>;
}

export function WatchlistTable({ d }: { d: WatchlistData }) {
  if (d.items.length === 0) return <Empty />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-fg-muted">
          <tr className="border-b border-border">
            <th className="py-2 pr-3 font-medium">Stock</th>
            <th className="py-2 pr-3 font-medium">Shape</th>
            <th className="py-2 pr-3 font-medium">Signal now</th>
            <th className="py-2 pr-3 text-right font-medium">Score</th>
            <th className="py-2 pr-3 text-right font-medium">Price</th>
            <th className="py-2 pr-3 font-medium">Last signal change</th>
            <th className="py-2 pr-3 font-medium">Note</th>
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

function WatchCard({ w }: { w: WatchItem }) {
  const remove = useRemove(w);
  return (
    <article className="flex h-full flex-col gap-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-fg">
            <Link to={`/analysis/${encodeURIComponent(w.ticker)}`} className="hover:underline">
              {w.label}
            </Link>
          </h3>
          <p className="truncate font-mono text-xs text-fg-subtle">
            {w.ticker}
            {w.sector ? ` · ${w.sector}` : ""}
          </p>
        </div>
        {w.held && <Badge tone="accent">You hold this</Badge>}
      </header>
      {w.status === "no_data" ? (
        <p className="text-sm text-fg-muted">No prices downloaded yet. A download runs in the background; refresh in a minute.</p>
      ) : (
        <>
          <div className="flex items-center gap-3">
            {w.axes ? (
              <ScoreShape axes={axesFromRecord(w.axes)} total={w.shape_total} maxTotal={w.shape_max} step={w.shape_step} size="md" name={w.label} animate={false} />
            ) : (
              <div className="grid size-[116px] shrink-0 place-items-center rounded-card bg-surface-2 text-xs text-fg-subtle">No shape yet</div>
            )}
            <dl className="min-w-0 space-y-2 text-sm">
              <div>
                <dt className="sr-only">Signal</dt>
                <dd>{w.signal && w.signal_label && <SignalPill signal={w.signal} label={w.signal_label} />}</dd>
              </div>
              <div>
                <dt className="text-xs text-fg-subtle">Price</dt>
                <dd className="text-fg">
                  {formatINR(w.price)}
                  {w.price_change_pct !== null && <span className={`block text-xs ${tone(w.price_change_pct)}`}>{formatPct(w.price_change_pct)} since added</span>}
                </dd>
              </div>
              {w.stop !== null && (
                <div>
                  <dt className="text-xs text-fg-subtle">Stop</dt>
                  <dd className={w.stop_breached ? "text-bad" : "text-fg"}>
                    {formatINR(w.stop)}
                    {w.stop_breached && " · closed below"}
                  </dd>
                </div>
              )}
            </dl>
          </div>
          <div className="space-y-1.5">
            <WeekBadge wc={w.week_change} />
            {w.signal_changed_since_added && w.added_signal_label && <p className="text-xs font-medium text-caution">Was {w.added_signal_label} when added</p>}
          </div>
          <Why w={w} />
        </>
      )}
      <div className="mt-auto flex items-end justify-between gap-2 border-t border-border pt-2">
        <NoteCell w={w} />
        <Button variant="ghost" size="sm" aria-label={`Remove ${w.label}`} disabled={remove.isPending} onClick={() => remove.mutate()}>
          Remove
        </Button>
      </div>
      <p className="text-xs text-fg-subtle">
        Added {formatDate(w.added_at)}
        {w.source ? ` · ${w.source}` : ""}
      </p>
    </article>
  );
}

export function WatchlistCards({ d }: { d: WatchlistData }) {
  if (d.items.length === 0) return <Empty />;
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
      {d.items.map((w) => (
        <li key={w.ticker}>
          <WatchCard w={w} />
        </li>
      ))}
    </ul>
  );
}

/** Stocks you're tracking, scored live with your style and risk, and what changed since you added them. */
export function Watchlist() {
  const qc = useQueryClient();
  const [layout, setLayout] = useState<"cards" | "table">("cards");
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
      <PageHeader
        title="Watchlist"
        description="Ideas you're tracking, scored from cached data each time you open this page. The daily refresh records their signals and shapes, so changes show with a date."
      />
      <Card title="Add a stock">
        <AddForm />
      </Card>
      {q.isError ? (
        <ErrorState title="Couldn't score your watchlist" detail={q.error.message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <Loading label="your watchlist">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-72 w-full" />
            ))}
          </div>
        </Loading>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-fg-muted">
              {q.data.items.length} stock{q.data.items.length === 1 ? "" : "s"} · {q.data.style_label} · {q.data.risk_label} risk
            </p>
            <Segmented
              label="Layout"
              value={layout}
              onChange={setLayout}
              options={[
                { value: "cards", label: "Cards", icon: LayoutGrid },
                { value: "table", label: "Table", icon: Table2 },
              ]}
            />
          </div>
          {jobId !== null && <Alert tone="info">Downloading data for newly added stocks…</Alert>}
          {layout === "cards" ? (
            <WatchlistCards d={q.data} />
          ) : (
            <Card>
              <WatchlistTable d={q.data} />
            </Card>
          )}
          {q.data.items.length > 0 && (
            <Disclosure summary="How the week-on-week badge works">
              <p className="text-sm text-fg-muted">
                Each day the refresh saves every watched stock&apos;s Score Shape. The badge compares today&apos;s shape with the one from about a week ago: the total, each axis that moved, and
                whether the signal changed.
              </p>
            </Disclosure>
          )}
        </>
      )}
    </div>
  );
}
