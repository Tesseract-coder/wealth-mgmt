import { Check } from "lucide-react";
import type { ReactNode } from "react";

/** A toggleable filter chip. Pressed chips show a tick as well as the accent colour. */
export function Chip({ pressed, onClick, children, count }: { pressed: boolean; onClick: () => void; children: ReactNode; count?: number }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`inline-flex h-7 items-center gap-1 whitespace-nowrap rounded-full border px-2.5 text-xs font-medium ${
        pressed ? "border-accent bg-accent-soft text-accent-text" : "border-border bg-surface text-fg-muted hover:border-border-strong hover:text-fg"
      }`}
    >
      {pressed && <Check aria-hidden className="size-3.5" />}
      {children}
      {count !== undefined && <span className={pressed ? "" : "text-fg-subtle"}>{count}</span>}
    </button>
  );
}

/** A labelled row of chips (one filter dimension). */
export function ChipGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-xs font-medium text-fg-subtle">{label}</span>
      {children}
    </div>
  );
}
