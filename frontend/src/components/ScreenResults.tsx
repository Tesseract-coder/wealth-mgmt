import { ArrowDownRight, ArrowUpRight, CircleAlert, LayoutGrid, Table2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Candidate, ScreenResult } from "../api/client";
import { formatFreshness, formatINR } from "../lib/format";
import { AXIS_LABEL, axesFromRecord, ScoreShape, SignalPill } from "./analysis";
import { ConfidenceTag } from "./SignalView";
import { Alert, Disclosure, EmptyState, Segmented } from "./ui";
import { WatchButton } from "./WatchButton";

const TF: Record<string, string> = { "15m": "15-min", "1h": "hourly", "1d": "daily", "1wk": "weekly", "1mo": "monthly" };
const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;
const AXES = ["valuation", "growth", "past", "health", "momentum", "dividends"] as const;

/** "501 in the universe → 486 scored → … → 12 passed": where stocks dropped out. */
export function funnel(c: ScreenResult["counts"], includeHeld: boolean): string[] {
  const out = [`${c.universe} in the universe`];
  if (c.not_scored) out.push(`${c.not_scored} not scored (no data, illiquid or too new)`);
  if (c.held && !includeHeld) out.push(`${c.held} you already hold`);
  if (c.prefilter) out.push(`${c.prefilter} outside your risk limits`);
  if (c.signal) out.push(`${c.signal} with a Sell or Reduce signal`);
  if (c.filters) out.push(`${c.filters} failed the screen`);
  if (c.missing_data) out.push(`${c.missing_data} missing data for a filter`);
  out.push(`${c.passed} passed`);
  return out;
}

/** The scan's Score Shape for a candidate, or null for scans made before shapes existed. */
export function shapeFromFacts(facts: Record<string, number | null>): { axes: Record<string, number | null>; total: number | null } | null {
  if (!AXES.some((k) => `axis_${k}` in facts)) return null;
  return { axes: Object.fromEntries(AXES.map((k) => [k, facts[`axis_${k}`] ?? null])), total: facts.axis_total ?? null };
}

/** Two key facts: the strongest and weakest axis, or the top reasons when there's no shape. */
export function keyFacts(c: Candidate): string[] {
  const s = shapeFromFacts(c.facts);
  const scored = s ? Object.entries(s.axes).filter((e): e is [string, number] => e[1] !== null) : [];
  if (scored.length >= 2) {
    const sorted = [...scored].sort((a, b) => b[1] - a[1]);
    const [hi, lo] = [sorted[0]!, sorted.at(-1)!];
    return [`Strongest: ${AXIS_LABEL[hi[0]]} ${hi[1]}/6`, `Weakest: ${AXIS_LABEL[lo[0]]} ${lo[1]}/6`];
  }
  return [...c.bullish.slice(0, 1), ...c.bearish.slice(0, 1)];
}

function Levels({ c }: { c: Candidate }) {
  const lv = c.levels;
  if (!lv) return <span className="text-xs text-fg-subtle">Not enough bars for levels</span>;
  return (
    <div className="space-y-0.5 text-xs" title={`${lv.entry_basis} ${lv.basis}`}>
      <div className="text-fg">
        <span className="text-fg-subtle">Entry </span>
        {formatINR(lv.entry_low)} – {formatINR(lv.entry_high)}
      </div>
      <div className="text-bad">
        <span className="text-fg-subtle">Stop </span>
        {formatINR(lv.stop)} ({signed(lv.stop_pct)})
      </div>
      {lv.targets.map((t) => (
        <div key={t.label} className="text-good">
          <span className="text-fg-subtle">{t.label} </span>
          {formatINR(t.price)} ({signed(t.pct)})
        </div>
      ))}
      <div className="text-fg-subtle">on {TF[lv.interval] ?? lv.interval} bars</div>
    </div>
  );
}

function Impact({ c }: { c: Candidate }) {
  const i = c.impact;
  return (
    <div className={`text-xs ${i.over_limit ? "text-caution" : "text-fg"}`}>
      {i.before !== null && i.after !== null ? (
        <>
          <div className="font-medium" title={i.text}>
            {i.over_limit && <CircleAlert aria-hidden className="mr-1 inline size-3.5" />}
            {i.sector}: {pct(i.before)} → {pct(i.after)}
          </div>
          <div className="text-fg-subtle">
            Starter {formatINR(i.amount, 0)}
            {i.quantity ? ` (${i.quantity} shares)` : ""}
          </div>
          {i.over_limit && <div>Above your sector limit</div>}
        </>
      ) : (
        <span className="text-fg-subtle">{i.text}</span>
      )}
    </div>
  );
}

