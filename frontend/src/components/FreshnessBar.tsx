import { useQuery, useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { marketApi, type MarketStatus } from "../api/client";
import { formatDate, formatFreshness } from "../lib/format";
import { invalidateData } from "../lib/queries";

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

type Line = ReturnType<typeof freshnessText>;
const LAST_KEY = "freshness-line";

/** The last line shown, so a reload draws it straight away instead of growing the header later. */
function lastLine(): Line | null {
  try {
    const v = JSON.parse(localStorage.getItem(LAST_KEY) ?? "null") as Line | null;
    return v && typeof v.prices === "string" ? v : null;
  } catch {
    return null;
  }
}

/** When a refresh that ran in the background (the daily schedule, or one started elsewhere)
 *  finishes, the pages kept in the cache are out of date: fetch them again. */
function useRefetchAfterRefresh(s: MarketStatus | undefined) {
  const qc = useQueryClient();
  const stamp = s ? `${s.last_job?.finished_at}|${s.last_fundamentals_job?.finished_at}` : null;
  const seen = useRef<string | null>(null);
  useEffect(() => {
    if (stamp === null) return;
    if (seen.current !== null && seen.current !== stamp) void invalidateData(qc);
    seen.current = stamp;
  }, [stamp, qc]);
}

/** Shown under the header on every page. */
export function FreshnessBar() {
  const q = useQuery({ queryKey: ["market-status"], queryFn: marketApi.status, refetchInterval: 5 * 60_000 });
  useRefetchAfterRefresh(q.data);
  const [last] = useState(lastLine);
  const fresh = q.data ? freshnessText(q.data) : null;
  const saved = fresh && JSON.stringify(fresh);
  useEffect(() => {
    if (!saved) return;
    try {
      localStorage.setItem(LAST_KEY, saved);
    } catch {
      // Private window or storage blocked: the placeholder below still holds the space.
    }
  }, [saved]);
  if (!fresh && !last && !q.isError)
    // First visit: same shape as the loaded line (it wraps on a phone), so little moves when it arrives.
    return (
      <p className="flex flex-wrap gap-x-3 text-xs text-fg-subtle">
        <span className="sr-only">Checking price dates…</span>
        <span aria-hidden className="invisible">
          Prices as of 12 Oct 2026, 3:30 PM IST
        </span>
        <span aria-hidden className="invisible">
          NAVs as of 09 Oct 2026
        </span>
        <span>Yahoo Finance prices are delayed, end of day.</span>
      </p>
    );
  const f = fresh ?? (q.isError ? { prices: "Price dates unavailable", navs: null, stale: 0 } : last!);
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
