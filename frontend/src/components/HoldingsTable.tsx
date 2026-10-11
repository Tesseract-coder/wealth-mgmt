import { ArrowDown, ArrowUp, CircleAlert, OctagonAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { HoldingShape, HoldingSignal, SignalKey } from "../api/client";
import { formatINR, formatPct } from "../lib/format";
import { axesFromRecord, ScoreShape, SignalPill } from "./analysis";
import { FreshnessBadge } from "./MarketData";
import { ConfidenceTag } from "./SignalView";
import { Delta } from "./ui";

export type AxisKey = "valuation" | "growth" | "past" | "health" | "momentum" | "dividends";
export type SortKey =
  | "label"
  | "quantity"
  | "avg_price"
  | "price"
  | "pnl"
  | "pnl_pct"
  | "weight"
  | "composite"
  | "technical"
  | "fundamental"
  | "signal"
  | "confidence"
  | "shape"
  | `axis:${AxisKey}`;

export interface Sort {
  key: SortKey;
  dir: 1 | -1;
}

/** Most urgent first when sorting by signal. */
const SIGNAL_RANK: Record<SignalKey, number> = { sell: 0, reduce: 1, strong_buy: 2, buy: 3, hold: 4, no_signal: 5 };
const CONF_RANK = { high: 0, medium: 1, low: 2 } as const;

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "label", label: "Stock" },
  { key: "shape", label: "Shape", numeric: true },
  { key: "signal", label: "Signal" },
  { key: "confidence", label: "Confidence" },
  { key: "composite", label: "Score", numeric: true },
  { key: "technical", label: "Tech", numeric: true },
  { key: "fundamental", label: "Fund", numeric: true },
  { key: "quantity", label: "Qty", numeric: true },
  { key: "avg_price", label: "Avg price", numeric: true },
  { key: "price", label: "LTP", numeric: true },
  { key: "pnl", label: "P&L", numeric: true },
  { key: "weight", label: "Weight", numeric: true },
];

/** Numbers sort biggest first on the first click; names and signals A→Z / most urgent first. */
export const isNumericSort = (k: SortKey) => k.startsWith("axis:") || !!COLUMNS.find((c) => c.key === k)?.numeric || k === "pnl_pct";

function sortValue(h: HoldingSignal, k: SortKey, shape?: HoldingShape): number | string | null {
  if (k === "signal") return SIGNAL_RANK[h.signal];
  if (k === "confidence") return h.confidence ? CONF_RANK[h.confidence] : null;
  if (k === "label") return h.label.toLowerCase();
  if (k === "shape") return shape ? shape.total : null;
  if (k.startsWith("axis:")) return shape?.axes[k.slice(5)] ?? null;
  return h[k as keyof HoldingSignal] as number | null;
}

/** Sorted copy; missing values always go last, whichever the direction. Ties: biggest weight first. */
export function sortHoldings(rows: HoldingSignal[], key: SortKey, dir: 1 | -1, shapes: Map<string, HoldingShape> = new Map()): HoldingSignal[] {
  return [...rows].sort((a, b) => {
    const x = sortValue(a, key, shapes.get(a.ticker));
    const y = sortValue(b, key, shapes.get(b.ticker));
    if (x === null && y === null) return 0;
    if (x === null) return 1;
    if (y === null) return -1;
    const c = x < y ? -1 : x > y ? 1 : 0;
    return c * dir || (b.weight ?? 0) - (a.weight ?? 0);
  });
}

const score = (v: number | null) => (v === null ? "—" : v.toFixed(0));

/** Flags not already said by the rule (a severe flag is often the rule itself). */
export function extraFlags(h: HoldingSignal) {
  return h.flags.filter((f) => !h.rule.includes(f.text));
}

export function FlagLine({ f }: { f: HoldingSignal["flags"][number] }) {
  const Icon = f.severe ? OctagonAlert : CircleAlert;
  return (
    <div className={`flex items-start gap-1 text-xs ${f.severe ? "text-bad" : "text-caution"}`}>
      <Icon aria-hidden className="mt-px size-3.5 shrink-0" />
      <span>
        <span className="sr-only">{f.severe ? "Severe red flag: " : "Red flag: "}</span>
        {f.text}
      </span>
    </div>
  );
}

/**
 * Every holding as a table row: all the signal columns plus a small Score Shape. Header buttons
 * sort; a row click opens the stock.
 */