/** "How this changes my portfolio": the sector's share before and after a starter position, as two bars. */
export function PortfolioEffect({ c }: { c: Candidate }) {
  const i = c.impact;
  if (i.before === null || i.after === null) return <p className="text-xs text-fg-muted">{i.text}</p>;
  const max = Math.max(i.after, 0.01) * 1.15;
  const rows = [
    { label: "Now", v: i.before, cls: "bg-border-strong" },
    { label: "After buying", v: i.after, cls: i.over_limit ? "bg-caution" : "bg-accent" },
  ];
  return (
    <figure aria-label={`${i.sector} share of your portfolio, now and after a starter position`}>
      <p className="mb-1.5 text-xs font-medium text-fg">{i.sector} share of your portfolio</p>
      <div className="space-y-1">
        {rows.map((r) => (
          <div key={r.label} className="grid grid-cols-[5.5rem_1fr_3rem] items-center gap-2 text-xs">
            <span className="text-fg-muted">{r.label}</span>
            <span className="h-3 rounded-[3px] bg-surface-2">
              <span className={`block h-3 rounded-[3px] ${r.cls}`} style={{ width: `${(r.v / max) * 100}%` }} />
            </span>
            <span className="text-right font-semibold text-fg">{pct(r.v)}</span>
          </div>
        ))}
      </div>
      <figcaption className="mt-1.5 text-xs text-fg-muted">
        A starter of {formatINR(i.amount, 0)}
        {i.quantity ? ` (${i.quantity} shares)` : ""} {i.over_limit ? "would take the sector above your limit." : "keeps the sector within your limit."}
      </figcaption>
    </figure>
  );
}

function Reasons({ c }: { c: Candidate }) {
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-fg-muted hover:text-fg">Why</summary>
      <div className="mt-1 max-w-md space-y-1">
        <p className="text-fg">{c.rule}</p>
        {c.passed.length > 0 && <p className="text-fg-muted">Screen: {c.passed.join(" · ")}</p>}
        <ul className="space-y-0.5">
          {c.bullish.map((r) => (
            <li key={r} className="flex items-start gap-1 text-good">
              <ArrowUpRight aria-hidden className="mt-px size-3.5 shrink-0" />
              <span className="sr-only">For: </span>
              {r}
            </li>
          ))}
          {c.bearish.map((r) => (
            <li key={r} className="flex items-start gap-1 text-bad">
              <ArrowDownRight aria-hidden className="mt-px size-3.5 shrink-0" />
              <span className="sr-only">Against: </span>
              {r}
            </li>
          ))}
          {c.flags.map((f) => (
            <li key={f.key} className="flex items-start gap-1 text-caution">
              <CircleAlert aria-hidden className="mt-px size-3.5 shrink-0" />
              <span className="sr-only">Red flag: </span>
              {f.text}
            </li>
          ))}
        </ul>
        {c.levels && <p className="text-fg-subtle">{c.levels.entry_basis}</p>}
      </div>
    </details>
  );
}

function SmallShape({ c, size }: { c: Candidate; size: "sm" | "md" }) {
  const s = shapeFromFacts(c.facts);
  if (!s) return size === "md" ? <div className="grid size-[116px] shrink-0 place-items-center rounded-card bg-surface-2 text-center text-xs text-fg-subtle">Re-scan for a shape</div> : <span className="text-fg-subtle">—</span>;
  return <ScoreShape axes={axesFromRecord(s.axes)} total={s.total} maxTotal={36} size={size} name={c.label} animate={false} />;
}

