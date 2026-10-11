import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, LayoutGrid, Minus, Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { checksApi, fundApi, type FundChecks, type FundReport, type FundSignalKey, type MFHoldingsAnalysis, type RiskStats } from "../api/client";
import { FundCharts } from "../charts/FundCharts";
import { formatDate, formatINR, formatPct } from "../lib/format";
import { axesFromSections, CheckList, RewardsRisks, ScoreShape, SectionHeader } from "./analysis";
import { FundSignalPill } from "./analysis/SignalPill";
import { FreshnessBadge } from "./MarketData";
import { Alert, Badge, Button, Card, Delta, EmptyState, ErrorState, inputClass, Loading, Segmented, Skeleton, SkeletonText, Stat } from "./ui";

/** Kept here for existing imports; the pill now lives in components/analysis. */
export { FundSignalPill };

const pct = (v: number | null | undefined) => (v == null ? "—" : formatPct(v));
const PLAN: Record<string, string> = { direct: "Direct", regular: "Regular" };
const RANK: Record<FundSignalKey, number> = { switch: 0, review: 1, continue: 2, no_signal: 3 };
const shortName = (n: string) => n.replace(/ - (Direct|Regular) Plan.*$/i, "");

/** Direct is cheaper, so it reads as good; Regular as a caution. Always with the word. */
export function PlanBadge({ plan }: { plan: string | null }) {
  if (!plan) return <Badge>Plan unknown</Badge>;
  return <Badge tone={plan === "direct" ? "good" : plan === "regular" ? "caution" : "neutral"}>{PLAN[plan] ?? plan} plan</Badge>;
}

/** The fund's Risk axis in words: how bumpy against its benchmark. */
export function riskGrade(checks?: FundChecks): string {
  const s = checks?.sections.find((x) => x.key === "risk")?.score;
  if (s == null) return "Risk: not enough data";
  return s >= 5 ? "Lower risk than its benchmark" : s >= 3 ? "About as risky as its benchmark" : "Riskier than its benchmark";
}

/** The longest return period with both figures, as "3y +12.4% vs index +8.5%". */
function headlineReturn(f: FundReport) {
  const r = [...f.returns].reverse().find((x) => x.fund != null && x.benchmark != null && x.years <= 3) ?? f.returns.find((x) => x.fund != null);
  return r ?? null;
}

// ------------------------------------------------------------------------------------ list

export function FundHoldings() {
  const q = useQuery({ queryKey: ["mf-holdings"], queryFn: fundApi.holdings });
  const checks = useQuery({ queryKey: ["mf-checks"], queryFn: checksApi.funds, enabled: q.isSuccess });
  if (q.isError) return <ErrorState title="Couldn't analyse your funds" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data)
    return (
      <Loading label="your funds">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-64 w-full" />
          ))}
        </div>
      </Loading>
    );
  return <FundHoldingsBody d={q.data} checks={checks.data?.funds} />;
}

