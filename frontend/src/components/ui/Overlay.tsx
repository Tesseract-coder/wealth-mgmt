import * as RTabs from "@radix-ui/react-tabs";
import * as RToggle from "@radix-ui/react-toggle-group";
import * as RTooltip from "@radix-ui/react-tooltip";
import { Info, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Hover/focus tooltip. The trigger must be focusable (a button or link) so keyboards reach it. */
export function Tooltip({ content, children, side = "top" }: { content: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <RTooltip.Provider delayDuration={200}>
      <RTooltip.Root>
        <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
        <RTooltip.Portal>
          <RTooltip.Content
            side={side}
            sideOffset={6}
            collisionPadding={8}
            className="z-50 max-w-xs rounded-control border border-border bg-surface-3 px-2.5 py-1.5 text-xs text-fg shadow-pop"
          >
            {content}
            <RTooltip.Arrow className="fill-surface-3" />
          </RTooltip.Content>
        </RTooltip.Portal>
      </RTooltip.Root>
    </RTooltip.Provider>
  );
}

/** A small (i) button explaining a metric in one plain sentence. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip content={children}>
      <button type="button" aria-label={`About ${label}`} className="relative inline-grid size-4 place-items-center rounded-full text-fg-subtle after:absolute after:-inset-1 hover:text-fg">
        <Info aria-hidden className="size-3.5" />
      </button>
    </Tooltip>
  );
}

/** Tabs with arrow-key navigation. `value`/`onValueChange` make them controlled (e.g. from the URL). */
export function Tabs({
  tabs,
  value,
  defaultValue,
  onValueChange,
  label,
}: {
  tabs: { value: string; label: ReactNode; content: ReactNode }[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (v: string) => void;
  label: string;
}) {
  return (
    <RTabs.Root value={value} defaultValue={defaultValue ?? tabs[0]?.value} onValueChange={onValueChange}>
      <RTabs.List aria-label={label} className="flex gap-1 overflow-x-auto border-b border-border">
        {tabs.map((t) => (
          <RTabs.Trigger
            key={t.value}
            value={t.value}
            className="-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-medium text-fg-muted hover:text-fg data-[state=active]:border-accent data-[state=active]:text-fg"
          >
            {t.label}
          </RTabs.Trigger>
        ))}
      </RTabs.List>
      {tabs.map((t) => (
        <RTabs.Content key={t.value} value={t.value} className="pt-4">
          {t.content}
        </RTabs.Content>
      ))}
    </RTabs.Root>
  );
}

/** A segmented control: exactly one option is always selected (e.g. Cards / Table). */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string; icon?: LucideIcon; hideLabel?: boolean }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <RToggle.Root
      type="single"
      aria-label={label}
      value={value}
      onValueChange={(v) => v && onChange(v as T)}
      className="inline-flex max-w-full flex-wrap rounded-control border border-border bg-surface-2 p-0.5"
    >
      {options.map((o) => (
        <RToggle.Item
          key={o.value}
          value={o.value}
          aria-label={o.hideLabel ? o.label : undefined}
          className="inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-[calc(var(--radius-control)-2px)] px-2.5 text-xs font-medium text-fg-muted hover:text-fg data-[state=on]:bg-surface data-[state=on]:text-fg data-[state=on]:shadow-card"
        >
          {o.icon && <o.icon aria-hidden className="size-3.5" />}
          {!o.hideLabel && o.label}
        </RToggle.Item>
      ))}
    </RToggle.Root>
  );
}
