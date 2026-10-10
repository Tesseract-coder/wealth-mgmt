import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { HoldingSignal, HoldingSignals, SignalKey } from "../api/client";
import { formatINR } from "../lib/format";
import { FreshnessBadge } from "./MarketData";
import { ConfidenceTag, SignalPill } from "./SignalView";
import { Alert, Card, inputClass } from "./ui";

type SortKey = "label" | "quantity" | "avg_price" | "price" | "pnl" | "pnl_pct" | "weight" | "composite" | "technical" | "fundamental" | "signal" | "confidence";

/** Most urgent first when sorting by signal. */
const SIGNAL_RANK: Record<SignalKey, number> = { sell: 0, reduce: 1, strong_buy: 2, buy: 3, hold: 4, no_signal: 5 };
const CONF_RANK = { high: 0, medium: 1, low: 2 } as const;

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "label", label: "Stock" },
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

function sortValue(h: HoldingSignal, k: SortKey): number | string | null {
  if (k === "signal") return SIGNAL_RANK[h.signal];
  if (k === "confidence") return h.confidence ? CONF_RANK[h.confidence] : null;
  if (k === "label") return h.label.toLowerCase();
  return h[k];
}

/** Sorted copy; missing values always go last, whichever the direction. */
export function sortHoldings(rows: HoldingSignal[], key: SortKey, dir: 1 | -1): HoldingSignal[] {
  return [...rows].sort((a, b) => {
    const x = sortValue(a, key);
    const y = sortValue(b, key);
    if (x === null && y === null) return 0;
    if (x === null) return 1;
    if (y === null) return -1;
    const c = x < y ? -1 : x > y ? 1 : 0;
    return c * dir || (b.weight ?? 0) - (a.weight ?? 0);
  });
}

