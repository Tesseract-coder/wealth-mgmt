import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText } from "lucide-react";
import { Link, Navigate } from "react-router-dom";
import { api, checksApi, REPORT_URL, signalApi, summaryApi, type HoldingsChecks, type PortfolioSummary } from "../api/client";
import { ActionList } from "../components/ActionList";
import { StaleNotice } from "../components/StaleNotice";
import { RewardsRisks } from "../components/analysis";
import { HoldingCard } from "../components/portfolio/HoldingCard";
import { NoHoldings, PortfolioCharts, PortfolioHero, SummarySkeleton } from "../components/PortfolioSummary";
import { buttonClass, Card, ErrorState, Loading, PageHeader, Skeleton, SkeletonText } from "../components/ui";
import { analysisQuery } from "./Technical";

/** Risks for the whole portfolio: the checks' risks plus the summary's limit warnings, without repeats. */
export function portfolioRisks(shape?: HoldingsChecks, summary?: PortfolioSummary): string[] {
  const out = [...(summary?.warnings ?? []), ...(shape?.risks ?? [])];
  return [...new Set(out)];
}

/**
 * The portfolio home: Score Shape and headline figures, what needs attention, the portfolio's
 * rewards and risks, allocation and performance charts, and the biggest holdings as cards.
 */
export function Overview() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const summary = useQuery({ queryKey: ["portfolio-summary"], queryFn: summaryApi.get });
  const style = profile.data?.style ?? null;
  const risk = profile.data?.risk ?? null;
  const hasStocks = (summary.data?.stock_value ?? 0) > 0;
  // Same keys as the Holdings page, so moving between the two doesn't re-score.
  const shapes = useQuery({ queryKey: ["checks-holdings", style, risk], queryFn: () => checksApi.holdings(style, risk), enabled: profile.isSuccess && hasStocks });
  const signals = useQuery({ queryKey: ["signal-holdings", style, risk], queryFn: () => signalApi.holdings(style, risk), enabled: profile.isSuccess && hasStocks });

  if (health.isError)
    return (
      <ErrorState
        title="The backend isn't answering"
        detail="The app couldn't reach its server."
        hint="Start it with make dev, then check /health on the backend port (BACKEND_PORT in .env)."
        onRetry={() => void health.refetch()}
      />
    );
  if (profile.data && !profile.data.onboarded) return <Navigate replace to="/onboarding" />;

  const riskLevel = profile.data && config.data?.risk_levels[profile.data.risk];
  const styleDef = profile.data?.style ? config.data?.styles[profile.data.style] : null;
  const sectorLimit = riskLevel ? riskLevel.max_weight_per_sector : null;
  const s = summary.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description={
          styleDef && riskLevel ? (
            <>
              {styleDef.label} style · {riskLevel.label} risk (max {Math.round(riskLevel.max_weight_per_stock * 100)}% per stock, {Math.round(riskLevel.max_weight_per_sector * 100)}% per
              sector, buy at ≥ {riskLevel.buy_threshold}).{" "}
              <Link className="text-accent-text underline" to="/settings">
                Change
              </Link>
            </>
          ) : profile.isError || config.isError ? undefined : (
            // Holds the line's space (two lines on a phone) until the profile arrives.
            <span aria-hidden className="skeleton block h-10 w-[36rem] max-w-full rounded-control sm:h-5" />
          )
        }
        actions={
          <a href={REPORT_URL} target="_blank" rel="noreferrer" className={buttonClass("secondary", "md")}>
            <FileText aria-hidden className="size-4" />
            Portfolio report<span className="sr-only"> (opens in a new tab)</span>
          </a>
        }
      />

      {summary.isError ? (
        <ErrorState title="Couldn't load the portfolio summary" detail={summary.error.message} onRetry={() => void summary.refetch()} />
      ) : !s ? (
        <SummarySkeleton />
      ) : s.total_value <= 0 ? (
        <NoHoldings />
      ) : (
        <>
          <StaleNotice />
          <PortfolioHero s={s} shape={shapes.data} shapeLoading={hasStocks && !shapes.data && !shapes.isError} />
          <ActionList />
          <Card title="Rewards and risks" description="Across your stocks, from the same checks as each stock's page.">
            {shapes.data ? (
              <RewardsRisks rewards={shapes.data.rewards} risks={portfolioRisks(shapes.data, s)} notes={shapes.data.notes} />
            ) : shapes.isError ? (
              <RewardsRisks rewards={[]} risks={portfolioRisks(undefined, s)} notes={["The stock checks couldn't be worked out just now; only the limit warnings are shown."]} />
            ) : hasStocks ? (
              <Loading label="rewards and risks">
                <SkeletonText lines={4} />
              </Loading>
            ) : (
              <RewardsRisks rewards={[]} risks={portfolioRisks(undefined, s)} />
            )}
          </Card>
          <PortfolioCharts s={s} sectorLimit={sectorLimit} />
          {hasStocks && <HoldingsPreview shapes={shapes.data} signals={signals} linkQuery={analysisQuery(null)} />}
        </>
      )}
    </div>
  );
}

function HoldingsPreview({
  shapes,
  signals,
  linkQuery,
}: {
  shapes?: HoldingsChecks;
  signals: { data?: Awaited<ReturnType<typeof signalApi.holdings>>; isError: boolean };
  linkQuery: string;
}) {
  const byTicker = new Map((shapes?.holdings ?? []).map((h) => [h.ticker, h]));
  const top = [...(signals.data?.holdings ?? [])].sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0)).slice(0, 6);
  return (
    <section aria-labelledby="preview-title" className="space-y-3">
      <div className="flex items-end justify-between gap-2">
        <div>
          <h2 id="preview-title" className="text-lg font-semibold text-fg">
            Biggest holdings
          </h2>
          <p className="text-sm text-fg-muted">Your six largest stocks by value.</p>
        </div>
        <Link to="/holdings" className="inline-flex min-h-6 items-center gap-1 py-1 text-sm font-medium text-accent-text hover:underline">
          View all <ArrowRight aria-hidden className="size-4" />
        </Link>
      </div>
      {signals.isError ? (
        <p className="text-sm text-fg-muted">Couldn't load the holdings. Open the Holdings page to retry.</p>
      ) : !signals.data ? (
        <Loading label="your biggest holdings">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-56 w-full" />
            ))}
          </div>
        </Loading>
      ) : (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
          {top.map((h) => (
            <li key={h.ticker}>
              <HoldingCard h={h} shape={byTicker.get(h.ticker)} linkQuery={linkQuery} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