/** One idea as a card: shape, signal, entry zone, two key facts, and the portfolio effect. */
function CandidateCard({ c, source }: { c: Candidate; source: string }) {
  const s = shapeFromFacts(c.facts);
  return (
    <article className="flex h-full flex-col gap-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-fg">
            <span className="mr-1 text-fg-subtle">{c.rank}.</span>
            <Link to={`/analysis/${encodeURIComponent(c.ticker)}`} className="hover:underline">
              {c.label}
            </Link>
          </h3>
          <p className="truncate font-mono text-xs text-fg-subtle">
            {c.symbol}
            {c.sector ? ` · ${c.sector}` : ""}
            {c.held ? " · you hold this" : ""}
          </p>
        </div>
        <WatchButton ticker={c.ticker} source={source} compact />
      </header>
      <div className="flex items-center gap-3">
        <SmallShape c={c} size="md" />
        <dl className="min-w-0 space-y-2 text-sm">
          <div>
            <dt className="sr-only">Signal</dt>
            <dd className="flex flex-wrap items-center gap-1.5">
              <SignalPill signal={c.signal} label={c.signal_label} />
              <ConfidenceTag c={c.confidence} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Score</dt>
            <dd className="text-fg">
              <span className="font-semibold">{c.composite?.toFixed(0) ?? "—"}</span>
              <span className="text-xs text-fg-muted">
                {" "}
                · T {c.technical?.toFixed(0) ?? "—"} · F {c.fundamental?.toFixed(0) ?? "—"}
              </span>
              {s?.total != null && <span className="block text-xs text-fg-muted">Shape {s.total}/36</span>}
            </dd>
          </div>
          {c.levels && (
            <div>
              <dt className="text-xs text-fg-subtle">Entry zone</dt>
              <dd className="text-fg">
                {formatINR(c.levels.entry_low)} – {formatINR(c.levels.entry_high)}
              </dd>
            </div>
          )}
        </dl>
      </div>
      <ul className="space-y-0.5 border-t border-border pt-2 text-xs text-fg-muted">
        {keyFacts(c).map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <Disclosure summary="How this changes my portfolio">
        <div className="space-y-3">
          <PortfolioEffect c={c} />
          <Levels c={c} />
        </div>
      </Disclosure>
      <Reasons c={c} />
    </article>
  );
}

export function ScreenResults({ r, includeHeld }: { r: ScreenResult; includeHeld: boolean }) {
  const [layout, setLayout] = useState<"cards" | "table">("cards");
  const source = `Screener: ${r.title}`;
  return (
    <div className="space-y-3">
      {r.stale_note && <Alert tone="warning">{r.stale_note}</Alert>}
      <div className="space-y-1 text-sm">
        <p className="text-xs text-fg-subtle">
          From the {r.scan.universe_label} scan of {formatFreshness(new Date(r.scan.finished_at ?? r.scan.created_at))} ({r.scan.style_label}, {r.scan.risk_label} risk
          {r.scan.status === "partial" ? ", stopped early" : ""})
        </p>
        <p className="font-medium text-fg">{r.filters.length ? r.filters.join(" · ") : "No screen filters: ranked by score."}</p>
        <p className="text-fg-muted">{funnel(r.counts, includeHeld).join(" → ")}</p>
        <details className="text-xs text-fg-subtle">
          <summary className="cursor-pointer">Always applied ({r.scan.risk_label} risk)</summary>
          <ul className="list-disc pl-5">
            {r.prefilters.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </details>
      </div>
      {r.candidates.length === 0 ? (
        <EmptyState title="No stock passed this screen">
          {r.near_misses.length > 0 ? "The closest misses are listed below. Loosen a condition or try another screen." : "Loosen a condition or try another screen."}
        </EmptyState>
      ) : (
        <>
          <div className="flex justify-end">
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
          {layout === "cards" ? (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4" aria-label="Ideas">
              {r.candidates.map((c) => (
                <li key={c.ticker}>
                  <CandidateCard c={c} source={source} />
                </li>
              ))}
            </ul>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-fg-muted">
                  <tr className="border-b border-border">
                    <th className="py-2 pr-3 font-medium">#</th>
                    <th className="py-2 pr-3 font-medium">Stock</th>
                    <th className="py-2 pr-3 font-medium">Shape</th>
                    <th className="py-2 pr-3 font-medium">Signal</th>
                    <th className="py-2 pr-3 text-right font-medium">Score</th>
                    <th className="py-2 pr-3 font-medium">Entry · stop · targets</th>
                    <th className="py-2 pr-3 font-medium">Sector effect</th>
                    <th className="py-2 font-medium">Watch</th>
                  </tr>
                </thead>
                <tbody>
                  {r.candidates.map((c) => (
                    <tr key={c.ticker} className="border-b border-border align-top">
                      <td className="py-2 pr-3 text-fg-subtle">{c.rank}</td>
                      <td className="py-2 pr-3">
                        <Link to={`/analysis/${encodeURIComponent(c.ticker)}`} className="font-medium text-fg hover:underline">
                          {c.label}
                        </Link>
                        <div className="font-mono text-xs text-fg-subtle">
                          {c.symbol}
                          {c.sector ? ` · ${c.sector}` : ""}
                          {c.held ? " · you hold this" : ""}
                        </div>
                        <Reasons c={c} />
                      </td>
                      <td className="py-2 pr-3">
                        <SmallShape c={c} size="sm" />
                      </td>
                      <td className="py-2 pr-3">
                        <SignalPill signal={c.signal} label={c.signal_label} />
                        <div>
                          <ConfidenceTag c={c.confidence} />
                        </div>
                      </td>
                      <td className="py-2 pr-3 text-right">
                        <div className="font-semibold text-fg">{c.composite?.toFixed(0) ?? "—"}</div>
                        <div className="text-xs text-fg-subtle">
                          T {c.technical?.toFixed(0) ?? "—"} · F {c.fundamental?.toFixed(0) ?? "—"}
                        </div>
                      </td>
                      <td className="py-2 pr-3">
                        <Levels c={c} />
                      </td>
                      <td className="max-w-56 py-2 pr-3">
                        <Impact c={c} />
                      </td>
                      <td className="py-2">
                        <WatchButton ticker={c.ticker} source={source} compact />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {r.near_misses.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-fg-muted hover:text-fg">Near misses (failed one condition)</summary>
          <ul className="mt-1 space-y-0.5 text-xs text-fg">
            {r.near_misses.map((m) => (
              <li key={m.ticker}>
                <Link to={`/analysis/${encodeURIComponent(m.ticker)}`} className="underline">
                  {m.label}
                </Link>{" "}
                (score {m.composite?.toFixed(0) ?? "—"}): failed {m.failed.join(", ")}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-fg-subtle">
        Entry zone, stop and targets use your style&apos;s main timeframe and your risk level&apos;s ATR multiple. Ideas to research, not orders: this app never places trades.
      </p>
    </div>
  );
}
