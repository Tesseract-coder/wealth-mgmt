import { useQuery } from "@tanstack/react-query";
import { api, OFFLINE_MESSAGE } from "../api/client";
import { Button } from "./ui";

/** A banner while the backend can't be reached; it re-checks every 15 s and clears itself. */
export function BackendStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    retry: 0,
    refetchInterval: (q) => (q.state.status === "error" ? 15_000 : 120_000),
  });
  if (health.isError) {
    return (
      <div role="alert" className="border-b border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2">
          <span className="font-medium">⚠ Backend offline.</span>
          <span>{health.error.message || OFFLINE_MESSAGE}</span>
          <Button variant="secondary" className="ml-auto" onClick={() => void health.refetch()} disabled={health.isFetching}>
            {health.isFetching ? "Checking…" : "Retry now"}
          </Button>
        </div>
      </div>
    );
  }
  if (health.data?.status === "degraded") {
    return (
      <div role="status" className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
        <div className="mx-auto max-w-7xl">⚠ Backend degraded: database {health.data.database}</div>
      </div>
    );
  }
  return null;
}
