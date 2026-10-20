import { QueryClient, type QueryClient as Client } from "@tanstack/react-query";

/** Answers that don't depend on your holdings or market data. */
const STATIC = new Set(["config", "meta", "health", "pattern-library"]);

/** Results are reused for a few minutes when you move between pages (the backend shares its
 *  analysis for as long). Anything that changes your data calls `invalidateData`. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5 * 60_000 } },
  });
}

/** After an import, a fix or a finished refresh: every analysis may have changed. */
export function invalidateData(qc: Client): Promise<void> {
  return qc.invalidateQueries({ predicate: (q) => !STATIC.has(String(q.queryKey[0])) });
}
