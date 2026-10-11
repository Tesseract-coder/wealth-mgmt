import { ArrowLeftRight, ChevronDown, ChevronsDown, ChevronsUp, ChevronUp, CircleCheck, CircleDot, CircleHelp, Eye, type LucideIcon } from "lucide-react";
import type { FundSignalKey, SignalKey } from "../../api/client";

type Pill = { icon: LucideIcon; cls: string };

const SOLID_GOOD = "border-transparent bg-good text-surface";
const SOLID_BAD = "border-transparent bg-bad text-surface";
const SOFT_GOOD = "border-good-border bg-good-soft text-good";
const SOFT_CAUTION = "border-caution-border bg-caution-soft text-caution";
const SOFT_NEUTRAL = "border-neutral-border bg-neutral-soft text-neutral";
const NONE = "border-dashed border-neutral-border bg-transparent text-fg-muted";

const STOCK: Record<SignalKey, Pill> = {
  strong_buy: { icon: ChevronsUp, cls: SOLID_GOOD },
  buy: { icon: ChevronUp, cls: SOFT_GOOD },
  hold: { icon: CircleDot, cls: SOFT_NEUTRAL },
  reduce: { icon: ChevronDown, cls: SOFT_CAUTION },
  sell: { icon: ChevronsDown, cls: SOLID_BAD },
  no_signal: { icon: CircleHelp, cls: NONE },
};

const FUND: Record<FundSignalKey, Pill> = {
  continue: { icon: CircleCheck, cls: SOFT_GOOD },
  review: { icon: Eye, cls: SOFT_CAUTION },
  switch: { icon: ArrowLeftRight, cls: SOLID_BAD },
  no_signal: { icon: CircleHelp, cls: NONE },
};

function Pill({ p, label, size }: { p: Pill; label: string; size: "sm" | "md" }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-semibold ${p.cls} ${
        size === "md" ? "px-2.5 py-1 text-sm" : "px-2 py-0.5 text-xs"
      }`}
    >
      <p.icon aria-hidden className={size === "md" ? "size-4" : "size-3.5"} strokeWidth={2.5} />
      {label}
    </span>
  );
}

/** A stock signal (Strong Buy … Sell) as a pill with an icon and text: never colour alone. */
export function SignalPill({ signal, label, size = "sm" }: { signal: SignalKey; label: string; size?: "sm" | "md" }) {
  return <Pill p={STOCK[signal] ?? STOCK.no_signal} label={label} size={size} />;
}

/** A fund signal (Continue / Review / Switch) in the same style. */
export function FundSignalPill({ signal, label, size = "sm" }: { signal: FundSignalKey; label: string; size?: "sm" | "md" }) {
  return <Pill p={FUND[signal] ?? FUND.no_signal} label={label} size={size} />;
}
