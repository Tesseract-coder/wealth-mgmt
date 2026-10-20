import { useQuery } from "@tanstack/react-query";
import { Shapes } from "lucide-react";
import { useState } from "react";
import { patternApi, type PatternInterval, type PatternMatch, type PatternReport, type StyleKey } from "../../api/client";
import { formatDate, formatINR, formatNumber } from "../../lib/format";
import { Button, Disclosure, EmptyState, ErrorState, Segmented, SkeletonCard } from "../ui";
import { DIRECTION, INTERVAL_LABEL } from "./meta";
import { PatternCard } from "./PatternCard";
import { PatternGuide } from "./PatternGuide";

const INTERVALS: { value: PatternInterval; label: string }[] = [
  { value: "15m", label: "15-min" },
  { value: "1h", label: "Hourly" },
  { value: "1d", label: "Daily" },
  { value: "1wk", label: "Weekly" },
  { value: "1mo", label: "Monthly" },
];

/** The chart a style reads patterns on first. */
export function defaultPatternInterval(style: StyleKey | null): PatternInterval {
  return style === "long_term" ? "1wk" : "1d";
}

/** Can the main price chart draw this timeframe? */
export const onPriceChart = (iv: PatternInterval): iv is "1d" | "1wk" | "1mo" => iv === "1d" || iv === "1wk" || iv === "1mo";

/** "2 patterns on the daily chart: 1 bullish, 1 bearish. 1 is confirmed." */
export function patternSummary(r: PatternReport): string {
  const ps = r.patterns;
  const chart = `the ${INTERVAL_LABEL[r.interval]} chart`;
  if (!ps.length) return `No classic pattern on ${chart} right now.`;
  const by = (["bullish", "bearish", "neutral"] as const)
    .map((d) => [d, ps.filter((p) => p.direction === d).length] as const)
    .filter(([, n]) => n > 0)
    .map(([d, n]) => `${n} ${DIRECTION[d].label.toLowerCase()}`);
  const done = ps.filter((p) => p.status === "confirmed").length;
  return (
    `${ps.length} pattern${ps.length === 1 ? "" : "s"} on ${chart}: ${by.join(", ")}. ` +
    (done ? `${done === ps.length && done > 1 ? "All are" : `${done} ${done === 1 ? "is" : "are"}`} confirmed.` : "None is confirmed yet: wait for the break.")
  );
}

/** The stock page's Chart patterns section: what's on the chart now, then the full guide. */
export function PatternsSection({
  ticker,
  style,
  onShow,
}: {
  ticker: string;
  style: StyleKey | null;
  onShow?: (m: PatternMatch, interval: "1d" | "1wk" | "1mo") => void;
}) {
  const [interval, setIv] = useState<PatternInterval>(defaultPatternInterval(style));
  const q = useQuery({ queryKey: ["patterns", ticker, interval], queryFn: () => patternApi.stock(ticker, interval) });
  const lib = useQuery({ queryKey: ["pattern-library"], queryFn: patternApi.library, staleTime: Infinity });
  const info = new Map((lib.data ?? []).map((p) => [p.key, p]));
  const px = ticker.startsWith("^") ? (v: number) => formatNumber(v) : (v: number) => formatINR(v);
  const r = q.data;
  const found = new Set(r?.patterns.map((p) => p.key) ?? []);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-fg">Chart patterns</h2>
          <p className="text-sm text-fg-muted">Classic shapes on this chart, what they mean, and the prices that confirm or cancel them.</p>
        </div>
        <Segmented options={INTERVALS} value={interval} onChange={setIv} label="Chart timeframe" />
      </header>

      {q.isError ? (
        <ErrorState title="Couldn't scan the chart for patterns" detail={q.error.message} onRetry={() => void q.refetch()} />
      ) : !r ? (
        <SkeletonCard label={`patterns on the ${INTERVAL_LABEL[interval]} chart`} lines={5} />
      ) : (
        <>
          <p className="text-sm font-medium text-fg" aria-live="polite">
            {patternSummary(r)}
            {r.as_of && <span className="ml-1 font-normal text-fg-subtle">Bars to {formatDate(r.as_of)}.</span>}
          </p>
          {r.patterns.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {r.patterns.map((m) => (
                <PatternCard
                  key={m.key}
                  match={m}
                  info={info.get(m.key)}
                  report={r}
                  px={px}
                  onShow={onShow && onPriceChart(r.interval) ? () => onShow(m, r.interval as "1d" | "1wk" | "1mo") : undefined}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Shapes}
              title={`No clear pattern on the ${INTERVAL_LABEL[interval]} chart`}
              action={
                interval !== "1wk" ? (
                  <Button variant="secondary" size="sm" onClick={() => setIv("1wk")}>
                    Check the weekly chart
                  </Button>
                ) : undefined
              }
            >
              That's normal: most of the time price isn't in a textbook shape. Patterns that broke out more than 10 bars ago are no longer shown.
            </EmptyState>
          )}
          {r.notes.map((n) => (
            <p key={n} className="text-xs text-fg-subtle">
              {n}
            </p>
          ))}
        </>
      )}

      <Disclosure summary="Pattern guide: every pattern, what it means and when to use it" hint={`${lib.data?.length ?? 15} patterns`} lazy>
        <PatternGuide found={found} />
      </Disclosure>
    </div>
  );
}
