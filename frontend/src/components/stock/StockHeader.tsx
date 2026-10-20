import { GitCompareArrows } from "lucide-react";
import { Link } from "react-router-dom";
import type { PriceSeries, StockChecks, StockSignal } from "../../api/client";
import { formatDate, formatINR, formatPct } from "../../lib/format";
import { SignalPill } from "../analysis";
import { FreshnessBadge } from "../MarketData";
import { Badge, buttonClass, Delta, Skeleton, Stat } from "../ui";
import { WatchButton } from "../WatchButton";

const CONFIDENCE = { high: "High", medium: "Medium", low: "Low" } as const;

/** Last close and the change on the previous session, from the daily bars. */
export function lastMove(prices: PriceSeries | undefined): { close: number; change: number | null; pct: number | null; date: string } | null {
  const bars = prices?.bars ?? [];
  const last = bars.at(-1);
  if (!last) return null;
  const prev = bars.at(-2);
  const change = prev ? last.close - prev.close : null;
  return { close: last.close, change, pct: prev && change !== null ? (change / prev.close) * 100 : null, date: last.t };
}

/** Name, ticker, sector, last price and change, the signal and its confidence, and your position. */
export function StockHeader({
  ticker,
  checks,
  signal,
  prices,
}: {
  ticker: string;
  checks?: StockChecks;
  signal?: StockSignal;
  prices?: PriceSeries;
}) {
  const name = checks?.label ?? signal?.label ?? ticker;
  const sector = checks?.sector ?? signal?.sector;
  const move = lastMove(prices);
  const pos = signal?.position;
  const isIndex = ticker.startsWith("^");
  const confidence = signal?.scores.confidence;
  // Small companies (often BSE-only) can be missing figures at Yahoo: say so up front.
  const unscored = checks?.sections.filter((s) => s.score === null).length ?? 0;
  return (
    <header className="rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-fg">{name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-fg-muted">
            <span className="font-mono">{ticker}</span>
            {sector && <Badge>{sector}</Badge>}
            {ticker.endsWith(".BO") && <Badge>BSE only</Badge>}
            {checks?.is_financial && <Badge tone="accent">Lender: own health checks</Badge>}
            {unscored >= 2 && (
              <span title={`Yahoo Finance has too few figures to score ${unscored} of the ${checks!.sections.length} sections, so the total is out of ${checks!.max_total}.`}>
                <Badge tone="caution">Limited data</Badge>
              </span>
            )}
          </p>
        </div>
        {!isIndex && (ticker.endsWith(".NS") || ticker.endsWith(".BO")) && (
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/compare?t=${encodeURIComponent(ticker)}`} className={buttonClass("secondary", "sm")}>
              <GitCompareArrows aria-hidden className="size-3.5" /> Compare
            </Link>
            <WatchButton ticker={ticker} source="Stock page" />
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-4">
        <div>
          {move ? (
            <>
              <p className="flex flex-wrap items-baseline gap-x-3 text-2xl font-semibold text-fg">
                {isIndex ? move.close.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : formatINR(move.close)}
                <span className="text-base">
                  <Delta value={move.pct} /> {move.change !== null && <span className="text-sm text-fg-muted">({move.change >= 0 ? "+" : "−"}{Math.abs(move.change).toFixed(2)})</span>}
                </span>
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
                Close on {formatDate(move.date)}, change on the session before
                {prices && <FreshnessBadge f={prices.freshness} />}
              </p>
            </>
          ) : (
            <Skeleton className="h-9 w-48" />
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {signal ? (
            <>
              <SignalPill signal={signal.signal} label={signal.signal_label} size="md" />
              <span className="text-sm text-fg-muted" title={signal.scores.confidence_reason}>
                {confidence ? `${CONFIDENCE[confidence]} confidence` : "No confidence"}
              </span>
              <span className="text-xs text-fg-subtle">
                {signal.style_label} style · {signal.risk_label} risk
              </span>
            </>
          ) : (
            <Skeleton className="h-8 w-40" />
          )}
        </div>
      </div>

      {signal && (
        <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-border pt-4 sm:grid-cols-4">
          {pos ? (
            <>
              <Stat label="Your holding" value={`${pos.quantity} shares`} hint={`avg ${formatINR(pos.avg_price)}`} />
              <Stat label="Value" value={formatINR(pos.value, 0)} hint={pos.price_source} />
              <Stat label="Unrealised P&L" value={<Delta value={pos.pnl} format="inr" />} hint={pos.pnl_pct !== null ? formatPct(pos.pnl_pct) : undefined} />
              <Stat
                label="Weight"
                value={signal.weight === null ? "—" : `${(signal.weight * 100).toFixed(1)}%`}
                hint={
                  signal.weight !== null && signal.weight > signal.max_weight
                    ? `above your ${Math.round(signal.max_weight * 100)}% limit`
                    : `limit ${Math.round(signal.max_weight * 100)}%`
                }
                help="This stock's share of your portfolio, against your risk level's limit for one stock."
              />
            </>
          ) : (
            <p className="col-span-full text-sm text-fg-muted">You don't hold this stock.</p>
          )}
        </dl>
      )}
    </header>
  );
}
