import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { patternApi, type Direction, type PatternHolding, type PatternMatch, type StyleKey } from "../../api/client";
import { Alert, Card, Chip, ChipGroup, Disclosure, ErrorState, SkeletonCard, Stat } from "../ui";
import { DIRECTION, INTERVAL_LABEL } from "./meta";
import { PatternGuide } from "./PatternGuide";
import { PatternShape } from "./PatternShape";

const RING: Record<Direction, string> = {
  bullish: "border-good-border bg-good-soft",
  bearish: "border-bad-border bg-bad-soft",
  neutral: "border-neutral-border bg-neutral-soft",
};

/** A found pattern as a link to the stock's Chart patterns section. */
function PatternChip({ m, to }: { m: PatternMatch; to: string }) {
  const d = DIRECTION[m.direction];
  return (
    <Link to={to} className={`inline-flex items-center gap-2 rounded-full border py-0.5 pl-1 pr-2.5 text-xs hover:shadow-card ${RING[m.direction]}`}>
      <PatternShape patternKey={m.key} direction={m.direction} className="h-5 w-10" />
      <span className="font-semibold text-fg">{m.name}</span>
      <span className="text-fg-muted">
        <span className="sr-only">{d.label}, </span>
        {m.status === "confirmed" ? "confirmed" : "forming"}
      </span>
    </Link>
  );
}

type Filter = "all" | Direction;

/** The Holdings page's Chart patterns view: patterns on every holding, then the pattern guide. */
export function HoldingsPatterns({ style, linkQuery }: { style: StyleKey | null; linkQuery: (ticker: string) => string }) {
  const q = useQuery({ queryKey: ["patterns-holdings", style], queryFn: () => patternApi.holdings(style) });
  const [dir, setDir] = useState<Filter>("all");
  const [confirmedOnly, setConfirmedOnly] = useState(false);

  const keep = (m: PatternMatch) => (dir === "all" || m.direction === dir) && (!confirmedOnly || m.status === "confirmed");
  const rows = (q.data ?? []).map((h) => ({ h, shown: h.patterns.filter(keep) })).filter((r) => r.shown.length > 0);
  const none = (q.data ?? []).filter((h) => h.patterns.length === 0);
  const all = (q.data ?? []).flatMap((h) => h.patterns);
  const count = (d: Direction) => all.filter((m) => m.direction === d).length;

  return (
    <div className="space-y-4">
      {q.isError ? (
        <ErrorState title="Couldn't scan your holdings" detail={q.error.message} onRetry={() => void q.refetch()} />
      ) : !q.data ? (
        <SkeletonCard label="patterns on your holdings" lines={6} />
      ) : q.data.length === 0 ? (
        <Alert tone="info">
          No stock holdings yet. <Link className="underline" to="/import">Import your Groww file</Link>, or search for any stock above to see its chart patterns.
        </Alert>
      ) : (
        <Card
          title="Chart patterns on your holdings"
          description={`Read from cached prices on the ${INTERVAL_LABEL[q.data[0]!.interval]} chart. Open a pattern to see it drawn, with its breakout, target and cancel prices.`}
        >
          <dl className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Holdings with a pattern" value={`${q.data.length - none.length} of ${q.data.length}`} />
            <Stat label="Bullish" value={count("bullish")} hint="patterns" />
            <Stat label="Bearish" value={count("bearish")} hint="patterns" />
            <Stat label="Confirmed" value={all.filter((m) => m.status === "confirmed").length} hint="broke out recently" />
          </dl>
          <div className="mb-3 flex flex-wrap gap-x-6 gap-y-2">
            <ChipGroup label="Show">
              <Chip pressed={dir === "all"} onClick={() => setDir("all")} count={all.length}>
                All
              </Chip>
              {(["bullish", "bearish", "neutral"] as const).map((d) => (
                <Chip key={d} pressed={dir === d} onClick={() => setDir(d)} count={count(d)}>
                  {DIRECTION[d].label}
                </Chip>
              ))}
            </ChipGroup>
            <ChipGroup label="Status">
              <Chip pressed={confirmedOnly} onClick={() => setConfirmedOnly((v) => !v)}>
                Confirmed only
              </Chip>
            </ChipGroup>
          </div>
          {rows.length ? (
            <ul className="divide-y divide-border">
              {rows.map(({ h, shown }) => (
                <Row key={h.ticker} h={h} shown={shown} to={linkQuery(h.ticker)} />
              ))}
            </ul>
          ) : (
            <p className="py-4 text-sm text-fg-muted">No holding has a pattern matching these filters.</p>
          )}
          {none.length > 0 && (
            <div className="mt-3">
              <Disclosure summary={`${none.length} holding${none.length === 1 ? "" : "s"} with no clear pattern`}>
                <p className="text-sm text-fg-muted">{none.map((h) => h.label).join(", ")}</p>
              </Disclosure>
            </div>
          )}
        </Card>
      )}
      <Card title="Pattern guide" description="Every pattern the scanner looks for: what it means, whether it's a buy or a sell, and which trading style it suits.">
        <PatternGuide />
      </Card>
    </div>
  );
}

function Row({ h, shown, to }: { h: PatternHolding; shown: PatternMatch[]; to: string }) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-2.5">
      <div className="w-48 min-w-0 shrink-0">
        <Link to={to} className="font-medium text-fg underline-offset-2 hover:underline">
          {h.label}
        </Link>
        <div className="font-mono text-xs text-fg-subtle">{h.ticker}</div>
      </div>
      <div className="flex min-w-0 flex-1 flex-wrap gap-2">
        {shown.map((m) => (
          <PatternChip key={m.key} m={m} to={to} />
        ))}
      </div>
    </li>
  );
}
