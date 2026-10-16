import { Link } from "react-router-dom";
import type { HoldingShape, HoldingSignal } from "../../api/client";
import { formatPct } from "../../lib/format";
import { axesFromRecord, ScoreShape, SignalPill } from "../analysis";
import { extraFlags, FlagLine } from "../HoldingsTable";
import { Delta } from "../ui";

/**
 * One holding as a card: a Score Shape, the signal, P&L and weight, and two key facts (strongest
 * and weakest section). The whole card links to the stock page.
 */
export function HoldingCard({
  h,
  shape,
  shapeLoading = false,
  linkQuery = "",
}: {
  h: HoldingSignal;
  shape?: HoldingShape;
  shapeLoading?: boolean;
  linkQuery?: string;
}) {
  const over = h.weight !== null && h.weight > h.max_weight;
  return (
    <article className="relative flex flex-col gap-3 rounded-card border border-border bg-surface p-4 shadow-card transition-colors hover:border-border-strong">
      <header className="min-w-0">
        <h3 className="truncate text-sm font-semibold text-fg">
          <Link to={`/analysis/${encodeURIComponent(h.ticker)}${linkQuery}`} className="after:absolute after:inset-0 after:rounded-card hover:underline">
            {h.label}
          </Link>
        </h3>
        <p className="truncate font-mono text-xs text-fg-subtle">
          {h.ticker}
          {h.sector ? ` · ${h.sector}` : ""}
        </p>
      </header>
      <div className="flex items-center gap-3">
        {shape ? (
          // Above the stretched link so the shape's own hover readout still works.
          <div className="relative z-10 shrink-0">
            <ScoreShape axes={axesFromRecord(shape.axes)} total={shape.total} maxTotal={shape.max_total} step={shape.step} size="md" name={h.label} animate={false} />
          </div>
        ) : shapeLoading ? (
          <div role="status" className="skeleton grid size-[116px] shrink-0 place-items-center rounded-card">
            <span className="sr-only">Working out the Score Shape…</span>
          </div>
        ) : (
          <div className="grid size-[116px] shrink-0 place-items-center rounded-card bg-surface-2 text-center text-xs text-fg-subtle">No shape yet</div>
        )}
        <dl className="min-w-0 space-y-2 text-sm">
          <div>
            <dt className="sr-only">Signal</dt>
            <dd>
              <SignalPill signal={h.signal} label={h.signal_label} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">P&amp;L</dt>
            <dd className="font-semibold">
              <Delta value={h.pnl} format="inr-compact" /> <span className="text-xs font-normal text-fg-muted">{h.pnl_pct === null ? "" : formatPct(h.pnl_pct)}</span>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-fg-subtle">Weight</dt>
            <dd className={over ? "font-semibold text-caution" : "text-fg"}>
              {h.weight === null ? "—" : `${(h.weight * 100).toFixed(1)}%`}
              {over && <span className="text-xs font-normal"> · above {Math.round(h.max_weight * 100)}% max</span>}
            </dd>
          </div>
        </dl>
      </div>
      {(shape?.top.length || extraFlags(h).length > 0) && (
        <div className="space-y-1 border-t border-border pt-2 text-xs text-fg-muted">
          {shape?.top.map((t) => (
            <p key={t}>{t}</p>
          ))}
          {extraFlags(h).map((f) => (
            <FlagLine key={f.key} f={f} />
          ))}
        </div>
      )}
    </article>
  );
}
