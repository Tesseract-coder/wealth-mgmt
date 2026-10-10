import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { watchlistApi } from "../api/client";
import { Button } from "./ui";

/** Add a stock to the watchlist (or show that it's already there). Text, not just a star. */
export function WatchButton({ ticker, source, compact = false }: { ticker: string; source: string; compact?: boolean }) {
  const qc = useQueryClient();
  const watched = useQuery({ queryKey: ["watch-tickers"], queryFn: watchlistApi.tickers });
  const add = useMutation({
    mutationFn: () => watchlistApi.add(ticker, source),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watch-tickers"] });
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
  const on = watched.data?.includes(ticker) ?? false;
  if (on)
    return (
      <span className="whitespace-nowrap text-xs font-medium text-emerald-700 dark:text-emerald-400">
        <span aria-hidden="true">★ </span>
        {compact ? "Watching" : "On your watchlist"}
      </span>
    );
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <Button variant="secondary" className="whitespace-nowrap !px-2 !py-1 text-xs" disabled={add.isPending || !watched.isSuccess} onClick={() => add.mutate()}>
        <span aria-hidden="true">☆ </span>
        {compact ? "Watch" : "Add to watchlist"}
      </Button>
      {add.isError && <span className="text-xs text-red-700 dark:text-red-400">{add.error.message}</span>}
    </span>
  );
}