function FundCard({ f, c }: { f: FundReport; c?: FundChecks }) {
  const r = headlineReturn(f);
  const ahead = r?.fund != null && r.benchmark != null ? r.fund - r.benchmark : null;
  return (
    <article className="relative flex h-full flex-col gap-3 rounded-card border border-border bg-surface p-4 shadow-card hover:border-border-strong">
      <header className="min-w-0">
        <h3 className="text-sm font-semibold text-fg">
          <Link to={`/mutual-funds/${f.code}`} className="after:absolute after:inset-0 after:rounded-card hover:underline">
            {f.name}
          </Link>
        </h3>
        <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-fg-subtle">
          <PlanBadge plan={f.plan} />
          <span className="truncate">{f.category ?? "Category unknown"}</span>
        </p>
      </header>
      <div className="flex items-center gap-3">
        {c ? (
          <div className="relative z-10 shrink-0">
            <ScoreShape axes={axesFromSections(c.sections)} total={c.total} maxTotal={c.max_total} step={c.step} size="md" name={f.name} animate={false} />
          </div>
        ) : (
          <Skeleton className="size-[116px] shrink-0" />
        )}
        <dl className="min-w-0 space-y-2 text-sm">
          <div>
            <dt className="sr-only">Signal</dt>
            <dd>
              <FundSignalPill signal={f.signal} label={f.signal_label} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">{r ? `${r.years}y return a year` : "Return"}</dt>
            <dd className="text-fg">
              <span className="font-semibold">{pct(r?.fund)}</span>
              {r?.benchmark != null && <span className="text-xs text-fg-muted"> vs index {pct(r.benchmark)}</span>}
            </dd>
            {ahead !== null && (
              <dd className={`flex items-center gap-0.5 text-xs ${ahead >= 0 ? "text-good" : "text-bad"}`}>
                {ahead >= 0 ? <ArrowUpRight aria-hidden className="size-3.5" /> : <ArrowDownRight aria-hidden className="size-3.5" />}
                {Math.abs(ahead).toFixed(1)} pp {ahead >= 0 ? "ahead" : "behind"}
              </dd>
            )}
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Value</dt>
            <dd className="text-fg">{formatINR(f.holding?.value, 0)}</dd>
          </div>
        </dl>
      </div>
      <ul className="space-y-1 border-t border-border pt-2 text-xs text-fg-muted">
        <li>{riskGrade(c)}</li>
        <li>{f.expense_ratio_pct != null ? `Expense ratio ${f.expense_ratio_pct.toFixed(2)}%` : "Expense ratio not entered"}</li>
      </ul>
    </article>
  );
}

export function FundHoldingsBody({ d, checks = [] }: { d: MFHoldingsAnalysis; checks?: FundChecks[] }) {
  const [layout, setLayout] = useState<"cards" | "table">("cards");
  if (d.funds.length === 0)
    return (
      <EmptyState
        title="No mutual funds yet"
        action={
          <Link className="text-sm font-medium text-accent-text underline" to="/import">
            Import your Groww MF file or CAS
          </Link>
        }
      >
        Import your funds to see a Continue / Review / Switch signal and a Score Shape for each.
      </EmptyState>
    );
  const byCode = new Map(checks.map((c) => [c.code, c]));
  const funds = [...d.funds].sort((a, b) => RANK[a.signal] - RANK[b.signal]);
  return (
    <div className="space-y-4">
      {d.warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-fg-subtle">Cached NAVs only: run Refresh now in Settings → Data refresh first. Returns are a year (CAGR). Most urgent first.</p>
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
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
          {funds.map((f) => (
            <li key={f.code}>
              <FundCard f={f} c={byCode.get(f.code)} />
            </li>
          ))}
        </ul>
      ) : (
        <Card>
          <FundTable funds={funds} byCode={byCode} />
        </Card>
      )}
      <OverlapMatrix d={d} />
    </div>
  );
}

