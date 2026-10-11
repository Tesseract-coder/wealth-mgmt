import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { marketApi, type MarketStatus } from "../api/client";
import { formatDate, formatFreshness } from "../lib/format";

/** NSE closes at 3:30 PM IST; an end-of-day bar is "as of" that time. */
export function closeTime(day: string): Date {
  return new Date(`${day.slice(0, 10)}T15:30:00+05:30`);
}

const latest = (days: (string | null)[]) => days.filter((d): d is string => !!d).sort().at(-1) ?? null;

export function freshnessText(s: MarketStatus): { prices: string; navs: string | null; stale: number } {
  const p = latest(s.quotes.filter((q) => q.kind !== "mf").map((q) => q.as_of));
  const n = latest(s.quotes.filter((q) => q.kind === "mf").map((q) => q.as_of));
  return {
    prices: p ? `Prices as of ${formatFreshness(closeTime(p))}` : "No prices downloaded yet",
    navs: n ? `NAVs as of ${formatDate(n)}` : null,
    stale: s.summary.stale + s.summary.unavailable,
  };
}

/** Shown under the header on every page. */
export function FreshnessBar() {
  const q = useQuery({ queryKey: ["market-status"], queryFn: marketApi.status, refetchInterval: 5 * 60_000 });
  if (!q.data) return null;
  const f = freshnessText(q.data);
  return (
    <p className="flex flex-wrap gap-x-3 text-xs text-fg-subtle" aria-live="polite">
      <span>{f.prices}</span>
      {f.navs && <span>{f.navs}</span>}
      {f.stale > 0 && (
        <Link to="/settings#data" className="inline-flex items-center gap-1 text-caution underline">
          <TriangleAlert aria-hidden className="size-3.5" />
          {f.stale} item{f.stale === 1 ? "" : "s"} stale or unavailable
        </Link>
      )}
      <span>Yahoo Finance prices are delayed, end of day.</span>
    </p>
  );
}
