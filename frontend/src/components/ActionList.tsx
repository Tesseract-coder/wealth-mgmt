import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ChevronRight, Info, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { dashboardApi, type ActionItem, type Actions, type HoldingShape, type HoldingSignal, type Severity } from "../api/client";
import { axesFromRecord, ScoreShape } from "./analysis";
import { SignalPill } from "./analysis/SignalPill";
import { fmtScore } from "./SignalView";
import { Badge, buttonClass, Card, Drawer, ErrorState, Loading, Skeleton, SkeletonText, type Semantic } from "./ui";

/** What the page already knows about a held stock, for the quick look. */
export interface QuickLookData {
  signal?: HoldingSignal;
  shape?: HoldingShape;
}
export type QuickLookup = (ticker: string) => QuickLookData;

/** The stock a card's link points at, when it is a stock's page. */
export const tickerOf = (link: string | null) => (link ? (/^\/analysis\/([^/?#]+)/.exec(link)?.[1] ?? null) : null);

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

export function ActionList({ limit, lookup }: { limit?: number; lookup?: QuickLookup }) {
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
  return <ActionListBody d={q.data} limit={limit} lookup={lookup} />;
}

function ActionCard({ a, onQuickLook }: { a: ActionItem; onQuickLook?: () => void }) {
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
        {onQuickLook ? (
          <button type="button" onClick={onQuickLook} aria-haspopup="dialog" className="text-left after:absolute after:inset-0 hover:underline">
            {a.subject}
          </button>
        ) : a.link ? (
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

/** A held stock's signal, shape, reasons and suggested step, without leaving the page. */
function QuickLook({ a, data, onClose }: { a: ActionItem; data: QuickLookData; onClose: () => void }) {
  const { signal: s, shape } = data;
  const ticker = tickerOf(a.link)!;
  return (
    <Drawer
      title={
        <>
          {a.subject}
          <span className="block font-mono text-xs font-normal text-fg-subtle">{ticker}</span>
        </>
      }
      onClose={onClose}
      footer={
        <Link to={a.link!} className={`${buttonClass("primary", "md")} w-full justify-center`}>
          Open the full story <ArrowRight aria-hidden className="size-4" />
        </Link>
      }
    >
      {!s ? (
        <Loading label={`the signal for ${a.subject}`}>
          <SkeletonText lines={6} />
        </Loading>
      ) : (
        <div className="space-y-4 text-sm">
          <div className="flex items-center gap-4">
            {shape && <ScoreShape axes={axesFromRecord(shape.axes)} total={shape.total} maxTotal={shape.max_total} step={shape.step} size="md" name={s.label} animate={false} />}
            <dl className="space-y-1.5">
              <dd>
                <SignalPill signal={s.signal} label={s.signal_label} />
              </dd>
              <div className="flex gap-3 tabular-nums text-fg-muted">
                <span>
                  Score <b className="text-fg">{fmtScore(s.composite)}</b>
                </span>
                <span>Tech {fmtScore(s.technical)}</span>
                <span>Fund {fmtScore(s.fundamental)}</span>
              </div>
              {s.weight !== null && <div className="text-fg-muted">Weight {(s.weight * 100).toFixed(1)}%</div>}
            </dl>
          </div>
          <section>
            <h3 className="mb-1 font-semibold">Why</h3>
            <p>{s.rule}</p>
            <ul className="mt-1 space-y-0.5 text-xs">
              {s.flags.filter((f) => !s.rule.includes(f.text)).map((f) => (
                <li key={f.key} className={f.severe ? "text-bad" : "text-caution"}>
                  {f.severe ? "⛔" : "⚠"} {f.text}
                </li>
              ))}
              {s.top_bullish.slice(0, 3).map((t) => (
                <li key={`b${t}`}>▲ {t}</li>
              ))}
              {s.top_bearish.slice(0, 3).map((t) => (
                <li key={`r${t}`}>▼ {t}</li>
              ))}
            </ul>
          </section>
          {s.rebalance.action !== "none" && (
            <section>
              <h3 className="mb-1 font-semibold">Suggested</h3>
              <p>{s.rebalance.text}</p>
            </section>
          )}
          {shape && shape.top.length > 0 && <p className="text-xs text-fg-muted">{shape.top.join(" · ")}</p>}
        </div>
      )}
    </Drawer>
  );
}

/** What needs attention, most severe first, as cards. A held stock's card opens a quick look
 *  (when the page passes `lookup`); the others link to the reasons. */
export function ActionListBody({ d, limit = 9, lookup }: { d: Actions; limit?: number; lookup?: QuickLookup }) {
  const [open, setOpen] = useState<ActionItem | null>(null);
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
                <ActionCard a={a} onQuickLook={lookup && a.kind === "stock" && tickerOf(a.link) ? () => setOpen(a) : undefined} />
              </li>
            ))}
          </ul>
          {open && lookup && <QuickLook a={open} data={lookup(tickerOf(open.link)!)} onClose={() => setOpen(null)} />}
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
