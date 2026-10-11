import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { marketApi, type MarketStatus } from "../api/client";
import { Alert, Button } from "./ui";

/** "Price data for TATAMOTORS is stale: Yahoo Finance did not respond …" for each out-of-date quote (first three). */
export function staleLines(s: MarketStatus, n = 3): { lines: string[]; more: number } {
  const bad = (s.quotes ?? []).filter((q) => q.freshness?.status !== "fresh");
  const lines = bad.slice(0, n).map((q) => {
    const what = q.kind === "mf" ? "NAV" : "Price data";
    const name = q.kind === "stock" ? q.code.replace(/\.(NS|BO)$/, "") : q.label;
    return `${what} for ${name} is ${q.freshness.status === "stale" ? "out of date" : "unavailable"}: ${q.freshness.reason.replace(/\.$/, "")}.`;
  });
  return { lines, more: Math.max(0, bad.length - n) };
}

/** Says which prices are out of date and why, with a one-click refresh. Renders nothing when all is fresh. */
export function StaleNotice() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["market-status"], queryFn: marketApi.status, refetchInterval: 5 * 60_000 });
  const refresh = useMutation({
    mutationFn: () => marketApi.refresh("prices"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["market-status"] }),
  });
  if (!q.data) return null;
  const { lines, more } = staleLines(q.data);
  if (!lines.length) return null;
  return (
    <Alert tone="warning" title="Some prices are out of date">
      <ul className="space-y-0.5">
        {lines.map((l) => (
          <li key={l}>{l}</li>
        ))}
        {more > 0 && <li>And {more} more.</li>}
      </ul>
      <span className="mt-2 flex flex-wrap items-center gap-3">
        <Button size="sm" variant="secondary" icon={RefreshCw} disabled={refresh.isPending || refresh.isSuccess} onClick={() => refresh.mutate()}>
          {refresh.isSuccess ? "Refreshing in the background" : "Refresh prices now"}
        </Button>
        <Link to="/settings#data" className="text-sm underline">
          See data status
        </Link>
      </span>
      {refresh.isError && <span className="mt-1 block">Couldn&apos;t start the refresh: {refresh.error.message}</span>}
    </Alert>
  );
}
