import { ArrowDownWideNarrow, ArrowUpNarrowWide, LayoutGrid, Search, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { ConfidenceLevel, HoldingShape, HoldingSignal, HoldingSignals, SignalKey } from "../../api/client";
import { formatINR } from "../../lib/format";
import { HoldingsTable, isNumericSort, sortHoldings, type Sort, type SortKey } from "../HoldingsTable";
import { Alert, Chip, ChipGroup, EmptyState, inputClass, Segmented } from "../ui";
import { HoldingCard } from "./HoldingCard";

export type HoldingsLayout = "cards" | "table";

/** Signal chips group Strong Buy with Buy, as people think of them. */
const SIGNAL_CHIPS: { key: string; label: string; signals: SignalKey[] }[] = [
  { key: "buy", label: "Buy", signals: ["strong_buy", "buy"] },
  { key: "hold", label: "Hold", signals: ["hold"] },
  { key: "reduce", label: "Reduce", signals: ["reduce"] },
  { key: "sell", label: "Sell", signals: ["sell"] },
  { key: "none", label: "No signal", signals: ["no_signal"] },
];
const CONFIDENCE: { key: ConfidenceLevel; label: string }[] = [
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
];

const SORTS: { key: SortKey; label: string }[] = [
  { key: "signal", label: "Signal (most urgent first)" },
  { key: "shape", label: "Total score (shape)" },
  { key: "composite", label: "Signal score" },
  { key: "pnl", label: "P&L (₹)" },
  { key: "pnl_pct", label: "P&L (%)" },
  { key: "weight", label: "Weight" },
  { key: "label", label: "Name" },
  { key: "axis:valuation", label: "Valuation axis" },
  { key: "axis:growth", label: "Future Growth axis" },
  { key: "axis:past", label: "Past Performance axis" },
  { key: "axis:health", label: "Financial Health axis" },
  { key: "axis:momentum", label: "Momentum axis" },
  { key: "axis:dividends", label: "Dividends axis" },
];

function toggle<T>(set: Set<T>, v: T): Set<T> {
  const n = new Set(set);
  if (n.has(v)) n.delete(v);
  else n.add(v);
  return n;
}

/**
 * Holdings with search, filter chips (signal, sector, confidence), sorting by any score or axis,
 * and a card grid / table toggle. `shapes` comes from the checks endpoint; holdings still show
 * while it loads.
 */
export function HoldingsView({
  d,
  shapes = [],
  linkQuery = "",
  layout,
  onLayout,
}: {
  d: HoldingSignals;
  shapes?: HoldingShape[];
  linkQuery?: string;
  layout: HoldingsLayout;
  onLayout: (l: HoldingsLayout) => void;
}) {
  const [q, setQ] = useState("");
  const [signals, setSignals] = useState<Set<string>>(new Set());
  const [sectors, setSectors] = useState<Set<string>>(new Set());
  const [conf, setConf] = useState<Set<ConfidenceLevel>>(new Set());
  const [sort, setSort] = useState<Sort>({ key: "signal", dir: 1 });
  const byTicker = useMemo(() => new Map(shapes.map((s) => [s.ticker, s])), [shapes]);

  const count = (pred: (h: HoldingSignal) => boolean) => d.holdings.filter(pred).length;
  const signalChips = SIGNAL_CHIPS.map((c) => ({ ...c, n: count((h) => c.signals.includes(h.signal)) })).filter((c) => c.n > 0);
  const sectorList = useMemo(() => [...new Set(d.holdings.map((h) => h.sector).filter((s): s is string => !!s))].sort(), [d]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const allowed = new Set(SIGNAL_CHIPS.filter((c) => signals.has(c.key)).flatMap((c) => c.signals));
    const f = d.holdings.filter(
      (h) =>
        (!needle || h.label.toLowerCase().includes(needle) || h.ticker.toLowerCase().includes(needle)) &&
        (!signals.size || allowed.has(h.signal)) &&
        (!sectors.size || (h.sector !== null && sectors.has(h.sector))) &&
        (!conf.size || (h.confidence !== null && conf.has(h.confidence))),
    );
    return sortHoldings(f, sort.key, sort.dir, byTicker);
  }, [d, q, signals, sectors, conf, sort, byTicker]);

  if (d.holdings.length === 0)
    return <EmptyState title="No stock holdings yet">Import your Groww holdings on the Import page to see a signal and a Score Shape for each stock.</EmptyState>;

  const onSort = (k: SortKey) => setSort((s) => (s.key === k ? { key: k, dir: s.dir === 1 ? -1 : 1 } : { key: k, dir: isNumericSort(k) ? -1 : 1 }));
  const filtered = signals.size + sectors.size + conf.size > 0 || q.trim() !== "";

  return (
    <div className="space-y-4">
      {d.notes.map((n) => (
        <Alert key={n} tone="info">
          {n}
        </Alert>
      ))}
      <div className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card">
        <div className="flex flex-wrap items-end gap-3">
          <label className="w-full sm:w-60">
            <span className="mb-1 block text-xs font-medium text-fg-muted">Search</span>
            <span className="relative block">
              <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" />
              <input className={`${inputClass} pl-8`} placeholder="Name or ticker" value={q} onChange={(e) => setQ(e.target.value)} />
            </span>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium text-fg-muted">Sort by</span>
            <select className={inputClass} value={sort.key} onChange={(e) => setSort({ key: e.target.value as SortKey, dir: isNumericSort(e.target.value as SortKey) ? -1 : 1 })}>
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => setSort((s) => ({ ...s, dir: s.dir === 1 ? -1 : 1 }))}
            aria-label={sort.dir === 1 ? "Ascending: switch to descending" : "Descending: switch to ascending"}
            className="inline-flex h-[34px] items-center gap-1 rounded-control border border-border-strong bg-surface px-2.5 text-xs text-fg-muted hover:text-fg"
          >
            {sort.dir === 1 ? <ArrowUpNarrowWide aria-hidden className="size-4" /> : <ArrowDownWideNarrow aria-hidden className="size-4" />}
            {sort.dir === 1 ? "Low → high" : "High → low"}
          </button>
          <div className="ml-auto">
            <Segmented
              label="Layout"
              value={layout}
              onChange={onLayout}
              options={[
                { value: "cards", label: "Cards", icon: LayoutGrid },
                { value: "table", label: "Table", icon: Table2 },
              ]}
            />
          </div>
        </div>
        <ChipGroup label="Signal">
          {signalChips.map((c) => (
            <Chip key={c.key} pressed={signals.has(c.key)} onClick={() => setSignals((s) => toggle(s, c.key))} count={c.n}>
              {c.label}
            </Chip>
          ))}
        </ChipGroup>
        {sectorList.length > 1 && (
          <ChipGroup label="Sector">
            {sectorList.map((s) => (
              <Chip key={s} pressed={sectors.has(s)} onClick={() => setSectors((x) => toggle(x, s))} count={count((h) => h.sector === s)}>
                {s}
              </Chip>
            ))}
          </ChipGroup>
        )}
        <ChipGroup label="Confidence">
          {CONFIDENCE.filter((c) => count((h) => h.confidence === c.key) > 0).map((c) => (
            <Chip key={c.key} pressed={conf.has(c.key)} onClick={() => setConf((x) => toggle(x, c.key))} count={count((h) => h.confidence === c.key)}>
              {c.label}
            </Chip>
          ))}
        </ChipGroup>
        <p className="flex flex-wrap items-center gap-x-3 text-xs text-fg-subtle">
          <span>
            {rows.length} of {d.holdings.length} · {d.style_label} style (technical {Math.round(d.technical_weight * 100)}%), {d.risk_label} risk · weights are of the whole portfolio (
            {formatINR(d.total_value, 0)})
          </span>
          {filtered && (
            <button
              type="button"
              className="font-medium text-accent-text hover:underline"
              onClick={() => {
                setQ("");
                setSignals(new Set());
                setSectors(new Set());
                setConf(new Set());
              }}
            >
              Clear filters
            </button>
          )}
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No holdings match">Clear a filter or change the search.</EmptyState>
      ) : layout === "cards" ? (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((h) => (
            <li key={h.ticker}>
              <HoldingCard h={h} shape={byTicker.get(h.ticker)} linkQuery={linkQuery} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="rounded-card border border-border bg-surface p-4 shadow-card">
          <HoldingsTable rows={rows} shapes={byTicker} sort={sort} onSort={onSort} linkQuery={linkQuery} />
          <p className="mt-2 text-xs text-fg-subtle">Uses cached data only; run Refresh now in Settings → Data refresh first. Click a row for the full story.</p>
        </div>
      )}
    </div>
  );
}
