import { Link } from "react-router-dom";
import type { Candidate, ScreenResult } from "../api/client";
import { formatFreshness, formatINR } from "../lib/format";
import { ConfidenceTag, SignalPill } from "./SignalView";
import { Alert } from "./ui";
import { WatchButton } from "./WatchButton";

const TF: Record<string, string> = {
  "15m": "15-min",
  "1h": "hourly",
  "1d": "daily",
  "1wk": "weekly",
  "1mo": "monthly",
};
const pct = (v: number | null) =>
  v === null ? "—" : `${(v * 100).toFixed(1)}%`;
const signed = (v: number) =>
  `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;

/** "501 in the universe → 486 scored → … → 12 passed": where stocks dropped out. */
export function funnel(
  c: ScreenResult["counts"],
  includeHeld: boolean,
): string[] {
  const out = [`${c.universe} in the universe`];
  if (c.not_scored)
    out.push(`${c.not_scored} not scored (no data, illiquid or too new)`);
  if (c.held && !includeHeld) out.push(`${c.held} you already hold`);
  if (c.prefilter) out.push(`${c.prefilter} outside your risk limits`);
  if (c.signal) out.push(`${c.signal} with a Sell or Reduce signal`);
  if (c.filters) out.push(`${c.filters} failed the screen`);
  if (c.missing_data) out.push(`${c.missing_data} missing data for a filter`);
  out.push(`${c.passed} passed`);
  return out;
}

function Levels({ c }: { c: Candidate }) {
  const lv = c.levels;
  if (!lv)
    return <span className="text-slate-500">Not enough bars for levels</span>;
  return (
    <div
      className="space-y-0.5 text-xs tabular-nums"
      title={`${lv.entry_basis} ${lv.basis}`}
    >
      <div>
        <span className="text-slate-500">Entry </span>
        {formatINR(lv.entry_low)} – {formatINR(lv.entry_high)}
      </div>
      <div className="text-red-700 dark:text-red-400">
        <span className="text-slate-500">Stop </span>
        {formatINR(lv.stop)} ({signed(lv.stop_pct)})
      </div>
      {lv.targets.map((t) => (
        <div key={t.label} className="text-emerald-700 dark:text-emerald-400">
          <span className="text-slate-500">{t.label} </span>
          {formatINR(t.price)} ({signed(t.pct)})
        </div>
      ))}
      <div className="text-slate-500">
        on {TF[lv.interval] ?? lv.interval} bars
      </div>
    </div>
  );
}

function Impact({ c }: { c: Candidate }) {
  const i = c.impact;
  return (
    <div
      className={`text-xs ${i.over_limit ? "text-amber-800 dark:text-amber-300" : ""}`}
    >
      {i.before !== null && i.after !== null ? (
        <>
          <div className="font-medium" title={i.text}>
            {i.over_limit && <span aria-hidden="true">⚠ </span>}
            {i.sector}: {pct(i.before)} → {pct(i.after)}
          </div>
          <div className="text-slate-500">
            Starter {formatINR(i.amount, 0)}
            {i.quantity ? ` (${i.quantity} shares)` : ""}
          </div>
          {i.over_limit && <div>Above your sector limit</div>}
        </>
      ) : (
        <span className="text-slate-500">{i.text}</span>
      )}
    </div>
  );
}

/** Small screens: one card per idea instead of a wide table. */
function CandidateCard({ c, source }: { c: Candidate; source: string }) {
  return (
    <li className="rounded border border-slate-200 p-3 dark:border-slate-800">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="mr-1 tabular-nums text-slate-500">{c.rank}.</span>
          <Link
            to={`/analysis/${encodeURIComponent(c.ticker)}`}
            className="font-medium underline"
          >
            {c.label}
          </Link>
          <div className="font-mono text-xs text-slate-500">
            {c.symbol}
            {c.sector ? ` · ${c.sector}` : ""}
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold tabular-nums">
            {c.composite?.toFixed(0) ?? "—"}
          </div>
          <div className="text-xs text-slate-500">
            T {c.technical?.toFixed(0) ?? "—"} · F{" "}
            {c.fundamental?.toFixed(0) ?? "—"}
          </div>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <SignalPill signal={c.signal} label={c.signal_label} />
        <ConfidenceTag c={c.confidence} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-3">
        <Levels c={c} />
        <Impact c={c} />
      </div>
      <div className="mt-2 flex items-start justify-between gap-2">
        <Reasons c={c} />
        <WatchButton ticker={c.ticker} source={source} compact />
      </div>
    </li>
  );
}

function Reasons({ c }: { c: Candidate }) {
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-slate-600 dark:text-slate-400">
        Why
      </summary>
      <div className="mt-1 max-w-md space-y-1">
        <p>{c.rule}</p>
        {c.passed.length > 0 && (
          <p className="text-slate-600 dark:text-slate-400">
            Screen: {c.passed.join(" · ")}
          </p>
        )}
        <ul className="space-y-0.5">
          {c.bullish.map((r) => (
            <li key={r} className="text-emerald-800 dark:text-emerald-300">
              ▲ {r}
            </li>
          ))}
          {c.bearish.map((r) => (
            <li key={r} className="text-red-800 dark:text-red-300">
              ▼ {r}
            </li>
          ))}
          {c.flags.map((f) => (
            <li key={f.key} className="text-amber-800 dark:text-amber-300">
              ⚠ {f.text}
            </li>
          ))}
        </ul>
        {c.levels && <p className="text-slate-500">{c.levels.entry_basis}</p>}
      </div>
    </details>
  );
}

export function ScreenResults({
  r,
  includeHeld,
}: {
  r: ScreenResult;
  includeHeld: boolean;
}) {
  return (
    <div className="space-y-3">
      {r.stale_note && <Alert tone="warning">{r.stale_note}</Alert>}
      <div className="text-sm">
        <p className="text-xs text-slate-500">
          From the {r.scan.universe_label} scan of{" "}
          {formatFreshness(new Date(r.scan.finished_at ?? r.scan.created_at))} (
          {r.scan.style_label}, {r.scan.risk_label} risk
          {r.scan.status === "partial" ? ", stopped early" : ""})
        </p>
        <p className="font-medium">
          {r.filters.length
            ? r.filters.join(" · ")
            : "No screen filters: ranked by score."}
        </p>
        <p className="text-slate-600 dark:text-slate-400">
          {funnel(r.counts, includeHeld).join(" → ")}
        </p>
        <details className="text-xs text-slate-500">
          <summary className="cursor-pointer">
            Always applied ({r.scan.risk_label} risk)
          </summary>
          <ul className="list-disc pl-5">
            {r.prefilters.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </details>
      </div>
      {r.candidates.length === 0 ? (
        <Alert tone="info">
          No stock passed this screen.
          {r.near_misses.length > 0 && " Closest misses are listed below."}
        </Alert>
      ) : (
        <>
          <ul className="space-y-2 md:hidden" aria-label="Ideas">
            {r.candidates.map((c) => (
              <CandidateCard
                key={c.ticker}
                c={c}
                source={`Screener: ${r.title}`}
              />
            ))}
          </ul>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-1 pr-2">#</th>
                  <th className="pr-2">Stock</th>
                  <th className="pr-2">Signal</th>
                  <th className="pr-2 text-right">Score</th>
                  <th className="pr-2">Entry · stop · targets</th>
                  <th className="pr-2">Sector effect</th>
                  <th>Watch</th>
                </tr>
              </thead>
              <tbody>
                {r.candidates.map((c) => (
                  <tr
                    key={c.ticker}
                    className="border-t border-slate-100 align-top dark:border-slate-800"
                  >
                    <td className="py-1.5 pr-2 tabular-nums text-slate-500">
                      {c.rank}
                    </td>
                    <td className="pr-2">
                      <Link
                        to={`/analysis/${encodeURIComponent(c.ticker)}`}
                        className="font-medium underline"
                      >
                        {c.label}
                      </Link>
                      <div className="font-mono text-xs text-slate-500">
                        {c.symbol}
                        {c.sector ? ` · ${c.sector}` : ""}
                        {c.held ? " · you hold this" : ""}
                      </div>
                      <Reasons c={c} />
                    </td>
                    <td className="pr-2">
                      <SignalPill signal={c.signal} label={c.signal_label} />
                      <div>
                        <ConfidenceTag c={c.confidence} />
                      </div>
                    </td>
                    <td className="pr-2 text-right tabular-nums">
                      <div className="font-semibold">
                        {c.composite?.toFixed(0) ?? "—"}
                      </div>
                      <div className="text-xs text-slate-500">
                        T {c.technical?.toFixed(0) ?? "—"} · F{" "}
                        {c.fundamental?.toFixed(0) ?? "—"}
                      </div>
                    </td>
                    <td className="pr-2">
                      <Levels c={c} />
                    </td>
                    <td className="max-w-56 pr-2">
                      <Impact c={c} />
                    </td>
                    <td>
                      <WatchButton
                        ticker={c.ticker}
                        source={`Screener: ${r.title}`}
                        compact
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {r.near_misses.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-slate-600 dark:text-slate-400">
            Near misses (failed one condition)
          </summary>
          <ul className="mt-1 space-y-0.5 text-xs">
            {r.near_misses.map((m) => (
              <li key={m.ticker}>
                <Link
                  to={`/analysis/${encodeURIComponent(m.ticker)}`}
                  className="underline"
                >
                  {m.label}
                </Link>{" "}
                (score {m.composite?.toFixed(0) ?? "—"}): failed{" "}
                {m.failed.join(", ")}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-slate-500">
        Entry zone, stop and targets use your style's main timeframe and your
        risk level's ATR multiple. Ideas to research, not orders: this app never
        places trades.
      </p>
    </div>
  );
}
