import { CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import { useState } from "react";

function List({
  title,
  items,
  icon: Icon,
  tone,
  empty,
  limit,
}: {
  title: string;
  items: string[];
  icon: LucideIcon;
  tone: string;
  empty: string;
  limit: number;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, limit);
  return (
    <section aria-label={title}>
      <h3 className={`mb-2 flex items-center gap-1.5 text-sm font-semibold ${tone}`}>
        <Icon aria-hidden className="size-4" />
        {title}
        <span className="font-normal text-fg-subtle">({items.length})</span>
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-fg-muted">{empty}</p>
      ) : (
        <ul className="space-y-1.5">
          {shown.map((t) => (
            <li key={t} className="flex items-start gap-2 text-sm text-fg">
              <Icon aria-hidden className={`mt-0.5 size-4 shrink-0 ${tone}`} />
              <span>{t}</span>
            </li>
          ))}
        </ul>
      )}
      {items.length > limit && (
        <button type="button" className="mt-1.5 text-xs font-medium text-accent-text hover:underline" onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </section>
  );
}

/**
 * Rewards (ticks) and Risks (warnings) in plain English, side by side on wide screens. Each list is
 * headed with its icon, name and count, so the colour is never the only signal.
 */
export function RewardsRisks({
  rewards,
  risks,
  notes = [],
  limit = 5,
  stacked = false,
}: {
  rewards: string[];
  risks: string[];
  /** Neutral footnotes (e.g. what the shape covers). */
  notes?: string[];
  limit?: number;
  stacked?: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className={`grid gap-4 ${stacked ? "" : "md:grid-cols-2"}`}>
        <List title="Rewards" items={rewards} icon={CircleCheck} tone="text-good" empty="No standout strengths in the checks." limit={limit} />
        <List title="Risks" items={risks} icon={TriangleAlert} tone="text-bad" empty="No risks flagged by the checks." limit={limit} />
      </div>
      {notes.length > 0 && (
        <ul className="space-y-1">
          {notes.map((n) => (
            <li key={n} className="flex items-start gap-1.5 text-xs text-fg-subtle">
              <Info aria-hidden className="mt-px size-3.5 shrink-0" />
              {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
