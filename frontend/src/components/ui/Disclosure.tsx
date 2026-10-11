import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";

/**
 * A titled expander (native <details>, so it works with the keyboard and screen readers as-is).
 * `lazy` mounts the content on first open: use it for anything that fetches or draws a chart.
 */
export function Disclosure({
  summary,
  hint,
  defaultOpen = false,
  lazy = false,
  children,
  id,
}: {
  summary: ReactNode;
  hint?: ReactNode;
  defaultOpen?: boolean;
  lazy?: boolean;
  children: ReactNode;
  id?: string;
}) {
  const [opened, setOpened] = useState(defaultOpen);
  return (
    <details
      id={id}
      open={defaultOpen}
      onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && setOpened(true)}
      className="group rounded-control border border-border bg-surface"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm font-medium text-fg hover:bg-surface-2 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 shrink-0 text-fg-subtle transition-transform group-open:rotate-90" />
        <span className="min-w-0 flex-1">{summary}</span>
        {hint && <span className="text-xs font-normal text-fg-subtle">{hint}</span>}
      </summary>
      <div className="border-t border-border p-3">{!lazy || opened ? children : null}</div>
    </details>
  );
}
