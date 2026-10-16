import { useQueries, useQuery } from "@tanstack/react-query";
import { LoaderCircle, Plus, X } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, checksApi, portfolioApi, summaryApi, type StockChecks } from "../api/client";
import { axesFromSections, ShapeOverlay, SignalPill } from "../components/analysis";
import { Card, Chip, EmptyState, ErrorState, inputClass, Loading, PageHeader, Skeleton, StatusIcon } from "../components/ui";
import { useDebounced } from "../hooks/useDebounced";

const MAX = 4;

/** Tickers from ?t=A,B,C (deduplicated, at most four). */
export function parseTickers(raw: string | null): string[] {
  return [...new Set((raw ?? "").split(",").map((t) => t.trim().toUpperCase()).filter(Boolean))].slice(0, MAX);
}

function Picker({ tickers, onAdd }: { tickers: string[]; onAdd: (t: string) => void }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim());
  const results = useQuery({ queryKey: ["ref", "stock", dq], queryFn: () => portfolioApi.searchSecurities(dq), enabled: dq.length >= 2 });
  const summary = useQuery({ queryKey: ["portfolio-summary"], queryFn: summaryApi.get });
  const held = (summary.data?.by_holding ?? []).filter((h) => h.key.endsWith(".NS") && !tickers.includes(h.key)).slice(0, 10);
  const full = tickers.length >= MAX;
  const add = (t: string) => {
    setQ("");
    onAdd(t);
  };
  return (
    <div className="space-y-3">
      <div className="relative max-w-md">
        <label className="text-sm">
          <span className="mb-1 block text-xs font-medium text-fg-muted">Add a stock {full && "(up to four: remove one first)"}</span>
          <input
            className={inputClass}
            disabled={full}
            placeholder="Search NSE symbol or company…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && q.trim()) {
                const t = q.trim().toUpperCase();
                add(t.includes(".") ? t : `${t}.NS`);
              }
            }}
          />
        </label>
        {dq.length >= 2 && results.data && results.data.length > 0 && !full && (
          <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-control border border-border bg-surface shadow-pop">
            {results.data
              .filter((s) => s.symbol)
              .map((s) => (
                <li key={s.symbol}>
                  <button type="button" className="w-full px-3 py-1.5 text-left text-sm hover:bg-surface-2" onClick={() => add(`${s.symbol}.NS`)}>
                    <span className="font-mono">{s.symbol}</span> · {s.name}
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>
      {held.length > 0 && !full && (
        <div role="group" aria-label="Your holdings" className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-xs font-medium text-fg-subtle">From your holdings</span>
          {held.map((h) => (
            <Chip key={h.key} pressed={false} onClick={() => add(h.key)}>
              <Plus aria-hidden className="size-3" />
              {h.label}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}

/** Every check any of the stocks has in a section (lenders have their own Health checks), in first-seen order. */
export function unionChecks(stocks: StockChecks[], section: string) {
  const seen = new Map<string, StockChecks["sections"][number]["checks"][number]>();
  for (const s of stocks) for (const c of s.sections.find((x) => x.key === section)?.checks ?? []) if (!seen.has(c.check_id)) seen.set(c.check_id, c);
  return [...seen.values()];
}

/** Each section's checks, one column per stock: icon, the value, and each column's score in the section row. */
export function CompareTable({ stocks }: { stocks: StockChecks[] }) {
  const first = stocks[0];
  if (!first) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[36rem] text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="sticky left-0 z-10 w-[34%] bg-surface py-2 pr-3 text-xs font-medium text-fg-muted">Check</th>
            {stocks.map((s) => (
              <th key={s.ticker} scope="col" className="py-2 pr-3 align-bottom">
                <Link to={`/analysis/${encodeURIComponent(s.ticker)}`} className="font-semibold text-fg hover:underline">
                  {s.label}
                </Link>
                <span className="mt-1 block">
                  <SignalPill signal={s.signal} label={s.signal_label} />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        {first.sections.map((sec) => (
          <tbody key={sec.key}>
            <tr className="bg-surface-2">
              <th scope="rowgroup" className="sticky left-0 z-10 bg-surface-2 py-2 pl-2 pr-3 text-left font-semibold text-fg">
                {sec.label}
              </th>
              {stocks.map((s) => {
                const x = s.sections.find((y) => y.key === sec.key);
                return (
                  <td key={s.ticker} className="py-2 pr-3 font-semibold text-fg">
                    {x?.score == null ? "Not enough data" : `${x.score}/6`}
                    <span className="ml-1 text-xs font-normal text-fg-subtle">{x ? `${x.passed} of ${x.checks.length} passed` : ""}</span>
                  </td>
                );
              })}
            </tr>
            {unionChecks(stocks, sec.key).map((c) => (
              <tr key={c.check_id} className="border-b border-border">
                <th scope="row" className="sticky left-0 z-10 max-w-40 bg-surface py-1.5 pl-2 pr-3 text-left font-normal text-fg-muted sm:max-w-none">
                  {c.label}
                </th>
                {stocks.map((s) => {
                  const x = s.sections.find((y) => y.key === sec.key)?.checks.find((y) => y.check_id === c.check_id);
                  return (
                    <td key={s.ticker} className="py-1.5 pr-3" title={x?.explanation}>
                      {x ? (
                        <span className="inline-flex items-center gap-1.5">
                          <StatusIcon status={x.status} />
                          <span className="text-fg">{x.status === "no_data" ? "No data" : x.display_value}</span>
                        </span>
                      ) : (
                        <span className="text-fg-subtle">n/a</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

/** Pick two to four stocks; overlay their Score Shapes and compare every check side by side. */
export function Compare() {
  const [params, setParams] = useSearchParams();
  const tickers = parseTickers(params.get("t"));
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const style = profile.data?.style ?? null;
  const results = useQueries({
    queries: tickers.map((t) => ({
      // Same key as the stock page (saved risk level), so opening a stock from here is instant.
      queryKey: ["checks", t, style],
      queryFn: () => checksApi.stock(t, style),
      enabled: profile.isSuccess || profile.isError,
    })),
  });
  const set = (next: string[]) => {
    const p = new URLSearchParams(params);
    if (next.length) p.set("t", next.join(","));
    else p.delete("t");
    setParams(p);
  };
  const loaded = results.flatMap((r) => (r.data ? [r.data] : []));
  const loading = results.some((r) => r.isLoading);

  return (
    <div className="space-y-4">
      <PageHeader title="Compare" description="Put two to four stocks side by side: their Score Shapes on one chart, then every check." />
      <Card>
        {tickers.length > 0 && (
          <div role="group" aria-label="Stocks being compared" className="mb-4 flex flex-wrap gap-2">
            {tickers.map((t, i) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 py-0.5 pl-3 pr-1 text-sm text-fg">
                {results[i]?.data?.label ?? t}
                <button type="button" aria-label={`Remove ${results[i]?.data?.label ?? t}`} onClick={() => set(tickers.filter((x) => x !== t))} className="grid size-6 place-items-center rounded-full text-fg-subtle hover:bg-surface-3 hover:text-fg">
                  <X aria-hidden className="size-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}
        <Picker tickers={tickers} onAdd={(t) => set([...tickers.filter((x) => x !== t), t].slice(0, MAX))} />
      </Card>

      {results.map((r, i) =>
        r.isError ? <ErrorState key={tickers[i]} title={`Couldn't check ${tickers[i]}`} detail={r.error.message} hint="Check the ticker, or remove it and try another." onRetry={() => void r.refetch()} /> : null,
      )}

      {tickers.length < 2 ? (
        <EmptyState title="Pick at least two stocks">Search above or tap one of your holdings. You can compare up to four.</EmptyState>
      ) : loaded.length < 2 && loading ? (
        <Loading label="the comparison">
          <Skeleton className="h-80 w-full" />
        </Loading>
      ) : loaded.length >= 2 ? (
        <>
          {loading && (
            <p role="status" className="flex items-center gap-2 text-sm text-fg-muted">
              <LoaderCircle aria-hidden className="size-4 animate-spin" />
              Still loading {tickers.filter((_, i) => results[i]?.isLoading).join(", ")}: it's added below when ready (the first look downloads its data).
            </p>
          )}
          <Card title="Score Shapes">
            <ShapeOverlay series={loaded.map((s) => ({ name: s.label, axes: axesFromSections(s.sections), total: s.total, maxTotal: s.max_total }))} />
            <p className="mt-3 text-center text-sm text-fg-muted">
              {(() => {
                const best = [...loaded].sort((a, b) => b.total - a.total)[0]!;
                return `${best.label} has the biggest shape at ${best.total}/${best.max_total}.`;
              })()}{" "}
              Scores use your {loaded[0]!.style_label.toLowerCase()} style and {loaded[0]!.risk_label.toLowerCase()} risk.
            </p>
          </Card>
          <Card title="Checks side by side" description="Tick = pass, warning = fail, dash = no data. Hover a cell for the explanation.">
            <CompareTable stocks={loaded} />
          </Card>
        </>
      ) : null}
    </div>
  );
}
