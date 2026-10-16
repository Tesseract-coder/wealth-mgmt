import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  analysisApi,
  api,
  chartApi,
  checksApi,
  fundamentalApi,
  signalApi,
  type CheckResult,
  type FinancialHistory,
  type FundamentalReport,
  type SectionResult,
  type StockChecks,
  type StockSignal,
  type StyleKey,
} from "../../api/client";
import { PriceChart } from "../../charts/lazy";
import { startFor } from "../../charts/priceData";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { formatDate, formatINR } from "../../lib/format";
import { TechnicalReportView } from "../../pages/Technical";
import { axesFromSections, ChartCaption, ChartFigure, CheckBar, CheckList, RewardsRisks, ScoreShape, SectionHeader, stepFor } from "../analysis";
import { BacktestView } from "../Backtest";
import { FundamentalBody } from "../FundamentalView";
import { Alert, Badge, Delta, Disclosure, EmptyState, ErrorState, Loading, Skeleton, SkeletonText, Stat } from "../ui";
import {
  debtCaption,
  dividendCaption,
  fairValueCaption,
  growthCaption,
  marginCaption,
  ownershipCaption,
  peCaption,
  quarterCaption,
  roeCaption,
  rsiZone,
} from "./captions";
import { StockHeader } from "./StockHeader";
import { CompareBars, FairValueBar, OwnershipBar, RsiGauge } from "./Visuals";
import { WhatToDo } from "./WhatToDo";

// Recharts is the heaviest part of the page and every chart is below the fold.
const charts = () => import("./FinancialCharts");
const RevenueProfitChart = lazy(() => charts().then((m) => ({ default: m.RevenueProfitChart })));
const QuarterChart = lazy(() => charts().then((m) => ({ default: m.QuarterChart })));
const MarginRoeChart = lazy(() => charts().then((m) => ({ default: m.MarginRoeChart })));
const BalanceChart = lazy(() => charts().then((m) => ({ default: m.BalanceChart })));
const DividendChart = lazy(() => charts().then((m) => ({ default: m.DividendChart })));

/** The old tabs (?view=…) now open the section that holds their content. */
export type LegacyView = "signal" | "technical" | "fundamental" | "backtest";

export type SectionKey =
  | "summary"
  | "price"
  | "valuation"
  | "growth"
  | "past"
  | "health"
  | "momentum"
  | "dividends"
  | "ownership"
  | "action"
  | "test";

const NAV: { key: SectionKey; label: string }[] = [
  { key: "summary", label: "Summary" },
  { key: "price", label: "Price chart" },
  { key: "valuation", label: "Valuation" },
  { key: "growth", label: "Future Growth" },
  { key: "past", label: "Past Performance" },
  { key: "health", label: "Financial Health" },
  { key: "momentum", label: "Momentum" },
  { key: "dividends", label: "Dividends" },
  { key: "ownership", label: "Ownership" },
  { key: "action", label: "What to do" },
  { key: "test", label: "Test the rules" },
];

const FUNDAMENTAL_SECTIONS: SectionKey[] = ["valuation", "growth", "past", "health", "dividends", "ownership"];

const START: Record<LegacyView, SectionKey> = { signal: "summary", technical: "momentum", fundamental: "past", backtest: "test" };

const sectionId = (k: SectionKey) => `section-${k}`;

/**
 * One stock as a story, top to bottom: header, summary (Score Shape, Rewards and Risks), price
 * chart, the six check sections with their charts, ownership, what to do, and a backtest. Desktop
 * gets a sticky section list; phones get one section at a time behind tabs.
 */