function FundTable({ funds, byCode }: { funds: FundReport[]; byCode: Map<string, FundChecks> }) {
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-fg-muted">
            <tr className="border-b border-border">
              <th className="py-2 pr-3 font-medium">Fund</th>
              <th className="py-2 pr-3 text-right font-medium">Shape</th>
              <th className="py-2 pr-3 font-medium">Signal</th>
              <th className="py-2 pr-3 font-medium">Plan</th>
              <th className="py-2 pr-3 text-right font-medium">Value</th>
              <th className="py-2 pr-3 text-right font-medium">Your XIRR</th>
              <th className="py-2 pr-3 text-right font-medium">1y</th>
              <th className="py-2 pr-3 text-right font-medium">3y</th>
              <th className="py-2 pr-3 text-right font-medium">5y</th>
              <th className="py-2 pr-3 font-medium">Why</th>
              <th className="py-2 font-medium">NAV</th>
            </tr>
          </thead>
          <tbody>
            {funds.map((f) => {
              const r = Object.fromEntries(f.returns.map((x) => [x.years, x]));
              const c = byCode.get(f.code);
              return (
                <tr key={f.code} className="border-b border-border align-top">
                  <td className="py-2 pr-3">
                    <Link className="font-medium text-fg hover:underline" to={`/mutual-funds/${f.code}`}>
                      {f.name}
                    </Link>
                    <div className="text-xs text-fg-subtle">
                      {f.category ?? "—"} · {f.benchmark ? `vs ${f.benchmark.label}` : "no benchmark"}
                    </div>
                  </td>
                  <td className="py-2 pr-3">
                    {c ? (
                      <span className="flex items-center justify-end gap-1.5">
                        <ScoreShape axes={axesFromSections(c.sections)} total={c.total} maxTotal={c.max_total} step={c.step} size="sm" name={f.name} animate={false} />
                        <span className="whitespace-nowrap text-fg">
                          {c.total}
                          <span className="text-fg-subtle">/{c.max_total}</span>
                        </span>
                      </span>
                    ) : (
                      <span className="block text-right text-fg-subtle">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <FundSignalPill signal={f.signal} label={f.signal_label} />
                  </td>
                  <td className="py-2 pr-3">{f.plan ? PLAN[f.plan] ?? f.plan : "—"}</td>
                  <td className="py-2 pr-3 text-right">{formatINR(f.holding?.value, 0)}</td>
                  <td className="py-2 pr-3 text-right" title={f.holding?.xirr_basis}>
                    {pct(f.holding?.xirr)}
                    {f.holding?.xirr_approximate && "*"}
                  </td>
                  {[1, 3, 5].map((y) => (
                    <td key={y} className="py-2 pr-3 text-right">
                      {pct(r[y]?.fund)}
                      <div className="text-xs text-fg-subtle">{r[y]?.benchmark != null ? `idx ${pct(r[y]?.benchmark)}` : ""}</div>
                    </td>
                  ))}
                  <td className="py-2 pr-3 text-xs text-fg-muted">{f.rule}</td>
                  <td className="py-2">
                    <FreshnessBadge f={f.nav_freshness} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-fg-subtle">* approximate XIRR (one lump sum on the first purchase date assumed). idx = benchmark.</p>
    </>
  );
}

/** The biggest overlaps in words, e.g. "Fund A and Fund B share 62% of holdings." */
export function overlapCallouts(o: MFHoldingsAnalysis["overlap"], min = 30, n = 3): string[] {
  const pairs: { a: string; b: string; v: number }[] = [];
  o.pct.forEach((row, i) =>
    row.forEach((v, j) => {
      if (j > i && v !== null && v >= min) pairs.push({ a: shortName(o.names[i] ?? ""), b: shortName(o.names[j] ?? ""), v });
    }),
  );
  return pairs
    .sort((x, y) => y.v - x.v)
    .slice(0, n)
    .map((p) => `${p.a} and ${p.b} share ${p.v.toFixed(0)}% of holdings${p.v > 50 ? ": owning both adds little variety" : ""}.`);
}

function OverlapMatrix({ d }: { d: MFHoldingsAnalysis }) {
  const o = d.overlap;
  if (o.codes.length < 2) return null;
  const short = (n: string) => shortName(n).slice(0, 28);
  const callouts = overlapCallouts(o);
  const hasData = o.pct.some((row, i) => row.some((v, j) => i !== j && v !== null));
  return (
    <Card title={`Overlap between your funds${o.approximate ? " (approximate)" : ""}`} description="Share of holdings two funds have in common. Darker cells overlap more.">
      {!hasData ? (
        <EmptyState
          title="No overlap data yet"
          action={
            <Link className="text-sm font-medium text-accent-text underline" to="/import">
              Upload fund portfolios
            </Link>
          }
        >
          Upload each fund&apos;s monthly portfolio file under Import → Fund portfolios to see which of your funds own the same stocks.
        </EmptyState>
      ) : callouts.length > 0 ? (
        <ul className="mb-3 space-y-1 text-sm text-fg">
          {callouts.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      ) : (
        <p className="mb-3 text-sm text-fg">No two funds share more than 30% of their holdings.</p>
      )}
      {hasData && (
      <div className="overflow-x-auto">
        <table className="text-xs">
          <thead>
            <tr>
              <th />
              {o.names.map((n) => (
                <th key={n} className="max-w-28 px-1 pb-1 text-left align-bottom font-normal text-fg-subtle">
                  {short(n)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {o.pct.map((row, i) => (
              <tr key={o.codes[i]}>
                <th className="pr-2 text-left font-normal text-fg-muted">{short(o.names[i] ?? "")}</th>
                {row.map((v, j) => (
                  <td
                    key={o.codes[j]}
                    className={`h-9 min-w-14 border border-surface px-2 text-center ${v !== null && i !== j && v > 50 ? "font-semibold text-fg" : "text-fg-muted"}`}
                    style={v !== null && i !== j ? { backgroundColor: `color-mix(in srgb, var(--chart-4) ${Math.round(Math.min(100, v) * 0.7)}%, var(--surface-2))` } : { backgroundColor: "var(--surface-2)" }}
                  >
                    {v === null ? "" : i === j ? "—" : `${v.toFixed(0)}%`}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
      {hasData && <p className="mt-2 text-xs text-fg-subtle">Σ of the smaller weight in each shared stock. Upload each fund&apos;s portfolio under Import → Fund portfolios; blank cells have no data.</p>}
    </Card>
  );
}

// ---------------------------------------------------------------------------------- detail

function RiskRow({ label, r }: { label: string; r: RiskStats | null }) {
  return (
    <tr className="border-b border-border">
      <td className="py-1.5 pr-2 text-fg">{label}</td>
      <td className="pr-2 text-right">{r ? `${r.volatility.toFixed(1)}%` : "—"}</td>
      <td className="pr-2 text-right">{r?.sharpe?.toFixed(2) ?? "—"}</td>
      <td className="pr-2 text-right">{r?.sortino?.toFixed(2) ?? "—"}</td>
      <td className="pr-2 text-right">{r ? formatPct(r.max_drawdown) : "—"}</td>
      <td className="text-xs text-fg-subtle">{r ? `${formatDate(r.drawdown_peak)} → ${formatDate(r.drawdown_trough)}` : ""}</td>
    </tr>
  );
}

export function FundReportView({ code }: { code: string }) {
  const q = useQuery({ queryKey: ["mf", code], queryFn: () => fundApi.report(code) });
  const checks = useQuery({ queryKey: ["mf-checks", code], queryFn: () => checksApi.fund(code), enabled: q.isSuccess });
  if (q.isError) return <ErrorState title="Couldn't analyse this fund" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data)
    return (
      <Loading label="the fund">
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <SkeletonText lines={6} />
        </div>
      </Loading>
    );
  return <FundReportBody f={q.data} checks={checks.data} checksLoading={checks.isLoading} charts={<FundCharts code={code} />} />;
}

function Section({ title, children }: { title?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-4 rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
      {title}
      {children}
    </section>
  );
}

export function FundReportBody({ f, charts, checks, checksLoading = false }: { f: FundReport; charts?: ReactNode; checks?: FundChecks; checksLoading?: boolean }) {
  const h = f.holding;
  const sec = (k: string) => checks?.sections.find((s) => s.key === k);
  const header = (k: string, fallback: string) => {
    const s = sec(k);
    return s ? <SectionHeader section={s} /> : <h2 className="text-lg font-semibold text-fg">{fallback}</h2>;
  };
  const checkList = (k: string) => {
    const s = sec(k);
    return s ? <CheckList checks={s.checks} label={`${s.label} checks`} /> : checksLoading ? <SkeletonText lines={3} /> : null;
  };
  const navChange = f.nav != null && f.previous_nav ? ((f.nav - f.previous_nav) / f.previous_nav) * 100 : null;
  const DirIcon = { bullish: ArrowUpRight, bearish: ArrowDownRight, neutral: Minus };
  return (
    <div className="space-y-4">
      {f.fetch_errors.map((e) => (
        <Alert key={e} tone="warning">
          Could not refresh: {e}. Showing cached data where available.
        </Alert>
      ))}

      <header className="rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
        <h2 className="text-xl font-semibold text-fg">{f.name}</h2>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-fg-muted">
          <PlanBadge plan={f.plan} />
          <span>
            {f.amc ?? ""} · {f.category ?? "category unknown"} · AMFI {f.code}
          </span>
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-3">
          <div>
            <p className="flex items-baseline gap-2 text-2xl font-semibold text-fg">
              {f.nav != null ? formatINR(f.nav, 4) : "—"}
              <span className="text-base">
                <Delta value={navChange} decimals={2} />
              </span>
            </p>
            <p className="flex items-center gap-2 text-xs text-fg-subtle">
              NAV on {formatDate(f.nav_date)} <FreshnessBadge f={f.nav_freshness} />
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <FundSignalPill signal={f.signal} label={f.signal_label} size="md" />
            <span className="text-sm text-fg">
              <span className="font-semibold">Why: </span>
              {f.rule}.
            </span>
          </div>
        </div>
        <ul className="mt-3 space-y-1 text-sm">
          {f.reasons.map((r) => {
            const I = DirIcon[r.direction];
            return (
              <li key={r.text} className="flex items-start gap-1.5">
                <I aria-hidden className={`mt-0.5 size-4 shrink-0 ${r.direction === "bullish" ? "text-good" : r.direction === "bearish" ? "text-bad" : "text-fg-subtle"}`} />
                <span className="sr-only">{r.direction === "bullish" ? "For: " : r.direction === "bearish" ? "Against: " : ""}</span>
                <span className="text-fg">{r.text}</span>
              </li>
            );
          })}
        </ul>
        {f.notes.map((n) => (
          <p key={n} className="mt-2 text-xs text-fg-subtle">
            {n}
          </p>
        ))}
      </header>

      {checks ? (
        <Section title={<h2 className="text-lg font-semibold text-fg">Summary</h2>}>
          <div className="grid items-start gap-6 md:grid-cols-[minmax(0,22rem)_1fr]">
            <div className="flex justify-center">
              <ScoreShape axes={axesFromSections(checks.sections)} total={checks.total} maxTotal={checks.max_total} step={checks.step} size="lg" name={f.name} />
            </div>
            <div className="space-y-4">
              <p className="text-sm leading-relaxed text-fg">{checks.summary}</p>
              <RewardsRisks rewards={checks.rewards} risks={checks.risks} stacked />
            </div>
          </div>
        </Section>
      ) : checksLoading ? (
        <Loading label="the fund's checks">
          <Skeleton className="h-64 w-full" />
        </Loading>
      ) : null}

      {charts}

      {h && (
        <Card title="Your investment">
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Units" value={h.units} />
            <Stat label="Invested · value" value={`${formatINR(h.invested, 0)} · ${formatINR(h.value, 0)}`} />
            <Stat label="Gain" value={<Delta value={h.pnl} format="inr" />} />
            <Stat label="Your XIRR" value={pct(h.xirr)} hint={h.xirr_basis} />
          </dl>
        </Card>
      )}

      <Section title={header("returns", "Returns")}>
        <h3 className="text-sm font-semibold text-fg">Returns vs {f.benchmark?.label ?? "benchmark"}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-fg-muted">
              <tr className="border-b border-border">
                <th className="py-1.5 font-medium">Period</th>
                <th className="text-right font-medium">Fund</th>
                <th className="text-right font-medium">Benchmark</th>
                <th className="text-right font-medium">Difference</th>
              </tr>
            </thead>
            <tbody>
              {f.returns.map((r) => (
                <tr key={r.years} className="border-b border-border">
                  <td className="py-1.5 text-fg">
                    {r.years} year{r.years > 1 ? "s" : ""} (a year)
                  </td>
                  <td className="text-right">{pct(r.fund)}</td>
                  <td className="text-right">{pct(r.benchmark)}</td>
                  <td className="text-right">{r.fund != null && r.benchmark != null ? `${(r.fund - r.benchmark).toFixed(1)} pp` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {checkList("returns")}
      </Section>

      <Section title={header("consistency", "Consistency")}>
        {f.rolling.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-fg-muted">
                <tr className="border-b border-border">
                  <th className="py-1.5 font-medium">Rolling</th>
                  <th className="text-right font-medium">Fund avg</th>
                  <th className="text-right font-medium">Index avg</th>
                  <th className="text-right font-medium">Beat it</th>
                  <th className="text-right font-medium">Range vs index</th>
                </tr>
              </thead>
              <tbody>
                {f.rolling.map((r) => (
                  <tr key={r.years} className="border-b border-border">
                    <td className="py-1.5 text-fg">
                      {r.years}y ({r.windows} windows)
                    </td>
                    <td className="text-right">{r.fund_avg.toFixed(1)}%</td>
                    <td className="text-right">{r.bench_avg.toFixed(1)}%</td>
                    <td className="text-right">{Math.round(r.beat_share * 100)}%</td>
                    <td className="text-right text-xs">
                      {r.worst_excess.toFixed(1)} to {r.best_excess > 0 ? "+" : ""}
                      {r.best_excess.toFixed(1)} pp
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {checkList("consistency")}
      </Section>

      <Section title={header("risk", "Risk")}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-fg-muted">
              <tr className="border-b border-border">
                <th className="py-1.5" />
                <th className="text-right font-medium">Volatility</th>
                <th className="text-right font-medium">Sharpe</th>
                <th className="text-right font-medium">Sortino</th>
                <th className="text-right font-medium">Max fall</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <RiskRow label="Fund" r={f.risk} />
              {f.benchmark && <RiskRow label={f.benchmark.label} r={f.benchmark_risk} />}
            </tbody>
          </table>
        </div>
        {f.risk && <p className="text-xs text-fg-subtle">Over {f.risk.years} years to {formatDate(f.risk.end)}, annualised. Sharpe and Sortino use the risk-free rate in the config.</p>}
        {checkList("risk")}
      </Section>

      {sec("risk_adjusted") && <Section title={header("risk_adjusted", "Risk-adjusted")}>{checkList("risk_adjusted")}</Section>}

      <Section title={header("cost", "Cost")}>
        {f.plan === "regular" && (
          <p className="text-sm text-fg">
            Regular plan.{" "}
            {f.direct_twin ? (
              <>
                Direct plan:{" "}
                <Link className="text-accent-text underline" to={`/mutual-funds/${f.direct_twin.code}`}>
                  {f.direct_twin.name}
                </Link>
                {f.direct_gap_pp != null && ` returned ${f.direct_gap_pp > 0 ? "+" : ""}${f.direct_gap_pp.toFixed(2)} pp a year more (${f.direct_gap_basis.toLowerCase()}).`}
              </>
            ) : (
              f.direct_gap_basis
            )}
          </p>
        )}
        <ExpenseRatio f={f} />
        {checkList("cost")}
      </Section>

      <Card title="Overlap with your other funds">
        {f.overlaps.length === 0 ? (
          <p className="text-sm text-fg-muted">No overlap data. Upload this fund&apos;s portfolio (and your other funds&apos;) under Import → Fund portfolios.</p>
        ) : (
          <ul className="space-y-1 text-sm text-fg">
            {f.overlaps.map((o) => (
              <li key={o.code}>
                Shares {o.pct.toFixed(0)}% of its holdings with {shortName(o.name)} ({o.common} stocks in common)
                {o.approximate && <span className="text-xs text-fg-subtle"> · approximate: {o.note}</span>}
              </li>
            ))}
          </ul>
        )}
        {f.segment_peers.length > 0 && <p className="mt-2 text-xs text-fg-subtle">Same segment: {f.segment_peers.join(", ")}</p>}
      </Card>

      {f.unavailable.length > 0 && (
        <p className="text-xs text-fg-subtle">
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
      void qc.invalidateQueries({ queryKey: ["mf-checks"] });
    },
  });
  const num = v.trim() === "" ? null : Number(v);
  const valid = num === null || (Number.isFinite(num) && num >= 0 && num <= 5);
  return (
    <div>
      <label className="block text-sm">
        <span className="text-fg-muted">Expense ratio (TER %, from the fund&apos;s factsheet; no free source publishes it)</span>
        <span className="mt-1 flex gap-2">
          <input className={`${inputClass} w-28`} inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} placeholder="e.g. 0.65" />
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate(num)}>
            Save
          </Button>
        </span>
      </label>
      {!valid && <p className="mt-1 text-xs text-bad">Enter a percentage between 0 and 5.</p>}
      {save.isError && <Alert tone="error">{save.error.message}</Alert>}
    </div>
  );
}
