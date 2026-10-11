import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { fundApi, type FundReport, type FundSignalKey, type MFHoldingsAnalysis, type RiskStats } from "../api/client";
import { FundCharts } from "../charts/FundCharts";
import { formatDate, formatINR } from "../lib/format";
import { FreshnessBadge } from "./MarketData";
import { Alert, Button, Card, inputClass } from "./ui";
import { FundSignalPill } from "./analysis/SignalPill";

/** Kept here for existing imports; the pill now lives in components/analysis. */
export { FundSignalPill };

const pct = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`);
const PLAN: Record<string, string> = { direct: "Direct", regular: "Regular" };

export function FundHoldings() {
  const q = useQuery({ queryKey: ["mf-holdings"], queryFn: fundApi.holdings });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card>Analysing your funds…</Card>;
  return <FundHoldingsBody d={q.data} />;
}

export function FundHoldingsBody({ d }: { d: MFHoldingsAnalysis }) {
  if (d.funds.length === 0)
    return (
      <Alert tone="info">
        No mutual funds yet. <Link className="underline" to="/import">Import your Groww MF file or CAS</Link>.
      </Alert>
    );
  const rank: Record<FundSignalKey, number> = { switch: 0, review: 1, continue: 2, no_signal: 3 };
  const funds = [...d.funds].sort((a, b) => rank[a.signal] - rank[b.signal]);
  return (
    <div className="space-y-4">
      {d.warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      <Card title="Your funds">
        <p className="mb-3 text-sm text-slate-500">Cached NAVs only: run Refresh now in Settings → Data refresh first. Returns are a year (CAGR).</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1 pr-2">Fund</th>
                <th className="pr-2">Signal</th>
                <th className="pr-2">Plan</th>
                <th className="pr-2 text-right">Value</th>
                <th className="pr-2 text-right">Your XIRR</th>
                <th className="pr-2 text-right">1y</th>
                <th className="pr-2 text-right">3y</th>
                <th className="pr-2 text-right">5y</th>
                <th className="pr-2">Why</th>
                <th>NAV</th>
              </tr>
            </thead>
            <tbody>
              {funds.map((f) => {
                const r = Object.fromEntries(f.returns.map((x) => [x.years, x]));
                return (
                  <tr key={f.code} className="border-t border-slate-100 align-top dark:border-slate-800">
                    <td className="py-1 pr-2">
                      <Link className="underline" to={`/mutual-funds/${f.code}`}>
                        {f.name}
                      </Link>
                      <div className="text-xs text-slate-500">
                        {f.category ?? "—"} · {f.benchmark ? `vs ${f.benchmark.label}` : "no benchmark"}
                      </div>
                    </td>
                    <td className="pr-2">
                      <FundSignalPill signal={f.signal} label={f.signal_label} />
                    </td>
                    <td className="pr-2">{f.plan ? PLAN[f.plan] ?? f.plan : "—"}</td>
                    <td className="pr-2 text-right tabular-nums">{formatINR(f.holding?.value, 0)}</td>
                    <td className="pr-2 text-right tabular-nums" title={f.holding?.xirr_basis}>
                      {pct(f.holding?.xirr)}
                      {f.holding?.xirr_approximate && "*"}
                    </td>
                    {[1, 3, 5].map((y) => (
                      <td key={y} className="pr-2 text-right tabular-nums">
                        {pct(r[y]?.fund)}
                        <div className="text-xs text-slate-500">{r[y]?.benchmark != null ? `idx ${pct(r[y]?.benchmark)}` : ""}</div>
                      </td>
                    ))}
                    <td className="pr-2 text-xs">{f.rule}</td>
                    <td>
                      <FreshnessBadge f={f.nav_freshness} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">* approximate XIRR (one lump sum on the first purchase date assumed). idx = benchmark.</p>
      </Card>
      <OverlapMatrix d={d} />
    </div>
  );
}

function OverlapMatrix({ d }: { d: MFHoldingsAnalysis }) {
  const o = d.overlap;
  if (o.codes.length < 2) return null;
  const short = (n: string) => n.replace(/ - (Direct|Regular) Plan.*$/i, "").slice(0, 28);
  return (
    <Card title={`Portfolio overlap between your funds${o.approximate ? " (approximate)" : ""}`}>
      <p className="mb-2 text-xs text-slate-500">
        Share of holdings two funds have in common (Σ of the smaller weight in each shared stock). Upload each fund&apos;s portfolio under Import → Fund
        portfolios; blank cells have no data.
      </p>
      <div className="overflow-x-auto">
        <table className="text-xs">
          <thead>
            <tr>
              <th />
              {o.names.map((n) => (
                <th key={n} className="px-1 text-left font-normal text-slate-500">
                  {short(n)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {o.pct.map((row, i) => (
              <tr key={o.codes[i]}>
                <th className="pr-2 text-left font-normal">{short(o.names[i] ?? "")}</th>
                {row.map((v, j) => (
                  <td
                    key={o.codes[j]}
                    className={`px-2 py-1 text-center tabular-nums ${v !== null && i !== j && v > 50 ? "font-semibold text-amber-800 dark:text-amber-300" : ""}`}
                  >
                    {v === null ? "" : i === j ? "—" : `${v.toFixed(0)}%`}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function RiskRow({ label, r }: { label: string; r: RiskStats | null }) {
  return (
    <tr className="border-t border-slate-100 dark:border-slate-800">
      <td className="py-1 pr-2">{label}</td>
      <td className="pr-2 text-right tabular-nums">{r ? `${r.volatility.toFixed(1)}%` : "—"}</td>
      <td className="pr-2 text-right tabular-nums">{r?.sharpe?.toFixed(2) ?? "—"}</td>
      <td className="pr-2 text-right tabular-nums">{r?.sortino?.toFixed(2) ?? "—"}</td>
      <td className="pr-2 text-right tabular-nums">{r ? `${r.max_drawdown.toFixed(1)}%` : "—"}</td>
      <td className="text-xs text-slate-500">{r ? `${formatDate(r.drawdown_peak)} → ${formatDate(r.drawdown_trough)}` : ""}</td>
    </tr>
  );
}

export function FundReportView({ code }: { code: string }) {
  const q = useQuery({ queryKey: ["mf", code], queryFn: () => fundApi.report(code) });
  if (q.isError) return <Alert tone="error">{q.error.message}</Alert>;
  if (!q.data) return <Card>Analysing… (the first look downloads the NAV history and benchmark)</Card>;
  return <FundReportBody f={q.data} charts={<FundCharts code={code} />} />;
}

export function FundReportBody({ f, charts }: { f: FundReport; charts?: ReactNode }) {
  const h = f.holding;
  return (
    <div className="space-y-4">
      {f.fetch_errors.map((e) => (
        <Alert key={e} tone="warning">
          Could not refresh: {e}. Showing cached data where available.
        </Alert>
      ))}
      <Card
        title={f.name}
        actions={
          <span className="flex items-center gap-2 text-sm text-slate-500">
            NAV {f.nav != null ? formatINR(f.nav, 4) : "—"} on {formatDate(f.nav_date)} <FreshnessBadge f={f.nav_freshness} />
          </span>
        }
      >
        <p className="text-sm text-slate-500">
          {f.amc ?? ""} · {f.category ?? "category unknown"} · {f.plan ? PLAN[f.plan] ?? f.plan : "plan unknown"} plan · AMFI {f.code}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="text-lg">
            <FundSignalPill signal={f.signal} label={f.signal_label} />
          </span>
          <span className="text-sm">
            <span className="font-medium">Why: </span>
            {f.rule}.
          </span>
        </div>
        <ul className="mt-3 space-y-1 text-sm">
          {f.reasons.map((r) => (
            <li key={r.text}>
              <span className={r.direction === "bullish" ? "text-emerald-700 dark:text-emerald-400" : r.direction === "bearish" ? "text-red-700 dark:text-red-400" : "text-slate-500"}>
                {r.direction === "bullish" ? "▲" : r.direction === "bearish" ? "▼" : "●"}
              </span>{" "}
              {r.text}
            </li>
          ))}
        </ul>
        {f.notes.map((n) => (
          <p key={n} className="mt-2 text-xs text-slate-500">
            {n}
          </p>
        ))}
      </Card>

      {charts}

      {h && (
        <Card title="Your investment">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-slate-500">Units</dt>
              <dd className="tabular-nums">{h.units}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Invested · value</dt>
              <dd className="tabular-nums">
                {formatINR(h.invested, 0)} · {formatINR(h.value, 0)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Gain</dt>
              <dd className="tabular-nums">{formatINR(h.pnl, 0)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Your XIRR</dt>
              <dd className="tabular-nums">{pct(h.xirr)}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-slate-500">{h.xirr_basis}</p>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`Returns vs ${f.benchmark?.label ?? "benchmark"}`}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1">Period</th>
                <th className="text-right">Fund</th>
                <th className="text-right">Benchmark</th>
                <th className="text-right">Difference</th>
              </tr>
            </thead>
            <tbody>
              {f.returns.map((r) => (
                <tr key={r.years} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1">{r.years} year{r.years > 1 ? "s" : ""} (a year)</td>
                  <td className="text-right tabular-nums">{pct(r.fund)}</td>
                  <td className="text-right tabular-nums">{pct(r.benchmark)}</td>
                  <td className="text-right tabular-nums">{r.fund != null && r.benchmark != null ? `${(r.fund - r.benchmark).toFixed(1)} pp` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {f.rolling.length > 0 && (
            <table className="mt-3 w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-1">Rolling</th>
                  <th className="text-right">Fund avg</th>
                  <th className="text-right">Index avg</th>
                  <th className="text-right">Beat it</th>
                  <th className="text-right">Range vs index</th>
                </tr>
              </thead>
              <tbody>
                {f.rolling.map((r) => (
                  <tr key={r.years} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1">
                      {r.years}y ({r.windows} windows)
                    </td>
                    <td className="text-right tabular-nums">{r.fund_avg.toFixed(1)}%</td>
                    <td className="text-right tabular-nums">{r.bench_avg.toFixed(1)}%</td>
                    <td className="text-right tabular-nums">{Math.round(r.beat_share * 100)}%</td>
                    <td className="text-right tabular-nums text-xs">
                      {r.worst_excess.toFixed(1)} to {r.best_excess > 0 ? "+" : ""}
                      {r.best_excess.toFixed(1)} pp
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Risk">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="py-1" />
                <th className="text-right">Volatility</th>
                <th className="text-right">Sharpe</th>
                <th className="text-right">Sortino</th>
                <th className="text-right">Max fall</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <RiskRow label="Fund" r={f.risk} />
              {f.benchmark && <RiskRow label={f.benchmark.label} r={f.benchmark_risk} />}
            </tbody>
          </table>
          {f.risk && (
            <p className="mt-2 text-xs text-slate-500">
              Over {f.risk.years} years to {formatDate(f.risk.end)}, annualised. Sharpe and Sortino use the risk-free rate in the config.
            </p>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Cost">
          <div className="space-y-2 text-sm">
            {f.plan === "regular" && (
              <p>
                Regular plan.{" "}
                {f.direct_twin ? (
                  <>
                    Direct plan: <Link className="underline" to={`/mutual-funds/${f.direct_twin.code}`}>{f.direct_twin.name}</Link>
                    {f.direct_gap_pp != null && ` returned ${f.direct_gap_pp > 0 ? "+" : ""}${f.direct_gap_pp.toFixed(2)} pp a year more (${f.direct_gap_basis.toLowerCase()}).`}
                  </>
                ) : (
                  f.direct_gap_basis
                )}
              </p>
            )}
            <ExpenseRatio f={f} />
          </div>
        </Card>
        <Card title="Overlap with your other funds">
          {f.overlaps.length === 0 ? (
            <p className="text-sm text-slate-500">
              No overlap data. Upload this fund&apos;s portfolio (and your other funds&apos;) under Import → Fund portfolios.
            </p>
          ) : (
            <ul className="space-y-1 text-sm">
              {f.overlaps.map((o) => (
                <li key={o.code}>
                  {o.pct.toFixed(0)}% with {o.name} ({o.common} common holdings){o.approximate && <span className="text-xs text-slate-500"> · approximate: {o.note}</span>}
                </li>
              ))}
            </ul>
          )}
          {f.segment_peers.length > 0 && <p className="mt-2 text-xs text-slate-500">Same segment: {f.segment_peers.join(", ")}</p>}
        </Card>
      </div>

      {f.unavailable.length > 0 && (
        <p className="text-xs text-slate-500">
          <span className="font-medium">Not available:</span> {f.unavailable.join("; ")}
        </p>
      )}
    </div>
  );
}

function ExpenseRatio({ f }: { f: FundReport }) {
  const qc = useQueryClient();
  const [v, setV] = useState(f.expense_ratio_pct?.toString() ?? "");
  const save = useMutation({
    mutationFn: (pctValue: number | null) => fundApi.setExpenseRatio(f.code, pctValue),
    onSuccess: (r) => {
      qc.setQueryData(["mf", f.code], r);
      void qc.invalidateQueries({ queryKey: ["mf-holdings"] });
    },
  });
  const num = v.trim() === "" ? null : Number(v);
  const valid = num === null || (Number.isFinite(num) && num >= 0 && num <= 5);
  return (
    <div>
      <label className="block text-sm">
        <span className="text-slate-500">Expense ratio (TER %, from the fund&apos;s factsheet; no free source publishes it)</span>
        <span className="mt-1 flex gap-2">
          <input className={`${inputClass} w-28`} inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} placeholder="e.g. 0.65" />
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate(num)}>
            Save
          </Button>
        </span>
      </label>
      {!valid && <p className="text-xs text-red-700">Enter a percentage between 0 and 5.</p>}
      {save.isError && <Alert tone="error">{save.error.message}</Alert>}
    </div>
  );
}