export function StockStory({ ticker, style, view = "signal" }: { ticker: string; style: StyleKey | null; view?: LegacyView }) {
  const isIndex = ticker.startsWith("^");
  const wide = useMediaQuery("(min-width: 1024px)");
  const start = startFor(12);

  // The signal first: on a stock's first visit it downloads prices and fundamentals, and the rest reuse them.
  const sig = useQuery({ queryKey: ["signal", ticker, style, undefined], queryFn: () => signalApi.stock(ticker, style) });
  const settled = sig.isSuccess || sig.isError;
  const checks = useQuery({ queryKey: ["checks", ticker, style], queryFn: () => checksApi.stock(ticker, style), enabled: settled });
  const history = useQuery({ queryKey: ["fin-history", ticker], queryFn: () => checksApi.history(ticker), enabled: checks.isSuccess && !isIndex });
  const fund = useQuery({ queryKey: ["fundamental", ticker], queryFn: () => fundamentalApi.report(ticker), enabled: settled && !isIndex });
  const tech = useQuery({ queryKey: ["technical", ticker, style], queryFn: () => analysisApi.technical(ticker, style), enabled: sig.isSuccess });
  // Same key as the price chart's default view, so this is one request.
  const prices = useQuery({ queryKey: ["chart-prices", ticker, "1d", start], queryFn: () => chartApi.prices(ticker, "1d", start) });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });

  const daily = tech.data?.timeframes.find((t) => t.interval === "1d");
  const sr = (daily?.analysis.levels.length ? daily.analysis.levels : tech.data?.context.levels) ?? [];

  const sections = useMemo(() => new Map((checks.data?.sections ?? []).map((s) => [s.key, s])), [checks.data]);
  // Indices and ETFs have no statements: every fundamental section is empty.
  const priceOnly = isIndex || (!!checks.data && checks.data.sections.every((s) => s.key === "momentum" || s.with_data === 0));
  const nav = NAV.filter((n) => !(priceOnly && FUNDAMENTAL_SECTIONS.includes(n.key)));

  const [active, setActive] = useState<SectionKey>(START[view]);
  useEffect(() => setActive(START[view]), [view, ticker]);

  // Desktop: jump to the section an old link pointed at, then follow the scroll.
  useEffect(() => {
    if (!wide || START[view] === "summary") return;
    const el = document.getElementById(sectionId(START[view]));
    el?.scrollIntoView?.({ block: "start" });
  }, [wide, view, ticker, checks.isSuccess]);
  useEffect(() => {
    if (!wide || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(
      (entries) => {
        const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) setActive(top.target.id.replace("section-", "") as SectionKey);
      },
      { rootMargin: "-80px 0px -65% 0px" },
    );
    nav.forEach((n) => {
      const el = document.getElementById(sectionId(n.key));
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [wide, nav.length, checks.isSuccess]); // eslint-disable-line react-hooks/exhaustive-deps

  const content = (key: SectionKey): ReactNode => {
    switch (key) {
      case "summary":
        return <Summary checks={checks} priceOnly={priceOnly} style={style} />;
      case "price":
        return (
          <Plain title="Price chart" subtitle="Candles with moving averages, support and resistance, and your stop-loss and targets.">
            <PriceChart ticker={ticker} levels={sig.data?.levels ?? null} sr={sr} panes={false} embedded />
            <ChartCaption>
              {sig.data?.levels
                ? `${sig.data.levels.stop_breached ? "The price closed below" : "The price is above"} its trailing stop of ${formatINR(sig.data.levels.trailing_stop)}. Tick RSI or MACD above the chart to open their panes.`
                : "Tick RSI or MACD above the chart to open their panes."}
            </ChartCaption>
          </Plain>
        );
      case "action":
        return (
          <Plain title="What to do" subtitle="The signal for your style and risk level, and what it suggests.">
            {sig.isError ? <ErrorState title={`Couldn't score ${ticker}`} detail={sig.error.message} onRetry={() => void sig.refetch()} /> : sig.data ? <WhatToDo s={sig.data} /> : <SkeletonText lines={6} />}
          </Plain>
        );
      case "test":
        return (
          <Plain title="Test the rules" subtitle="Replay the technical rules over the last 3 years of prices to see how they would have done.">
            <Disclosure summary={`Backtest the signal rules on ${ticker}`} hint="takes a few seconds" lazy defaultOpen={view === "backtest"}>
              <BacktestView ticker={ticker} style={style} />
            </Disclosure>
          </Plain>
        );
      case "ownership":
        return <Ownership fund={fund.data} loading={fund.isLoading} />;
      default:
        return (
          <CheckSection
            k={key}
            section={sections.get(key)}
            checks={checks}
            history={history.data}
            historyLoading={history.isLoading}
            fund={fund.data}
            signal={sig.data}
            ticker={ticker}
            style={style}
            view={view}
            rsiBand={config.data?.technical?.thresholds}
          />
        );
    }
  };

  return (
    <div className="space-y-4">
      <StockHeader ticker={ticker} checks={checks.data} signal={sig.data} prices={prices.data} />
      {sig.data?.notes.map((n) => (
        <Alert key={n} tone="info">
          {n}
        </Alert>
      ))}

      {wide ? (
        <div className="grid grid-cols-[11rem_minmax(0,1fr)] gap-6">
          <nav aria-label="Sections" className="sticky top-20 self-start">
            <ul className="space-y-0.5 text-sm">
              {nav.map((n) => (
                <li key={n.key}>
                  <a
                    href={`#${sectionId(n.key)}`}
                    aria-current={active === n.key ? "location" : undefined}
                    onClick={(e) => {
                      e.preventDefault();
                      setActive(n.key);
                      document.getElementById(sectionId(n.key))?.scrollIntoView?.({ behavior: "smooth", block: "start" });
                    }}
                    className={`flex items-center justify-between gap-2 rounded-control px-2.5 py-1.5 ${
                      active === n.key ? "bg-accent-soft font-medium text-accent-text" : "text-fg-muted hover:bg-surface-2 hover:text-fg"
                    }`}
                  >
                    {n.label}
                    <NavScore s={sections.get(n.key)} />
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="min-w-0 space-y-4">
            {nav.map((n) => (
              <section key={n.key} id={sectionId(n.key)} aria-label={n.label} className="scroll-mt-20 rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
                {content(n.key)}
              </section>
            ))}
          </div>
        </div>
      ) : (
        <div>
          <div role="tablist" aria-label="Sections" className="-mx-4 flex gap-1 overflow-x-auto border-b border-border px-4">
            {nav.map((n) => (
              <button
                key={n.key}
                type="button"
                role="tab"
                id={`tab-${n.key}`}
                aria-selected={active === n.key}
                aria-controls={sectionId(n.key)}
                onClick={() => setActive(n.key)}
                className="-mb-px flex shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-medium text-fg-muted aria-selected:border-accent aria-selected:text-fg"
              >
                {n.label}
                <NavScore s={sections.get(n.key)} />
              </button>
            ))}
          </div>
          <section id={sectionId(active)} role="tabpanel" aria-labelledby={`tab-${active}`} className="mt-4 rounded-card border border-border bg-surface p-4 shadow-card">
            {content(active)}
          </section>
        </div>
      )}
    </div>
  );
}

function NavScore({ s }: { s?: SectionResult }) {
  if (!s) return null;
  return <span className="text-xs tabular-nums text-fg-subtle">{s.score === null ? "—" : `${s.score}/6`}</span>;
}

function Plain({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold text-fg">{title}</h2>
        <p className="text-sm text-fg-muted">{subtitle}</p>
      </header>
      {children}
    </div>
  );
}

type ChecksQuery = { data?: StockChecks; isError: boolean; error: Error | null; refetch: () => unknown };

function Summary({ checks, priceOnly, style }: { checks: ChecksQuery; priceOnly: boolean; style: StyleKey | null }) {
  const c = checks.data;
  if (checks.isError)
    return <ErrorState title="Couldn't work out the checks" detail={checks.error?.message ?? ""} hint="The signal and charts below still work." onRetry={() => void checks.refetch()} />;
  if (!c)
    return (
      <Loading label="the Score Shape">
        <div className="grid gap-6 md:grid-cols-[minmax(0,22rem)_1fr]">
          <Skeleton className="mx-auto aspect-[6/5] w-full max-w-80" />
          <SkeletonText lines={6} />
        </div>
      </Loading>
    );
  const wc = c.week_change;
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-fg">Summary</h2>
          <p className="text-sm text-fg-muted">
            {c.confidence[0]!.toUpperCase() + c.confidence.slice(1)} confidence: {c.confidence_reason}
          </p>
        </div>
        {wc && (
          <Badge tone={wc.total > 0 ? "good" : wc.total < 0 ? "bad" : "neutral"}>
            {wc.total > 0 ? "+" : wc.total < 0 ? "−" : "±"}
            {Math.abs(wc.total)} since {formatDate(wc.since)}
            {wc.signal_changed && wc.previous_signal_label ? ` · was ${wc.previous_signal_label}` : ""}
          </Badge>
        )}
      </header>
      {priceOnly && <Alert tone="info">This is an index or fund with no company accounts, so only the Momentum checks apply.</Alert>}
      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,22rem)_1fr]">
        <div className="flex justify-center">
          {priceOnly ? (
            // One axis isn't a shape: show the Momentum score on its own.
            <MomentumOnly section={c.sections.find((s) => s.key === "momentum")} />
          ) : (
            <ScoreShape axes={axesFromSections(c.sections)} total={c.total} maxTotal={c.max_total} step={c.step} size="lg" style={style ?? c.style} name={c.label} />
          )}
        </div>
        <div className="space-y-4">
          <p className="text-sm leading-relaxed text-fg">{c.summary}</p>
          <RewardsRisks rewards={c.rewards} risks={c.risks} stacked />
        </div>
      </div>
    </div>
  );
}

function MomentumOnly({ section }: { section?: SectionResult }) {
  if (!section) return null;
  return (
    <div className="flex flex-col items-center gap-2 py-6 text-center">
      <p className="text-sm text-fg-muted">Momentum</p>
      <p className="text-2xl font-semibold text-fg">
        {section.score === null ? "—" : section.score}
        <span className="text-base font-normal text-fg-subtle">/6</span>
      </p>
      <CheckBar statuses={section.checks.map((c) => c.status)} step={section.score === null ? null : stepFor(section.score, 6)} />
      <p className="text-xs text-fg-subtle">
        {section.passed} of {section.with_data} checks passed
      </p>
    </div>
  );
}

const find = (s: SectionResult | undefined, id: string): CheckResult | undefined => s?.checks.find((c) => c.check_id === id);

function ChartSlot({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Skeleton className="h-52 w-full" />}>{children}</Suspense>;
}

function CheckSection({
  k,
  section,
  checks,
  history,
  historyLoading,
  fund,
  signal,
  ticker,
  style,
  view,
  rsiBand,
}: {
  k: SectionKey;
  section?: SectionResult;
  checks: ChecksQuery;
  history?: FinancialHistory;
  historyLoading: boolean;
  fund?: FundamentalReport;
  signal?: StockSignal;
  ticker: string;
  style: StyleKey | null;
  view: LegacyView;
  rsiBand?: { rsi_overbought: number; rsi_oversold: number };
}) {
  if (checks.isError) return <ErrorState title="Couldn't work out the checks" detail={checks.error?.message ?? ""} onRetry={() => void checks.refetch()} />;
  if (!section)
    return (
      <Loading label={k}>
        <SkeletonText lines={5} />
      </Loading>
    );
  const years = history?.years ?? [];
  const unit = history?.unit ?? "₹ Cr";
  const noHistory = !historyLoading && years.length === 0;
  const metric = (key: string) => fund?.metrics.find((m) => m.key === key);

  let visuals: ReactNode = null;
  if (k === "valuation") {
    const fv = checks.data?.fair_value ?? null;
    const pe = find(section, "pe_vs_sector");
    const own = find(section, "pe_vs_history");
    const peValue = pe?.value ?? own?.value ?? null;
    const items = [
      { label: "This stock", value: peValue, display: peValue === null ? "—" : `${peValue.toFixed(1)}×`, self: true },
      ...(pe?.threshold != null ? [{ label: "Sector median", value: pe.threshold, display: `${pe.threshold.toFixed(1)}×` }] : []),
      ...(own?.threshold != null ? [{ label: "Own recent median", value: own.threshold, display: `${own.threshold.toFixed(1)}×` }] : []),
    ];
    visuals = (
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartFigure title="Price vs fair value" label="Bars comparing the share price with the estimated fair value" caption={fairValueCaption(fv, fv?.price ?? null)}>
          {fv ? (
            <>
              <FairValueBar fv={fv} />
              <div className="mt-3">
                <Disclosure summary="How fair value is estimated">
                  <ul className="space-y-1 text-sm">
                    {fv.methods.map((m) => (
                      <li key={m.name}>
                        <span className="font-semibold text-fg">
                          {m.name}: {formatINR(m.value)}
                        </span>{" "}
                        <span className="text-fg-muted">{m.basis}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-fg-subtle">{fv.caveat}</p>
                </Disclosure>
              </div>
            </>
          ) : (
            <p className="text-sm text-fg-muted">Not enough data for an estimate.</p>
          )}
        </ChartFigure>
        <ChartFigure title="P/E compared" label="Bars comparing this stock's P/E with its sector and its own history" caption={peCaption(peValue, pe?.threshold ?? null, own?.threshold ?? null)}>
          <CompareBars items={items} label="P/E comparison" />
        </ChartFigure>
      </div>
    );
  } else if (k === "growth") {
    visuals = noHistory ? null : (
      <div className="grid gap-6 lg:grid-cols-2">
        <ChartFigure title={`Revenue and profit by year (${unit})`} label="Bar chart of yearly revenue and net profit" caption={growthCaption(years, unit)}>
          <ChartSlot>{history ? <RevenueProfitChart years={years} unit={unit} /> : <Skeleton className="h-52 w-full" />}</ChartSlot>
        </ChartFigure>
        <ChartFigure title={`Latest quarters (${unit})`} label="Bar chart of quarterly revenue and net profit" caption={quarterCaption(history?.quarters ?? [])}>
          <ChartSlot>{history ? <QuarterChart quarters={history.quarters} unit={unit} /> : <Skeleton className="h-52 w-full" />}</ChartSlot>
        </ChartFigure>
      </div>
    );
  } else if (k === "past") {
    visuals = (
      <div className="space-y-4">
        {!noHistory && (
          <ChartFigure title="Margins and return on equity" label="Line chart of operating margin, net margin and ROE by year" caption={`${marginCaption(years)} ${roeCaption(years)}`}>
            <ChartSlot>{history ? <MarginRoeChart years={years} /> : <Skeleton className="h-52 w-full" />}</ChartSlot>
          </ChartFigure>
        )}
      </div>
    );
  } else if (k === "health") {
    const ic = find(section, "interest_coverage");
    const cr = find(section, "current_ratio");
    const fcf = find(section, "fcf_positive");
    visuals = (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_14rem]">
        {noHistory ? (
          <p className="text-sm text-fg-muted">No balance-sheet history to chart.</p>
        ) : (
          <ChartFigure title={`Debt, equity and cash (${unit})`} label="Bar chart of debt, equity and cash at each year-end" caption={debtCaption(years, unit)}>
            <ChartSlot>{history ? <BalanceChart years={years} unit={unit} /> : <Skeleton className="h-52 w-full" />}</ChartSlot>
          </ChartFigure>
        )}
        <dl className="grid grid-cols-2 content-start gap-4 lg:grid-cols-1">
          {ic && ic.status !== "no_data" && <Stat label="Interest coverage" value={ic.display_value} hint="operating profit ÷ interest" help={ic.help ?? undefined} />}
          {cr && cr.status !== "no_data" && <Stat label="Current ratio" value={cr.display_value} hint="short-term assets ÷ bills" help={cr.help ?? undefined} />}
          {fcf && fcf.status !== "no_data" && <Stat label="Free cash flow" value={fcf.display_value} hint="latest year" help={fcf.help ?? undefined} />}
        </dl>
      </div>
    );
  } else if (k === "momentum") {
    const rsi = find(section, "rsi_healthy");
    const band: [number, number] = [rsi?.threshold ?? 45, rsiBand?.rsi_overbought ?? 70];
    const oversold = rsiBand?.rsi_oversold ?? 30;
    const rs = find(section, "beats_nifty_6m");
    const sma200 = find(section, "above_sma200");
    const sma50 = find(section, "above_sma50");
    const trend = (c?: CheckResult) => (c?.status === "pass" ? "above" : c?.status === "fail" ? "below" : "—");
    visuals = (
      <div className="grid gap-6 md:grid-cols-[14rem_1fr]">
        {rsi?.value != null ? (
          <figure>
            <RsiGauge rsi={rsi.value} band={band} oversold={oversold} zone={rsiZone(rsi.value, band, oversold)} />
            <ChartCaption className="text-center">RSI {rsi.value.toFixed(1)} is {rsiZone(rsi.value, band, oversold)}.</ChartCaption>
          </figure>
        ) : (
          <p className="text-sm text-fg-muted">No RSI yet: needs more price history.</p>
        )}
        <dl className="grid grid-cols-2 content-start gap-4 sm:grid-cols-3">
          <Stat label="vs 200-day average" value={trend(sma200)} hint={sma200?.display_threshold} help="The long-term trend." />
          <Stat label="vs 50-day average" value={trend(sma50)} hint={sma50?.display_threshold} help="The medium-term trend." />
          <Stat label="vs Nifty 50, 6 months" value={rs?.display_value ?? "—"} help="The stock's 6-month return minus the Nifty 50's (relative strength)." />
        </dl>
      </div>
    );
  } else if (k === "dividends") {
    const y = metric("dividend_yield");
    visuals = (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,18rem)_1fr]">
        <ChartFigure
          title="Dividend yield"
          label="Bars comparing this stock's dividend yield with its sector median"
          caption={
            y?.value != null
              ? `Yields ${y.value.toFixed(1)}%${y.sector_median != null ? ` against a sector median of ${y.sector_median.toFixed(1)}%` : ""}.`
              : "No dividend yield: it doesn't pay one, or the data isn't available."
          }
        >
          <CompareBars
            label="Dividend yield comparison"
            items={[
              { label: "This stock", value: y?.value ?? null, display: y?.value != null ? `${y.value.toFixed(1)}%` : "—", self: true },
              ...(y?.sector_median != null ? [{ label: "Sector median", value: y.sector_median, display: `${y.sector_median.toFixed(1)}%` }] : []),
            ]}
          />
        </ChartFigure>
        {!noHistory && (
          <ChartFigure title={`Dividends paid and payout (${unit})`} label="Bar chart of dividends paid each year with the payout ratio as a line" caption={dividendCaption(years, unit)}>
            <ChartSlot>{history ? <DividendChart years={years} unit={unit} /> : <Skeleton className="h-52 w-full" />}</ChartSlot>
          </ChartFigure>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeader section={section} />
      {visuals}
      <CheckList checks={section.checks} label={`${section.label} checks`} />
      {k === "past" && (
        <Disclosure summary="F-score and every fundamental figure" hint="the old Fundamental tab" defaultOpen={view === "fundamental"}>
          {fund ? <FundamentalBody r={fund} /> : <SkeletonText lines={4} />}
        </Disclosure>
      )}
      {k === "momentum" && (
        <Disclosure summary="Every technical reading, by timeframe" hint="the old Technical tab" lazy defaultOpen={view === "technical"}>
          <TechnicalReportView ticker={ticker} style={style} chart={false} />
        </Disclosure>
      )}
      {k === "valuation" && signal && signal.fundamental_freshness.status !== "fresh" && <p className="text-xs text-fg-subtle">Fundamentals: {signal.fundamental_freshness.reason}.</p>}
      {history && k === "growth" && history.notes.map((n) => <p key={n} className="text-xs text-fg-subtle">{n}</p>)}
    </div>
  );
}

function Ownership({ fund, loading }: { fund?: FundamentalReport; loading: boolean }) {
  const m = (key: string) => fund?.metrics.find((x) => x.key === key)?.value ?? null;
  const promoter = m("promoter_pct");
  const changes = [
    ["Promoters", m("promoter_change")],
    ["FIIs", m("fii_change")],
    ["DIIs", m("dii_change")],
  ] as const;
  return (
    <Plain title="Ownership" subtitle="Who owns the company, and whether promoters have pledged shares.">
      {loading ? (
        <SkeletonText lines={3} />
      ) : promoter === null ? (
        <EmptyState title="No shareholding data" action={<Link to="/import" className="text-sm font-medium text-accent-text underline">Upload Screener.in data</Link>}>
          Yahoo Finance doesn't provide promoter, FII and DII holdings. Upload a Screener.in export for this company to see them, with pledged shares.
        </EmptyState>
      ) : (
        <ChartFigure title="Shareholding" label="Stacked bar of promoter, FII, DII and public holdings" caption={ownershipCaption(promoter, m("promoter_change"), m("pledge_pct"))} source="your Screener.in upload">
          <OwnershipBar promoter={promoter} fii={m("fii_pct")} dii={m("dii_pct")} />
          <dl className="mt-4 grid grid-cols-3 gap-4">
            {changes.map(([label, v]) => (
              <Stat key={label} label={`${label}, change`} value={<Delta value={v} format="number" />} hint="percentage points" />
            ))}
          </dl>
        </ChartFigure>
      )}
    </Plain>
  );
}
