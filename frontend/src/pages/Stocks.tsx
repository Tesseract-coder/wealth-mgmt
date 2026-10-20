import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { stocksApi, type IndexFilter, type StockRow, type StocksQuery } from "../api/client";
import { Badge, Button, Card, EmptyState, ErrorState, inputClass, PageHeader, Segmented, SkeletonCard } from "../components/ui";
import { useDebounced } from "../hooks/useDebounced";
import { formatDate, formatINR, formatINRCompact } from "../lib/format";

const PAGE = 100;
const INDEX_OPTIONS: { value: IndexFilter | ""; label: string }[] = [
  { value: "", label: "Any" },
  { value: "nifty50", label: "Nifty 50" },
  { value: "nifty100", label: "Nifty 100" },
  { value: "nifty200", label: "Nifty 200" },
  { value: "nifty500", label: "Nifty 500" },
  { value: "outside", label: "Outside the Nifty 500" },
];
const INDEX_NAME: Record<NonNullable<StockRow["index"]>, string> = { nifty50: "Nifty 50", nifty100: "Nifty 100", nifty200: "Nifty 200", nifty500: "Nifty 500" };

/** Every NSE stock and every share listed only on BSE, with what is already downloaded. */
export function Stocks() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [pages, setPages] = useState(1);
  const dq = useDebounced(q.trim(), 250);
  const exchange = (params.get("exchange") as StocksQuery["exchange"]) ?? "all";
  const index = (params.get("index") as IndexFilter | null) ?? null;
  const sector = params.get("sector");
  const loaded = params.get("loaded") === "1";
  const held = params.get("held") === "1";
  const sort = params.get("sort") === "mcap" ? "mcap" : "name";
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== "sector" && k !== "sort") p.delete("sector"); // the sector list depends on the other filters
    setParams(p, { replace: true });
    setPages(1);
  };
  const filters: StocksQuery = { q: dq, exchange, index, sector, loaded, held, sort, limit: PAGE * pages };
  const list = useQuery({ queryKey: ["stocks", filters], queryFn: () => stocksApi.list(filters), placeholderData: keepPreviousData });
  const d = list.data;

  return (
    <div className="space-y-4">
      <PageHeader
        title="All stocks"
        description={
          <>
            Every NSE stock and every share listed only on BSE. A stock's data downloads the first time you open it, and a nightly top-up fills in more.
            {d && ` ${d.loaded.toLocaleString("en-IN")} of ${d.all.toLocaleString("en-IN")} are loaded so far.`}
          </>
        }
      />
      <Card>
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="min-w-56 flex-1">
            <span className="mb-1 block text-xs font-medium text-fg-muted">Search</span>
            <span className="relative block">
              <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" />
              <input
                className={`${inputClass} pl-8`}
                placeholder="Symbol or company"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPages(1);
                }}
              />
            </span>
          </label>
          <div>
            <span className="mb-1 block text-xs font-medium text-fg-muted">Exchange</span>
            <Segmented
              label="Exchange"
              value={exchange ?? "all"}
              onChange={(v) => set("exchange", v === "all" ? null : v)}
              options={[
                { value: "all", label: "All" },
                { value: "NSE", label: "NSE" },
                { value: "BSE", label: "BSE only" },
              ]}
            />
          </div>
          <label>
            <span className="mb-1 block text-xs font-medium text-fg-muted">Index</span>
            <select className={inputClass} value={index ?? ""} onChange={(e) => set("index", e.target.value || null)}>
              {INDEX_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="mb-1 block text-xs font-medium text-fg-muted">Sector</span>
            <select className={`${inputClass} max-w-64`} value={sector ?? ""} onChange={(e) => set("sector", e.target.value || null)}>
              <option value="">Any</option>
              {sector && !d?.sectors.some((s) => s.name === sector) && <option value={sector}>{sector}</option>}
              {d?.sectors.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name} ({s.count})
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="mb-1 block text-xs font-medium text-fg-muted">Sort by</span>
            <select className={inputClass} value={sort} onChange={(e) => set("sort", e.target.value === "mcap" ? "mcap" : null)}>
              <option value="name">Name</option>
              <option value="mcap">Market cap (biggest first)</option>
            </select>
          </label>
          <div className="flex flex-col gap-1 pb-1">
            <label className="inline-flex items-center gap-1.5">
              <input type="checkbox" checked={loaded} onChange={(e) => set("loaded", e.target.checked ? "1" : null)} /> Loaded only
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input type="checkbox" checked={held} onChange={(e) => set("held", e.target.checked ? "1" : null)} /> My holdings
            </label>
          </div>
        </div>
        <p className="mt-3 text-xs text-fg-subtle" aria-live="polite">
          {d ? `${d.total.toLocaleString("en-IN")} stocks${d.total > d.rows.length ? `, showing ${d.rows.length}` : ""}.` : " "} Sector and market cap are known once a stock's data is loaded (Nifty 500 sectors always are).
        </p>
      </Card>
      {list.isError ? (
        <ErrorState title="Couldn't list the stocks" detail={list.error.message} onRetry={() => void list.refetch()} />
      ) : !d ? (
        <SkeletonCard label="every listed stock" lines={8} />
      ) : d.rows.length === 0 ? (
        <EmptyState title="No stocks match">Try fewer filters, or another spelling.</EmptyState>
      ) : (
        <Card>
          <div className="max-h-[75vh] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-surface text-left text-xs uppercase text-fg-subtle shadow-[0_1px_0_var(--color-border)]">
                <tr>
                  <th className="py-1.5 pr-3">Stock</th>
                  <th className="pr-3">Index</th>
                  <th className="pr-3">Sector</th>
                  <th className="pr-3 text-right">Market cap</th>
                  <th className="pr-3 text-right">Last close</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                {d.rows.map((r) => (
                  <StockLine key={r.ticker} r={r} />
                ))}
              </tbody>
            </table>
          </div>
          {d.total > d.rows.length && (
            <div className="mt-3 flex justify-center">
              <Button variant="secondary" disabled={list.isFetching} onClick={() => setPages((n) => n + 1)}>
                {list.isFetching ? "Loading…" : `Show ${Math.min(PAGE, d.total - d.rows.length)} more`}
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function StockLine({ r }: { r: StockRow }) {
  return (
    <tr className="border-t border-border align-top">
      <td className="py-1.5 pr-3">
        <Link className="font-medium text-fg underline-offset-2 hover:underline" to={`/analysis/${encodeURIComponent(r.ticker)}`}>
          {r.name}
        </Link>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-fg-subtle">
          <span className="font-mono">{r.ticker}</span>
          {r.exchange === "BSE" && <Badge>BSE only</Badge>}
          {r.held && <Badge tone="accent">Held</Badge>}
          {r.watched && <Badge tone="good">Watching</Badge>}
        </div>
      </td>
      <td className="whitespace-nowrap pr-3 text-fg-muted">{r.index ? INDEX_NAME[r.index] : "—"}</td>
      <td className="pr-3 text-fg-muted">{r.sector ?? "—"}</td>
      <td className="whitespace-nowrap pr-3 text-right tabular-nums">{r.mcap_cr === null ? "—" : formatINRCompact(r.mcap_cr * 1e7)}</td>
      <td className="whitespace-nowrap pr-3 text-right tabular-nums">
        {r.close === null ? "—" : formatINR(r.close)}
        {r.as_of && <div className="text-xs text-fg-subtle">{formatDate(r.as_of)}</div>}
      </td>
      <td className="whitespace-nowrap text-xs">{r.loaded ? <span className="text-fg-muted">Loaded</span> : <span className="text-fg-subtle">Not loaded yet: opens on first visit</span>}</td>
    </tr>
  );
}
