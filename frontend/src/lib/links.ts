import type { StyleKey } from "../api/client";

/** The views of the Analysis page. Kept apart from the page so linking to it doesn't load it. */
export type AnalysisView = "signal" | "technical" | "patterns" | "fundamental" | "backtest";

/** Query string for links to the Analysis page, keeping the chosen style and view. */
export function analysisQuery(style: StyleKey | null, view: AnalysisView = "signal"): string {
  const p = new URLSearchParams();
  if (style) p.set("style", style);
  if (view !== "signal") p.set("view", view);
  const s = p.toString();
  return s ? `?${s}` : "";
}
