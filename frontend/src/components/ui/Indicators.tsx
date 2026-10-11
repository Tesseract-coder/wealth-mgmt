import { ArrowDownRight, ArrowUpRight, CircleCheck, Minus, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { formatINR, formatINRCompact, formatPct } from "../../lib/format";
import { InfoTip } from "./Overlay";

export type Semantic = "good" | "caution" | "bad" | "neutral" | "accent";

const BADGE: Record<Semantic, string> = {
  good: "border-good-border bg-good-soft text-good",
  caution: "border-caution-border bg-caution-soft text-caution",
  bad: "border-bad-border bg-bad-soft text-bad",
  neutral: "border-neutral-border bg-neutral-soft text-neutral",
  accent: "border-transparent bg-accent-soft text-accent-text",
};

/** A small label. Always has text, so the colour is never the only signal. */
export function Badge({ tone = "neutral", icon: Icon, children }: { tone?: Semantic; icon?: LucideIcon; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${BADGE[tone]}`}>
      {Icon && <Icon aria-hidden className="size-3.5" />}
      {children}
    </span>
  );
}

export type CheckStatus = "pass" | "fail" | "no_data";

const STATUS: Record<CheckStatus, { icon: LucideIcon; cls: string; label: string }> = {
  pass: { icon: CircleCheck, cls: "text-good", label: "Pass" },
  fail: { icon: TriangleAlert, cls: "text-bad", label: "Fail" },
  no_data: { icon: Minus, cls: "text-fg-subtle", label: "No data" },
};

/** Tick for pass, warning for fail, dash for no data, with a screen-reader label (or a visible one). */
export function StatusIcon({ status, showLabel = false, className = "size-4" }: { status: CheckStatus; showLabel?: boolean; className?: string }) {
  const s = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-1 ${s.cls}`}>
      <s.icon aria-hidden className={`shrink-0 ${className}`} />
      <span className={showLabel ? "text-xs font-medium" : "sr-only"}>{s.label}</span>
    </span>
  );
}

type DeltaFormat = "pct" | "inr" | "inr-compact" | "number";

/** A change with its sign, an arrow and a colour: "▲ +₹8,948". Zero and missing values are neutral. */
export function Delta({ value, format = "pct", decimals, className = "" }: { value: number | null | undefined; format?: DeltaFormat; decimals?: number; className?: string }) {
  if (value === null || value === undefined || Number.isNaN(value)) return <span className={`text-fg-subtle ${className}`}>—</span>;
  const text =
    format === "pct"
      ? formatPct(value, decimals)
      : format === "inr-compact"
        ? formatINRCompact(value, { signed: true })
        : format === "inr"
          ? `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatINR(Math.abs(value), decimals ?? 0)}`
          : `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(decimals ?? 1)}`;
  const dir = text.startsWith("+") ? "up" : text.startsWith("−") ? "down" : "flat";
  const Icon = dir === "up" ? ArrowUpRight : dir === "down" ? ArrowDownRight : Minus;
  const cls = dir === "up" ? "text-good" : dir === "down" ? "text-bad" : "text-fg-muted";
  return (
    <span className={`inline-flex items-center gap-0.5 font-medium whitespace-nowrap ${cls} ${className}`}>
      <Icon aria-hidden className="size-[1em] shrink-0" />
      <span className="sr-only">{dir === "up" ? "Up " : dir === "down" ? "Down " : "Unchanged "}</span>
      {text}
    </span>
  );
}

/** One headline figure: label (with an optional one-line explanation), value, change, small print. */
export function Stat({
  label,
  value,
  delta,
  hint,
  help,
}: {
  label: string;
  value: ReactNode;
  delta?: ReactNode;
  hint?: ReactNode;
  help?: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1 text-xs font-medium text-fg-muted">
        {label}
        {help && <InfoTip label={label}>{help}</InfoTip>}
      </dt>
      <dd className="mt-1 flex flex-wrap items-baseline gap-x-2 text-lg font-semibold text-fg">
        {value}
        {delta && <span className="text-sm">{delta}</span>}
      </dd>
      {hint && <dd className="mt-0.5 text-xs text-fg-subtle">{hint}</dd>}
    </div>
  );
}