export function HoldingsTable({
  rows,
  shapes,
  sort,
  onSort,
  linkQuery = "",
}: {
  rows: HoldingSignal[];
  shapes: Map<string, HoldingShape>;
  sort: Sort;
  onSort: (k: SortKey) => void;
  linkQuery?: string;
}) {
  const navigate = useNavigate();
  const open = (t: string) => navigate(`/analysis/${encodeURIComponent(t)}${linkQuery}`);
  const totals = rows.reduce((a, h) => ({ value: a.value + (h.value ?? 0), pnl: a.pnl + (h.pnl ?? 0), invested: a.invested + (h.invested ?? 0) }), { value: 0, pnl: 0, invested: 0 });
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-fg-muted">
          <tr className="border-b border-border">
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                className={`py-2 pr-3 font-medium ${c.numeric ? "text-right" : ""}`}
              >
                <button type="button" onClick={() => onSort(c.key)} className="inline-flex items-center gap-0.5 hover:text-fg">
                  {c.label}
                  {sort.key === c.key && (sort.dir === 1 ? <ArrowUp aria-hidden className="size-3" /> : <ArrowDown aria-hidden className="size-3" />)}
                </button>
              </th>
            ))}
            <th className="py-2 pr-3 font-medium">Suggested</th>
            <th className="py-2 font-medium">Prices</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => {
            const s = shapes.get(h.ticker);
            const over = h.weight !== null && h.weight > h.max_weight;
            return (
              <tr key={h.ticker} onClick={() => open(h.ticker)} className="cursor-pointer border-b border-border align-top hover:bg-surface-2">
                <td className="py-2 pr-3">
                  <a
                    href={`/analysis/${encodeURIComponent(h.ticker)}${linkQuery}`}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      open(h.ticker);
                    }}
                    className="font-medium text-fg hover:underline"
                  >
                    {h.label}
                  </a>
                  <div className="font-mono text-xs text-fg-subtle">
                    {h.ticker}
                    {h.sector ? ` · ${h.sector}` : ""}
                  </div>
                  <div className="max-w-72 text-xs text-fg-muted">{h.rule}</div>
                  {extraFlags(h).map((f) => (
                    <FlagLine key={f.key} f={f} />
                  ))}
                </td>
                <td className="py-2 pr-3">
                  {s ? (
                    <span className="flex items-center justify-end gap-1.5">
                      <ScoreShape axes={axesFromRecord(s.axes)} total={s.total} maxTotal={s.max_total} step={s.step} size="sm" name={h.label} animate={false} />
                      <span className="whitespace-nowrap tabular-nums text-fg">
                        {s.total}
                        <span className="text-fg-subtle">/{s.max_total}</span>
                      </span>
                    </span>
                  ) : (
                    <span className="block text-right text-fg-subtle">—</span>
                  )}
                </td>
                <td className="py-2 pr-3">
                  <SignalPill signal={h.signal} label={h.signal_label} />
                </td>
                <td className="py-2 pr-3">
                  <ConfidenceTag c={h.confidence} />
                </td>
                <td className="py-2 pr-3 text-right font-medium">{score(h.composite)}</td>
                <td className="py-2 pr-3 text-right">{score(h.technical)}</td>
                <td className="py-2 pr-3 text-right">{score(h.fundamental)}</td>
                <td className="py-2 pr-3 text-right">{h.quantity ?? "—"}</td>
                <td className="whitespace-nowrap py-2 pr-3 text-right">{formatINR(h.avg_price)}</td>
                <td className="whitespace-nowrap py-2 pr-3 text-right">{formatINR(h.price)}</td>
                <td className="whitespace-nowrap py-2 pr-3 text-right">
                  <Delta value={h.pnl} format="inr" />
                  <div className="text-xs text-fg-muted">{h.pnl_pct === null ? "" : formatPct(h.pnl_pct)}</div>
                </td>
                <td className={`py-2 pr-3 text-right ${over ? "font-semibold text-caution" : ""}`}>
                  {h.weight === null ? "—" : `${(h.weight * 100).toFixed(1)}%`}
                  {over && <div className="text-xs font-normal">max {Math.round(h.max_weight * 100)}%</div>}
                </td>
                <td className="py-2 pr-3 text-xs text-fg-muted">{h.rebalance.action === "none" ? "—" : h.rebalance.text}</td>
                <td className="py-2">
                  <FreshnessBadge f={h.price_freshness} />
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="text-sm font-medium">
            <td className="py-2 pr-3" colSpan={10}>
              Shown: value {formatINR(totals.value, 0)}, invested {formatINR(totals.invested, 0)}
            </td>
            <td className="whitespace-nowrap py-2 pr-3 text-right">
              <Delta value={totals.pnl} format="inr" />
            </td>
            <td colSpan={3} />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