const score = (v: number | null) => (v === null ? "—" : v.toFixed(0));
const sign = (v: number | null) => (v === null ? "" : v >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400");

export function HoldingsTable({ d, linkQuery = "" }: { d: HoldingSignals; linkQuery?: string }) {
  const navigate = useNavigate();
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "signal", dir: 1 });
  const [q, setQ] = useState("");
  const [signal, setSignal] = useState<SignalKey | "">("");
  const [sector, setSector] = useState("");
  const sectors = useMemo(() => [...new Set(d.holdings.map((h) => h.sector).filter((s): s is string => !!s))].sort(), [d]);
  const signals = useMemo(() => [...new Map(d.holdings.map((h) => [h.signal, h.signal_label])).entries()], [d]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const f = d.holdings.filter(
      (h) =>
        (!needle || h.label.toLowerCase().includes(needle) || h.ticker.toLowerCase().includes(needle)) &&
        (!signal || h.signal === signal) &&
        (!sector || h.sector === sector),
    );
    return sortHoldings(f, sort.key, sort.dir);
  }, [d, q, signal, sector, sort]);

  if (d.holdings.length === 0)
    return <Alert tone="info">No stock holdings yet. Import your Groww file on the Import page.</Alert>;

  const click = (k: SortKey) => setSort((s) => (s.key === k ? { key: k, dir: s.dir === 1 ? -1 : 1 } : { key: k, dir: COLUMNS.find((c) => c.key === k)?.numeric ? -1 : 1 }));
  const open = (t: string) => navigate(`/analysis/${encodeURIComponent(t)}${linkQuery}`);
  const totals = rows.reduce((a, h) => ({ value: a.value + (h.value ?? 0), pnl: a.pnl + (h.pnl ?? 0), invested: a.invested + (h.invested ?? 0) }), { value: 0, pnl: 0, invested: 0 });
  return (
    <div className="space-y-4">
      {d.notes.map((n) => (
        <Alert key={n} tone="info">
          {n}
        </Alert>
      ))}
      <Card title={`${d.style_label} style (technical ${Math.round(d.technical_weight * 100)}%) · ${d.risk_label} risk`}>
        <div className="mb-3 flex flex-wrap items-end gap-2 text-sm">
          <label className="w-56">
            <span className="mb-1 block text-slate-500">Search</span>
            <input className={inputClass} placeholder="Name or ticker" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          <label>
            <span className="mb-1 block text-slate-500">Signal</span>
            <select className={inputClass} value={signal} onChange={(e) => setSignal(e.target.value as SignalKey | "")}>
              <option value="">All signals</option>
              {signals.map(([k, l]) => (
                <option key={k} value={k}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="mb-1 block text-slate-500">Sector</span>
            <select className={inputClass} value={sector} onChange={(e) => setSector(e.target.value)}>
              <option value="">All sectors</option>
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <span className="ml-auto text-xs text-slate-500">
            {rows.length} of {d.holdings.length} · weights are of the whole portfolio ({formatINR(d.total_value, 0)})
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c.key} aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"} className={`py-1 pr-2 ${c.numeric ? "text-right" : ""}`}>
                    <button type="button" onClick={() => click(c.key)} className="uppercase hover:underline">
                      {c.label}
                      {sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                    </button>
                  </th>
                ))}
                <th className="pr-2">Suggested</th>
                <th>Prices</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h) => (
                <tr
                  key={h.ticker}
                  onClick={() => open(h.ticker)}
                  className="cursor-pointer border-t border-slate-100 align-top hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                >
                  <td className="py-1.5 pr-2">
                    <a
                      href={`/analysis/${encodeURIComponent(h.ticker)}${linkQuery}`}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        open(h.ticker);
                      }}
                      className="font-medium underline"
                    >
                      {h.label}
                    </a>
                    <div className="font-mono text-xs text-slate-500">
                      {h.ticker}
                      {h.sector ? ` · ${h.sector}` : ""}
                    </div>
                    <div className="max-w-72 text-xs text-slate-600 dark:text-slate-400">{h.rule}</div>
                    {/* A severe flag is often the rule itself; don't repeat it. */}
                    {h.flags.filter((f) => !h.rule.includes(f.text)).map((f) => (
                      <div key={f.key} className={`max-w-72 text-xs ${f.severe ? "text-red-700 dark:text-red-400" : "text-amber-800 dark:text-amber-300"}`}>
                        {f.severe ? "⛔" : "⚠"} {f.text}
                      </div>
                    ))}
                  </td>
                  <td className="pr-2">
                    <SignalPill signal={h.signal} label={h.signal_label} />
                  </td>
                  <td className="pr-2">
                    <ConfidenceTag c={h.confidence} />
                  </td>
                  <td className="pr-2 text-right font-medium tabular-nums">{score(h.composite)}</td>
                  <td className="pr-2 text-right tabular-nums">{score(h.technical)}</td>
                  <td className="pr-2 text-right tabular-nums">{score(h.fundamental)}</td>
                  <td className="pr-2 text-right tabular-nums">{h.quantity ?? "—"}</td>
                  <td className="pr-2 text-right tabular-nums whitespace-nowrap">{formatINR(h.avg_price)}</td>
                  <td className="pr-2 text-right tabular-nums whitespace-nowrap">{formatINR(h.price)}</td>
                  <td className={`pr-2 text-right tabular-nums whitespace-nowrap ${sign(h.pnl)}`}>
                    {formatINR(h.pnl, 0)}
                    <div className="text-xs">{h.pnl_pct === null ? "" : `${h.pnl_pct > 0 ? "+" : ""}${h.pnl_pct.toFixed(1)}%`}</div>
                  </td>
                  <td className={`pr-2 text-right tabular-nums ${h.weight !== null && h.weight > h.max_weight ? "font-semibold text-amber-800 dark:text-amber-300" : ""}`}>
                    {h.weight === null ? "—" : `${(h.weight * 100).toFixed(1)}%`}
                    {h.weight !== null && h.weight > h.max_weight && <div className="text-xs font-normal">max {Math.round(h.max_weight * 100)}%</div>}
                  </td>
                  <td className="pr-2 text-xs">{h.rebalance.action === "none" ? "—" : h.rebalance.text}</td>
                  <td>
                    <FreshnessBadge f={h.price_freshness} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-slate-300 text-sm font-medium dark:border-slate-700">
                <td className="py-1.5 pr-2" colSpan={9}>
                  Shown: value {formatINR(totals.value, 0)}, invested {formatINR(totals.invested, 0)}
                </td>
                <td className={`pr-2 text-right tabular-nums ${sign(totals.pnl)}`}>{formatINR(totals.pnl, 0)}</td>
                <td colSpan={3} />
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">Uses cached data only; run Refresh now in Settings → Data refresh first. Click a row for the chart and full reasons.</p>
      </Card>
    </div>
  );
}
