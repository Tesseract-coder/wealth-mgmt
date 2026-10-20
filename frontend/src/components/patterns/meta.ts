import { MoveHorizontal, TrendingDown, TrendingUp, type LucideIcon } from "lucide-react";
import type { Direction, PatternInfo, PatternInterval, PatternMatch, Suitability } from "../../api/client";
import type { Semantic } from "../ui";

export const DIRECTION: Record<Direction, { label: string; icon: LucideIcon; tone: Semantic }> = {
  bullish: { label: "Bullish", icon: TrendingUp, tone: "good" },
  bearish: { label: "Bearish", icon: TrendingDown, tone: "bad" },
  neutral: { label: "Neutral", icon: MoveHorizontal, tone: "neutral" },
};

export const ACTION: Record<PatternInfo["action"], { label: string; tone: Semantic }> = {
  buy: { label: "Good for buying", tone: "good" },
  sell: { label: "Good for selling", tone: "bad" },
  wait: { label: "Wait for the break", tone: "neutral" },
};

export const KIND: Record<PatternInfo["kind"], string> = {
  reversal: "Reversal",
  continuation: "Continuation",
  either: "Either way",
};

export const SUIT: Record<Suitability, string> = { good: "Good fit", ok: "Works", poor: "Not suited" };

export const HORIZONS = [
  { key: "intraday", label: "Intraday" },
  { key: "swing", label: "Swing" },
  { key: "positional", label: "Positional" },
] as const;

export const INTERVAL_LABEL: Record<PatternInterval, string> = {
  "15m": "15-minute",
  "1h": "hourly",
  "1d": "daily",
  "1wk": "weekly",
  "1mo": "monthly",
};

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? "" : "s"}`;

/** "Confirmed 2 days ago" / "Forming: not confirmed yet". */
export function statusLabel(m: PatternMatch, unit: string): string {
  if (m.status === "forming") return "Forming: not confirmed yet";
  const ago = m.bars_since_breakout ?? 0;
  return ago === 0 ? "Confirmed on the latest bar" : `Confirmed ${plural(ago, unit)} ago`;
}

export const STRENGTH: Record<PatternMatch["strength"], string> = {
  strong: "Strong match",
  moderate: "Moderate match",
  weak: "Weak match",
};

/** Breakout / target / cancel labels, worded for the pattern's direction. */
export function levelLabels(m: PatternMatch): { breakout: string; target: string; cancel: string } {
  if (m.direction === "neutral") return { breakout: "Breaks up above", target: "Target if it breaks up", cancel: "Breaks down below" };
  const up = m.direction === "bullish";
  if (m.status === "confirmed") return { breakout: up ? "Broke out above" : "Broke down below", target: "Textbook target", cancel: up ? "Fails below" : "Fails above" };
  return { breakout: up ? "Confirms above" : "Confirms below", target: "Textbook target", cancel: up ? "Cancelled below" : "Cancelled above" };
}
