import { useQuery } from "@tanstack/react-query";
import { RefreshCw, TriangleAlert, WifiOff } from "lucide-react";
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
      <div role="alert" className="border-b border-bad-border bg-bad-soft px-4 py-2 text-sm text-fg">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2">
          <WifiOff aria-hidden className="size-4 text-bad" />
          <span className="font-medium">Backend offline.</span>
          <span>{health.error.message || OFFLINE_MESSAGE}</span>
          <Button variant="secondary" size="sm" icon={RefreshCw} className="ml-auto" onClick={() => void health.refetch()} disabled={health.isFetching}>
            {health.isFetching ? "Checking…" : "Retry now"}
          </Button>
        </div>
      </div>
    );
  }
  if (health.data?.status === "degraded") {
    return (
      <div role="status" className="border-b border-caution-border bg-caution-soft px-4 py-2 text-sm text-fg">
        <div className="mx-auto flex max-w-7xl items-center gap-2">
          <TriangleAlert aria-hidden className="size-4 text-caution" />
          Backend degraded: database {health.data.database}
        </div>
      </div>
    );
  }
  return null;
}
