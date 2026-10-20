/* Fake API answers for the stock page's endpoints (RELIANCE.NS samples), shared by page tests. */
import { SAMPLE_STOCK } from "../components/analysis/samples";
import { SAMPLE_PATTERN_LIBRARY, SAMPLE_PATTERNS } from "../components/patterns/samples";
import { SAMPLE_FUNDAMENTALS, SAMPLE_HISTORY, SAMPLE_SIGNAL } from "../components/stock/samples";

/** The body for a stock-page URL, or undefined if the URL isn't one of them. */
export function stockRoute(url: string): unknown {
  const path = url.replace(/^https?:\/\/[^/]+/, "").replace(/^\/api/, "").split("?")[0]!;
  if (path === "/watchlist/tickers") return [];
  if (path === "/analysis/patterns/library") return SAMPLE_PATTERN_LIBRARY;
  if (/^\/analysis\/technical\/[^/]+\/patterns$/.test(path)) return SAMPLE_PATTERNS;
  if (/^\/analysis\/stock\/[^/]+\/checks$/.test(path)) return SAMPLE_STOCK;
  if (/^\/analysis\/stock\/[^/]+\/history$/.test(path)) return [];
  if (/^\/analysis\/stock\/[^/]+$/.test(path)) return SAMPLE_SIGNAL;
  if (/^\/analysis\/fundamental\/[^/]+\/history$/.test(path)) return SAMPLE_HISTORY;
  if (/^\/analysis\/fundamental\/(?!holdings$)[^/]+$/.test(path)) return SAMPLE_FUNDAMENTALS;
  return undefined;
}
