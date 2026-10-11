import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Info, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { dashboardApi, type ActionItem, type Actions, type Severity } from "../api/client";
import { Badge, Card, ErrorState, Loading, Skeleton, type Semantic } from "./ui";

const SEV: Record<Severity, { label: string; icon: LucideIcon; tone: Semantic; edge: string }> = {
  high: { label: "High", icon: OctagonAlert, tone: "bad", edge: "border-l-bad" },
  medium: { label: "Medium", icon: TriangleAlert, tone: "caution", edge: "border-l-caution" },
  low: { label: "Low", icon: Info, tone: "neutral", edge: "border-l-border-strong" },
};

/** Severity as an icon and a word, never colour alone. */
export function SeverityTag({ s }: { s: Severity }) {
  const v = SEV[s];
  return (
    <Badge tone={v.tone} icon={v.icon}>
      {v.label}
    </Badge>
  );
}

export function ActionList({ limit }: { limit?: number }) {
  const q = useQuery({ queryKey: ["actions"], queryFn: dashboardApi.actions });
  if (q.isError) return <ErrorState title="Couldn't check what needs attention" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data)
    return (
      <Card title="Action needed">
        <Loading label="what needs attention">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        </Loading>
      </Card>
    );
  return <ActionListBody d={q.data} limit={limit} />;
}

function ActionCard({ a }: { a: ActionItem }) {
  const v = SEV[a.severity];
  return (
    <article className={`relative flex h-full flex-col gap-1.5 rounded-control border border-l-4 border-border bg-surface p-3 ${v.edge} ${a.link ? "hover:bg-surface-2" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <SeverityTag s={a.severity} />
        {a.link && <ChevronRight aria-hidden className="size-4 text-fg-subtle" />}
      </div>
      <h3 className="text-sm font-semibold text-fg">
        {a.title}
        {" · "}
        {a.link ? (
          <Link to={a.link} className="after:absolute after:inset-0 hover:underline">
            {a.subject}
          </Link>
        ) : (
          a.subject
        )}
      </h3>
      <p className="text-xs text-fg-muted">{a.detail}</p>
    </article>
  );
}

/** What needs attention, most severe first, as cards that link to the reasons. */
export function ActionListBody({ d, limit = 9 }: { d: Actions; limit?: number }) {
  const counts = { high: 0, medium: 0, low: 0 } as Record<Severity, number>;
  d.actions.forEach((a) => counts[a.severity]++);
  const shown = d.actions.slice(0, limit);
  return (
    <Card
      title="Action needed"
      description={d.actions.length ? `${counts.high} high, ${counts.medium} medium, ${counts.low} low.` : undefined}
      actions={
        <span className="text-xs text-fg-subtle">
          {d.style_label} style · {d.risk_label} risk · most severe first
        </span>
      }
    >
      {d.actions.length === 0 ? (
        <p className="text-sm text-fg-muted">Nothing needs attention under your current profile.</p>
      ) : (
        <>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((a, i) => (
              <li key={`${a.subject}-${a.title}-${i}`}>
                <ActionCard a={a} />
              </li>
            ))}
          </ul>
          {d.actions.length > limit && (
            <p className="mt-3 text-xs text-fg-subtle">
              {d.actions.length - limit} more. See{" "}
              <Link className="text-accent-text underline" to="/holdings">
                Holdings
              </Link>{" "}
              and{" "}
              <Link className="text-accent-text underline" to="/mutual-funds">
                Mutual funds
              </Link>
              .
            </p>
          )}
        </>
      )}
    </Card>
  );
}
